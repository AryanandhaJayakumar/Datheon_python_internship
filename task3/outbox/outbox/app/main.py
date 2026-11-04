"""Outbox: a notification microservice.

* POST /api/notifications queues an email or webhook and returns 202 immediately.
* FastAPI BackgroundTasks does the actual delivery (with retries) after the response.
* A sliding-window rate limiter protects the send endpoint.
"""
import asyncio
import ipaddress
import os
import re
import smtplib
import time
import uuid
from collections import OrderedDict, defaultdict, deque
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

import httpx
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, model_validator

# ---------- Settings (environment variables) ----------
RATE_LIMIT = int(os.getenv("RATE_LIMIT", "5"))
RATE_WINDOW = int(os.getenv("RATE_WINDOW", "60"))
MAX_ATTEMPTS = int(os.getenv("MAX_ATTEMPTS", "3"))
MAX_JOBS_KEPT = 50
TRUST_PROXY = os.getenv("TRUST_PROXY", "false").lower() == "true"
ALLOW_PRIVATE_WEBHOOKS = os.getenv("ALLOW_PRIVATE_WEBHOOKS", "false").lower() == "true"
SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
SMTP_FROM = os.getenv("SMTP_FROM", "outbox@localhost")

STATIC_DIR = Path(__file__).parent / "static"
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

app = FastAPI(title="Outbox", version="1.0.0")

# ---------- In-memory stores ----------
JOBS: "OrderedDict[str, dict]" = OrderedDict()
_hits: dict[str, deque] = defaultdict(deque)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------- Rate limiting (sliding window, per client IP) ----------
def client_ip(request: Request) -> str:
    if TRUST_PROXY:
        fwd = request.headers.get("x-forwarded-for")
        if fwd:
            return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def window_state(ip: str) -> tuple[int, int]:
    """Return (remaining, seconds_until_reset) without consuming a slot."""
    now = time.monotonic()
    hits = _hits[ip]
    while hits and now - hits[0] >= RATE_WINDOW:
        hits.popleft()
    remaining = max(0, RATE_LIMIT - len(hits))
    reset = int(RATE_WINDOW - (now - hits[0]) + 0.999) if hits else 0
    return remaining, reset


async def rate_limit(request: Request, response: Response) -> None:
    ip = client_ip(request)
    remaining, reset = window_state(ip)
    if remaining == 0:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit reached. Try again in {reset} seconds.",
            headers={
                "Retry-After": str(reset),
                "X-RateLimit-Limit": str(RATE_LIMIT),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(reset),
            },
        )
    _hits[ip].append(time.monotonic())
    remaining, reset = window_state(ip)
    response.headers["X-RateLimit-Limit"] = str(RATE_LIMIT)
    response.headers["X-RateLimit-Remaining"] = str(remaining)
    response.headers["X-RateLimit-Reset"] = str(reset)


# ---------- Schemas ----------
def check_webhook_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("Enter a full URL starting with http:// or https://")
    if ALLOW_PRIVATE_WEBHOOKS:
        return
    host = parsed.hostname
    blocked = "Webhook URLs that point to private or local addresses are blocked"
    if host.lower() == "localhost":
        raise ValueError(blocked)
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return  # a normal hostname
    if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
        raise ValueError(blocked)


class NotificationIn(BaseModel):
    channel: Literal["email", "webhook"]
    target: str = Field(min_length=3, max_length=500)
    subject: str = Field(default="", max_length=150)
    message: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def validate_target(self):
        if self.channel == "email":
            if not EMAIL_RE.match(self.target):
                raise ValueError("Enter a valid email address")
        else:
            check_webhook_url(self.target)
        return self


# ---------- Delivery (runs in the background) ----------
def _smtp_send(job: dict) -> None:
    msg = EmailMessage()
    msg["From"], msg["To"] = SMTP_FROM, job["target"]
    msg["Subject"] = job["subject"] or "Notification"
    msg.set_content(job["message"])
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as smtp:
        smtp.starttls()
        if SMTP_USER:
            smtp.login(SMTP_USER, SMTP_PASSWORD or "")
        smtp.send_message(msg)


async def send_email(job: dict) -> str:
    if SMTP_HOST:
        await asyncio.to_thread(_smtp_send, job)
        return "Sent through SMTP"
    await asyncio.sleep(1.5)  # simulate network latency
    return "Simulated send. Set SMTP_HOST to deliver real email."


async def send_webhook(job: dict) -> str:
    payload = {"id": job["id"], "subject": job["subject"], "message": job["message"]}
    async with httpx.AsyncClient(timeout=8, follow_redirects=False) as client:
        resp = await client.post(job["target"], json=payload)
        resp.raise_for_status()
    return f"Receiver answered {resp.status_code}"


async def deliver(job_id: str) -> None:
    job = JOBS[job_id]
    for attempt in range(1, MAX_ATTEMPTS + 1):
        job.update(status="sending", attempts=attempt)
        try:
            sender = send_email if job["channel"] == "email" else send_webhook
            detail = await sender(job)
            job.update(status="delivered", detail=detail, finished_at=now_iso())
            return
        except Exception as exc:  # noqa: BLE001
            job["detail"] = f"Attempt {attempt} of {MAX_ATTEMPTS} failed: {exc}"
            if attempt < MAX_ATTEMPTS:
                await asyncio.sleep(0.5 * 2**attempt)  # exponential backoff
    job.update(status="failed", finished_at=now_iso())


# ---------- Routes ----------
@app.get("/health")
async def health():
    return {"status": "ok", "jobs_tracked": len(JOBS)}


@app.get("/api/rate-limit")
async def rate_status(request: Request):
    remaining, reset = window_state(client_ip(request))
    return {"limit": RATE_LIMIT, "remaining": remaining, "reset_in": reset, "window": RATE_WINDOW}


@app.post("/api/notifications", status_code=202, dependencies=[Depends(rate_limit)])
async def create_notification(body: NotificationIn, background_tasks: BackgroundTasks):
    job = {
        "id": uuid.uuid4().hex[:10],
        "channel": body.channel,
        "target": body.target,
        "subject": body.subject,
        "message": body.message,
        "status": "queued",
        "attempts": 0,
        "detail": "Waiting for a worker",
        "created_at": now_iso(),
        "finished_at": None,
    }
    JOBS[job["id"]] = job
    while len(JOBS) > MAX_JOBS_KEPT:
        JOBS.popitem(last=False)
    background_tasks.add_task(deliver, job["id"])  # runs after the 202 is sent
    return job


@app.get("/api/jobs")
async def list_jobs():
    return list(reversed(JOBS.values()))


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str):
    if job_id not in JOBS:
        raise HTTPException(404, "Job not found")
    return JOBS[job_id]


@app.get("/", include_in_schema=False)
async def index():
    return FileResponse(STATIC_DIR / "index.html")
