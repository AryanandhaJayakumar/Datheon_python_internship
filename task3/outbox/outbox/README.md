# Outbox: FastAPI background-task microservice

Queues emails and webhooks, delivers them in the background (with retries),
rate-limits senders, and ships as a multi-stage Docker image.

## Run with Docker
    docker build -t outbox .
    docker run -d --name outbox -p 8000:8000 outbox
    # or: docker compose up --build

Open http://localhost:8000 (UI) or http://localhost:8000/docs (Swagger).

## Run without Docker
    python -m venv .venv && source .venv/bin/activate
    pip install -r requirements.txt
    uvicorn app.main:app --reload

## Test with curl
    # health
    curl http://localhost:8000/health

    # queue an email (returns 202 immediately)
    curl -i -X POST http://localhost:8000/api/notifications \
      -H "Content-Type: application/json" \
      -d '{"channel":"email","target":"you@example.com","subject":"Hello","message":"Sent in the background"}'

    # queue a webhook (grab a free URL from https://webhook.site)
    curl -X POST http://localhost:8000/api/notifications \
      -H "Content-Type: application/json" \
      -d '{"channel":"webhook","target":"https://webhook.site/YOUR-ID","message":"ping"}'

    # watch status change: queued -> sending -> delivered
    curl http://localhost:8000/api/jobs

    # trigger the rate limiter (5 per 60s by default): the 6th returns 429
    for i in $(seq 1 6); do
      curl -s -o /dev/null -w "%{http_code}\n" -X POST http://localhost:8000/api/notifications \
        -H "Content-Type: application/json" \
        -d '{"channel":"email","target":"a@b.co","message":"hi"}'
    done

## Configuration (environment variables)
| Variable | Default | Purpose |
|---|---|---|
| RATE_LIMIT / RATE_WINDOW | 5 / 60 | Sends allowed per client per window (seconds) |
| MAX_ATTEMPTS | 3 | Delivery tries with exponential backoff |
| SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM | unset | Set SMTP_HOST for real email; otherwise sends are simulated |
| TRUST_PROXY | false | Use X-Forwarded-For for client IP behind a proxy |
| ALLOW_PRIVATE_WEBHOOKS | false | Allow webhooks to localhost/private IPs |

## Notes
Jobs and rate-limit counters are in memory and run with one worker. For multiple
workers or replicas, move both to Redis and use a task queue (Celery, ARQ).
