"""
AuthNexa - User Authentication & RBAC with JWT
Frontend + backend in ONE file.

Install:
    pip install fastapi uvicorn python-multipart "python-jose[cryptography]" "passlib[bcrypt]" "bcrypt==4.0.1"

Run:
    python main.py

Website:     http://127.0.0.1:8000
Swagger UI:  http://127.0.0.1:8000/docs   (use the green "Authorize" button)

Demo admin account:  admin / Admin@123
"""

import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Annotated, Optional

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.responses import HTMLResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, Field, field_validator

# ---------------------------------------------------------------- Configuration
# In production set SECRET_KEY as an environment variable. If missing, a random
# key is generated on every start (all old tokens become invalid).
SECRET_KEY = os.getenv("SECRET_KEY", secrets.token_hex(32))
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

app = FastAPI(
    title="AuthNexa API",
    description="JWT authentication with bcrypt password hashing and role-based access control.",
    version="1.1.0",
    swagger_ui_parameters={"persistAuthorization": True, "displayRequestDuration": True},
)


# --------------------------------------------------------------------- Schemas
class Role(str, Enum):
    admin = "admin"
    user = "user"


class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=30, examples=["alice_01"])
    password: str = Field(..., min_length=8, max_length=72, examples=["Str0ngPass"])
    full_name: Optional[str] = Field(None, max_length=80, examples=["Alice Johnson"])

    @field_validator("username")
    @classmethod
    def valid_username(cls, v: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9_]+", v):
            raise ValueError("username may only contain letters, numbers and underscores")
        return v.lower()

    @field_validator("password")
    @classmethod
    def strong_password(cls, v: str) -> str:
        if not (re.search(r"[A-Za-z]", v) and re.search(r"\d", v)):
            raise ValueError("password must contain at least one letter and one number")
        if len(v.encode("utf-8")) > 72:
            raise ValueError("password is too long (bcrypt limit is 72 bytes)")
        return v


class UserPublic(BaseModel):
    username: str
    full_name: Optional[str] = None
    role: Role
    created_at: datetime


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(..., description="Lifetime in seconds")


class RoleUpdate(BaseModel):
    role: Role


# ------------------------------------------- In-memory store (use a DB in prod)
users_db: dict[str, dict] = {}


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def add_user(username: str, password: str, role: Role, full_name: Optional[str] = None) -> dict:
    user = {
        "username": username,
        "full_name": full_name,
        "role": role,
        "hashed_password": hash_password(password),
        "created_at": datetime.now(timezone.utc),
    }
    users_db[username] = user
    return user


add_user("admin", "Admin@123", Role.admin, "System Administrator")
DUMMY_HASH = hash_password("dummy-password-for-timing")


# ------------------------------------------------------ JWT helpers/dependencies
def create_access_token(username: str, role: Role) -> str:
    now = datetime.now(timezone.utc)
    claims = {
        "sub": username,
        "role": role.value,
        "iat": now,
        "exp": now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(claims, SECRET_KEY, algorithm=ALGORITHM)


async def get_current_user(token: Annotated[str, Depends(oauth2_scheme)]) -> dict:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: Optional[str] = payload.get("sub")
        if username is None:
            raise credentials_error
    except JWTError:
        # Covers bad signature, malformed token and expired token.
        raise credentials_error

    user = users_db.get(username)
    if user is None:
        raise credentials_error
    return user


CurrentUser = Annotated[dict, Depends(get_current_user)]


def require_roles(*allowed: Role):
    """Dependency factory: only users with one of the given roles may pass."""

    async def checker(user: CurrentUser) -> dict:
        if user["role"] not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires role: {', '.join(r.value for r in allowed)}",
            )
        return user

    return checker


AdminUser = Annotated[dict, Depends(require_roles(Role.admin))]


def to_public(user: dict) -> UserPublic:
    return UserPublic(**{k: user[k] for k in ("username", "full_name", "role", "created_at")})


# -------------------------------------------------------------- Auth endpoints
@app.post(
    "/auth/register",
    response_model=UserPublic,
    status_code=status.HTTP_201_CREATED,
    tags=["Auth"],
    summary="Register a new account (always gets the 'user' role)",
)
async def register(data: UserCreate):
    if data.username in users_db:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already taken")
    return to_public(add_user(data.username, data.password, Role.user, data.full_name))


@app.post("/auth/login", response_model=Token, tags=["Auth"], summary="Log in and receive a JWT")
async def login(form: Annotated[OAuth2PasswordRequestForm, Depends()]):
    user = users_db.get(form.username.lower())
    # Always run a hash check so response time does not reveal valid usernames.
    valid = verify_password(form.password, user["hashed_password"] if user else DUMMY_HASH)
    if not user or not valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return Token(
        access_token=create_access_token(user["username"], user["role"]),
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


# ------------------------------------------------------- Protected endpoints
@app.get("/users/me", response_model=UserPublic, tags=["Protected"], summary="Current user profile")
async def read_me(user: CurrentUser):
    return to_public(user)


@app.get("/protected/data", tags=["Protected"], summary="Data for any logged-in user")
async def protected_data(user: CurrentUser):
    return {
        "message": f"Hello {user['username']}, this data is only for authenticated users.",
        "server_time": datetime.now(timezone.utc).isoformat(),
        "your_role": user["role"],
    }


@app.get("/stats", tags=["Protected"], summary="Account totals for the dashboard")
async def stats(_: CurrentUser):
    return {
        "total_users": len(users_db),
        "admins": sum(1 for u in users_db.values() if u["role"] == Role.admin),
    }


# ------------------------------------------------------ Admin-only endpoints
@app.get("/admin/users", response_model=list[UserPublic], tags=["Admin"], summary="List all users")
async def list_users(_: AdminUser):
    return [to_public(u) for u in users_db.values()]


@app.patch(
    "/admin/users/{username}/role",
    response_model=UserPublic,
    tags=["Admin"],
    summary="Change a user's role",
)
async def change_role(username: str, body: RoleUpdate, admin: AdminUser):
    target = users_db.get(username)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if target["username"] == admin["username"]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot change your own role")
    target["role"] = body.role
    return to_public(target)


@app.delete(
    "/admin/users/{username}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["Admin"],
    summary="Delete a user",
)
async def delete_user(username: str, admin: AdminUser):
    if username not in users_db:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if username == admin["username"]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot delete yourself")
    del users_db[username]


# ------------------------------------------------------ Frontend (served at "/")
@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def home():
    return HTML_PAGE


HTML_PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AuthNexa</title>
<link href="https://fonts.googleapis.com/css2?family=Sora:wght@500;700&amp;family=IBM+Plex+Sans:wght@400;500;600&amp;family=IBM+Plex+Mono:wght@400;500&amp;display=swap" rel="stylesheet">
<style>
:root{--bg:#070a14;--p:#0f1527;--p2:#151d36;--ln:#242e4d;--ink:#e9eeff;--mu:#8e9bc2;--v:#7c6cff;--m:#3be8b0;--w:#ffc857;--r:#ff6b86;--b:#5cc8ff}
*{box-sizing:border-box;margin:0}
body{font:15px/1.5 "IBM Plex Sans",system-ui,sans-serif;background:var(--bg);color:var(--ink);min-height:100vh;overflow-x:hidden}
body::before,body::after{content:"";position:fixed;z-index:-1;width:60vmax;height:60vmax;border-radius:50%;filter:blur(110px);opacity:.28;animation:drift 22s ease-in-out infinite alternate}
body::before{background:var(--v);top:-30vmax;right:-15vmax}
body::after{background:var(--m);bottom:-35vmax;left:-20vmax;animation-delay:-9s;opacity:.18}
@keyframes drift{to{transform:translate(-6vmax,5vmax) scale(1.15)}}
h1,h2,h3{font-family:Sora,sans-serif;letter-spacing:-.02em}
button{font:inherit;cursor:pointer}
:focus-visible{outline:2px solid var(--m);outline-offset:2px}
.hide{display:none!important}
.card{background:linear-gradient(180deg,var(--p),var(--p2));border:1px solid var(--ln);border-radius:16px;padding:22px}
.mono{font-family:"IBM Plex Mono",monospace;font-size:.78rem}
.btn{border:0;border-radius:10px;padding:11px 18px;font-weight:600;color:#06121a;background:linear-gradient(135deg,var(--m),var(--b));transition:transform .15s,box-shadow .15s}
.btn:hover{transform:translateY(-1px);box-shadow:0 8px 22px -8px var(--m)}
.btn:disabled{opacity:.6;cursor:wait;transform:none}
.btn.sm{padding:7px 12px;font-size:.84rem}
.btn.ghost,.btn.danger{background:transparent;color:var(--ink);border:1.5px solid var(--ln)}
.btn.ghost:hover{border-color:var(--m);color:var(--m);box-shadow:none}
.btn.danger{color:var(--r)}.btn.danger:hover{border-color:var(--r);box-shadow:none}
.badge{font-size:.74rem;font-weight:600;padding:3px 10px;border-radius:99px;display:inline-block}
.badge.admin{background:rgba(255,200,87,.14);color:var(--w)}.badge.user{background:rgba(92,200,255,.14);color:var(--b)}
.badge.ok{background:rgba(59,232,176,.14);color:var(--m)}.badge.bad{background:rgba(255,107,134,.14);color:var(--r)}
/* auth */
.auth{display:grid;grid-template-columns:1.1fr 1fr;gap:56px;align-items:center;max-width:1100px;margin:0 auto;min-height:100vh;padding:32px 24px}
.pitch svg{width:120px;height:140px;filter:drop-shadow(0 0 28px rgba(124,108,255,.55));animation:float 6s ease-in-out infinite alternate}
@keyframes float{to{transform:translateY(-8px)}}
.pitch h1{font-size:clamp(2rem,4.6vw,3.2rem);line-height:1.08;margin:22px 0 14px}
.pitch p{color:var(--mu);max-width:440px;margin-bottom:20px}
.chips{display:flex;flex-wrap:wrap;gap:8px}.chip{font-size:.8rem;padding:5px 12px;border:1px solid var(--ln);border-radius:99px;color:var(--mu)}
.tabs{display:grid;grid-template-columns:1fr 1fr;background:var(--bg);border-radius:12px;padding:4px;margin-bottom:20px;position:relative}
.tabs i{position:absolute;top:4px;bottom:4px;left:4px;width:calc(50% - 4px);background:var(--p2);border-radius:9px;box-shadow:0 0 0 1px var(--ln);transition:transform .3s}
.tabs.reg i{transform:translateX(100%)}
.tabs button{position:relative;background:none;border:0;color:var(--mu);padding:10px;font-weight:600}.tabs button.on{color:var(--ink)}
form{display:grid;gap:14px;animation:fade .35s}
@keyframes fade{from{opacity:0;transform:translateY(6px)}}
label{font-size:.8rem;font-weight:600;color:var(--mu);display:grid;gap:6px}
.inp{position:relative}
input{font:inherit;color:var(--ink);background:var(--bg);border:1.5px solid var(--ln);border-radius:10px;padding:11px 14px;width:100%;outline:none;transition:border-color .2s,box-shadow .2s}
input:focus{border-color:var(--v);box-shadow:0 0 0 4px rgba(124,108,255,.18)}
.eye{position:absolute;right:6px;top:50%;transform:translateY(-50%);background:none;border:0;color:var(--mu);padding:6px 8px;font-size:.78rem;font-weight:600}
.meter{display:grid;grid-template-columns:repeat(4,1fr);gap:4px}.meter b{height:4px;border-radius:2px;background:var(--ln);transition:background .25s}
.hints{list-style:none;padding:0;display:flex;flex-wrap:wrap;gap:4px 14px;font-size:.78rem;color:var(--mu)}
.hints li::before{content:"\25CB  "}.hints li.ok{color:var(--m)}.hints li.ok::before{content:"\25CF  "}
.msg{font-size:.85rem;min-height:1.2em}.msg.err{color:var(--r)}.msg.ok{color:var(--m)}
.hint{font-size:.8rem;color:var(--mu);text-align:center}.hint a{color:var(--b);cursor:pointer;text-decoration:underline}
/* shell */
.shell{display:grid;grid-template-columns:230px 1fr;min-height:100vh}
.side{border-right:1px solid var(--ln);padding:20px 14px;display:flex;flex-direction:column;gap:6px;position:sticky;top:0;height:100vh;background:rgba(7,10,20,.7);backdrop-filter:blur(10px)}
.brand{display:flex;align-items:center;gap:10px;font:700 1.15rem Sora;padding:0 8px 18px}
.brand svg{width:26px;height:30px}
.nav button{display:flex;align-items:center;gap:10px;width:100%;background:none;border:0;color:var(--mu);padding:10px 12px;border-radius:10px;text-align:left;font-weight:500}
.nav button:hover{background:var(--p)}.nav button.on{background:var(--p2);color:var(--ink);box-shadow:inset 3px 0 var(--m)}
.side .out{margin-top:auto}
main{padding:28px clamp(16px,3vw,40px) 60px;max-width:1100px;width:100%}
main h1{font-size:1.7rem;margin-bottom:4px}main .sub{color:var(--mu);margin-bottom:22px}
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:16px}
.stat small{color:var(--mu);font-size:.8rem}.stat div{font:700 1.7rem Sora;margin-top:4px}
.two{display:grid;grid-template-columns:1fr 1fr;gap:16px}
.profile{display:flex;gap:16px;align-items:center;margin-bottom:14px}
.avatar{width:60px;height:60px;border-radius:16px;display:grid;place-items:center;font:700 1.6rem Sora;color:#06121a;background:linear-gradient(135deg,var(--v),var(--m))}
.kv{display:grid;grid-template-columns:auto 1fr;gap:8px 16px;font-size:.9rem}.kv b{color:var(--mu);font-weight:500}
h3{font-size:1.02rem;margin-bottom:12px}
.token{word-break:break-all;color:var(--b);background:var(--bg);padding:12px;border-radius:10px;border:1px solid var(--ln);max-height:110px;overflow:auto}
.facts{padding-left:18px;color:var(--mu);display:grid;gap:6px}
/* tester */
.tests{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:12px}
.console{background:#050813;border:1px solid var(--ln);border-radius:12px;padding:14px;min-height:170px;max-height:300px;overflow:auto;white-space:pre-wrap;word-break:break-word}
.console .st{font-weight:600;padding:2px 8px;border-radius:6px;margin-right:6px}
.st.c2{background:rgba(59,232,176,.16);color:var(--m)}.st.c4{background:rgba(255,200,87,.16);color:var(--w)}.st.c5{background:rgba(255,107,134,.16);color:var(--r)}
.j-k{color:var(--b)}.j-s{color:var(--m)}.j-n{color:var(--w)}.j-b{color:var(--v)}
.hist{display:flex;flex-wrap:wrap;gap:6px;margin-top:12px}.hist button{background:var(--bg);border:1px solid var(--ln);color:var(--mu);border-radius:8px;padding:4px 10px}
.spin{display:inline-block;width:14px;height:14px;border:2px solid var(--ln);border-top-color:var(--m);border-radius:50%;animation:rot .7s linear infinite;vertical-align:-2px;margin-right:8px}
@keyframes rot{to{transform:rotate(1turn)}}
/* users */
.bar{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:14px}.bar input{flex:1;min-width:180px}.bar select{font:inherit;color:var(--ink);background:var(--bg);border:1.5px solid var(--ln);border-radius:10px;padding:0 12px}
.scroll{overflow-x:auto}table{width:100%;border-collapse:collapse;min-width:520px}
th{text-align:left;color:var(--mu);font-weight:500;font-size:.82rem;padding:8px 10px}td{padding:11px 10px;border-top:1px solid var(--ln)}td .btn{margin-right:6px}
.empty{text-align:center;color:var(--mu);padding:34px 10px}
/* toast + dialog */
#toasts{position:fixed;right:16px;bottom:16px;display:grid;gap:8px;z-index:50}
.toast{background:var(--p2);border:1px solid var(--ln);border-left:4px solid var(--m);padding:10px 16px;border-radius:10px;animation:fade .25s;box-shadow:0 10px 30px -10px #000}
.toast.err{border-left-color:var(--r)}
dialog{margin:auto;background:var(--p2);color:var(--ink);border:1px solid var(--ln);border-radius:16px;padding:24px;max-width:380px}
dialog::backdrop{background:rgba(3,5,12,.7);backdrop-filter:blur(3px)}
dialog p{color:var(--mu);margin:8px 0 20px}dialog .row{display:flex;gap:10px;justify-content:flex-end}
@media(max-width:860px){
 .auth,.two{grid-template-columns:1fr}.stats{grid-template-columns:1fr 1fr}
 .shell{grid-template-columns:1fr}
 .side{position:fixed;inset:auto 0 0 0;height:auto;flex-direction:row;padding:6px;z-index:20;border:0;border-top:1px solid var(--ln);background:var(--bg)}
 .brand,.side .out span{display:none}.side .out{margin:0}.nav{display:flex;flex:1}.nav button{flex-direction:column;gap:2px;font-size:.72rem;padding:6px;text-align:center;align-items:center}
 main{padding-bottom:96px}
}
@media(prefers-reduced-motion:reduce){*,::before,::after{animation:none!important;transition:none!important}}
</style>
</head>
<body>
<svg width="0" height="0" style="position:absolute"><defs><linearGradient id="sg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#7c6cff"/><stop offset="1" stop-color="#3be8b0"/></linearGradient>
<symbol id="shield" viewBox="0 0 120 140"><path d="M60 6 108 24v40c0 36-20 60-48 70C32 124 12 100 12 64V24z" fill="url(#sg)" opacity=".18" stroke="url(#sg)" stroke-width="4"/><rect x="40" y="62" width="40" height="32" rx="6" fill="url(#sg)"/><path d="M47 62v-9a13 13 0 0 1 26 0v9" fill="none" stroke="url(#sg)" stroke-width="6"/><circle cx="60" cy="78" r="5" fill="#070a14"/></symbol></defs></svg>

<section id="authView" class="auth">
  <div class="pitch">
    <svg><use href="#shield"/></svg>
    <h1>Welcome to AuthNexa</h1>
    <p>Create an account, log in to get a signed token, then see which protected and admin-only endpoints accept or reject it.</p>
    <div class="chips"><span class="chip">bcrypt hashing</span><span class="chip">OAuth2 Bearer</span><span class="chip">30 min tokens</span><span class="chip">Role-based access</span></div>
  </div>
  <div class="card">
    <div class="tabs" id="tabs"><i></i><button id="tabLogin" class="on">Log in</button><button id="tabReg">Register</button></div>
    <form id="loginForm">
      <label>Username<input id="lUser" autocomplete="username" required></label>
      <label>Password<span class="inp"><input id="lPass" type="password" autocomplete="current-password" required><button type="button" class="eye" data-t="lPass">Show</button></span></label>
      <div class="msg" id="lMsg" role="alert"></div>
      <button class="btn" id="lBtn">Log in</button>
      <div class="hint">Demo admin: <a id="fill">admin / Admin@123</a></div>
    </form>
    <form id="regForm" class="hide">
      <label>Full name<input id="rName" autocomplete="name"></label>
      <label>Username<input id="rUser" autocomplete="username" required minlength="3" maxlength="30" pattern="[A-Za-z0-9_]+" title="Letters, numbers and underscores"></label>
      <label>Password<span class="inp"><input id="rPass" type="password" autocomplete="new-password" required minlength="8" maxlength="72"><button type="button" class="eye" data-t="rPass">Show</button></span></label>
      <div class="meter" id="meter"><b></b><b></b><b></b><b></b></div>
      <ul class="hints" id="hints"><li data-k="0">8+ characters</li><li data-k="1">A letter</li><li data-k="2">A number</li></ul>
      <div class="msg" id="rMsg" role="alert"></div>
      <button class="btn" id="rBtn">Create account</button>
      <div class="hint">New accounts always get the <b>user</b> role.</div>
    </form>
  </div>
</section>

<div id="dashView" class="shell hide">
  <aside class="side">
    <div class="brand"><svg><use href="#shield"/></svg>AuthNexa</div>
    <nav class="nav" id="nav">
      <button data-v="overview" class="on">&#9638; Overview</button>
      <button data-v="security">&#9919; Security</button>
      <button data-v="tester">&#9654; API tester</button>
      <button data-v="users" id="navUsers">&#9787; Users</button>
    </nav>
    <button class="btn ghost sm out" id="logout">&#10162; <span>Log out</span></button>
  </aside>
  <main>
    <section class="view" id="v-overview">
      <h1 id="welcome"></h1><p class="sub" id="welcomeSub"></p>
      <div class="stats">
        <div class="card stat"><small>Total users</small><div id="sTotal">-</div></div>
        <div class="card stat"><small>Administrators</small><div id="sAdmin">-</div></div>
        <div class="card stat"><small>Your role</small><div id="sRole">-</div></div>
        <div class="card stat"><small>Token status</small><div id="sTok" style="font-size:1.1rem;padding-top:6px">-</div></div>
      </div>
      <div class="two">
        <div class="card"><div class="profile"><div class="avatar" id="avatar">?</div><div><h3 id="pName" style="margin:0"></h3><div class="hint" style="text-align:left" id="pUser"></div></div></div>
          <div class="kv"><b>Role</b><span id="pRole"></span><b>Member since</b><span id="pSince"></span><b>Token expires in</b><span id="pExp"></span></div></div>
        <div class="card"><h3>What to try</h3><ul class="facts"><li>Open <b>API tester</b> and send a request with and without a token.</li><li>Call the admin endpoint as a regular user to see a <b>403</b>.</li><li id="tipAdmin">Admins can manage roles in <b>Users</b>.</li></ul></div>
      </div>
    </section>
    <section class="view hide" id="v-security">
      <h1>Security</h1><p class="sub">The token your browser sends with every request.</p>
      <div class="two">
        <div class="card"><div style="display:flex;justify-content:space-between;align-items:center"><h3>Your JWT</h3><button class="btn ghost sm" id="copyTok">Copy token</button></div><div class="token mono" id="tokenBox"></div></div>
        <div class="card"><h3>Decoded claims</h3><pre class="token mono" id="claims" style="color:var(--ink)"></pre></div>
        <div class="card span2" style="grid-column:1/-1"><h3>How it is protected</h3><ul class="facts"><li>Passwords are stored as bcrypt hashes, never as plain text.</li><li>Tokens are signed with HS256 and expire after 30 minutes.</li><li>Login runs a hash check even for unknown usernames, so timing does not reveal valid accounts.</li><li>The token lives in session storage and is cleared when you log out or close the tab.</li></ul></div>
      </div>
    </section>
    <section class="view hide" id="v-tester">
      <h1>API tester</h1><p class="sub">Send real requests and read the responses.</p>
      <div class="card">
        <div class="tests" id="tests">
          <button class="btn sm ghost" data-p="/users/me">200 &middot; GET /users/me</button>
          <button class="btn sm ghost" data-p="/protected/data">200 &middot; GET /protected/data</button>
          <button class="btn sm ghost" data-p="/admin/users">GET /admin/users (admin only)</button>
          <button class="btn sm danger" data-p="/users/me" data-m="anon">401 &middot; no token</button>
          <button class="btn sm danger" data-p="/users/me" data-m="fake">401 &middot; fake token</button>
        </div>
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px"><span class="hint" id="reqLine">No request sent yet</span><button class="btn ghost sm" id="copyRes">Copy response</button></div>
        <div class="console mono" id="console">Pick a request above. Signed in as a regular user, the admin endpoint returns 403.</div>
        <div class="hist" id="hist"></div>
      </div>
    </section>
    <section class="view hide" id="v-users">
      <h1>Users</h1><p class="sub">Search accounts, change roles or remove people.</p>
      <div class="card">
        <div class="bar"><input id="q" placeholder="Search by username or name" aria-label="Search users"><select id="rf" aria-label="Filter by role"><option value="">All roles</option><option value="admin">Admins</option><option value="user">Users</option></select><button class="btn ghost sm" id="refresh">Refresh</button></div>
        <div class="scroll"><table><thead><tr><th>User</th><th>Name</th><th>Role</th><th>Actions</th></tr></thead><tbody id="rows"></tbody></table></div>
        <div class="empty hide" id="empty"></div>
      </div>
    </section>
  </main>
</div>

<div id="toasts" aria-live="polite"></div>
<dialog id="dlg"><h3 id="dT"></h3><p id="dP"></p><div class="row"><button class="btn ghost sm" id="dNo">Cancel</button><button class="btn danger sm" id="dYes">Confirm</button></div></dialog>

<script>
const $=s=>document.querySelector(s),$$=s=>[...document.querySelectorAll(s)];
const esc=s=>String(s??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
let token=sessionStorage.getItem("jwt")||null,me=null,tick=null,hist=[],users=[],lastText="";

function toast(t,k=""){const d=document.createElement("div");d.className="toast "+k;d.textContent=t;$("#toasts").append(d);setTimeout(()=>d.remove(),3200)}
function parseJwt(t){try{return JSON.parse(atob(t.split(".")[1].replace(/-/g,"+").replace(/_/g,"/")))}catch(e){return null}}
function errText(d){return Array.isArray(d)?d.map(x=>x.loc.slice(-1)+": "+x.msg).join(" | "):(d||"Something went wrong")}
function copy(t,label){navigator.clipboard.writeText(t).then(()=>toast(label+" copied"),()=>toast("Copy failed","err"))}
function confirmBox(title,text){return new Promise(res=>{const d=$("#dlg");$("#dT").textContent=title;$("#dP").textContent=text;
  const done=v=>{d.close();res(v)};$("#dYes").onclick=()=>done(true);$("#dNo").onclick=()=>done(false);d.oncancel=()=>res(false);d.showModal()})}
function json(o){return esc(JSON.stringify(o,null,2)).replace(/(&quot;[^&]*?&quot;)(\s*:)?|\b(true|false|null)\b|-?\d+\.?\d*/g,(m,s,c,b)=>
  s?(c?`<span class="j-k">${s}</span>${c}`:`<span class="j-s">${s}</span>`):b?`<span class="j-b">${m}</span>`:`<span class="j-n">${m}</span>`)}

async function api(path,opt={},mode="auth"){
  const h={...(opt.headers||{})};
  if(mode==="fake")h.Authorization="Bearer not.a.valid.token";else if(mode==="auth"&&token)h.Authorization="Bearer "+token;
  const r=await fetch(path,{...opt,headers:h});let body=null;try{body=r.status===204?null:await r.json()}catch(e){}
  return {ok:r.ok,status:r.status,body};
}
function busy(btn,on,text){btn.disabled=on;if(text)btn.textContent=on?"Please wait...":text}

/* auth tabs */
function tab(reg){$("#tabs").classList.toggle("reg",reg);$("#tabLogin").classList.toggle("on",!reg);$("#tabReg").classList.toggle("on",reg);$("#loginForm").classList.toggle("hide",reg);$("#regForm").classList.toggle("hide",!reg)}
$("#tabLogin").onclick=()=>tab(false);$("#tabReg").onclick=()=>tab(true);
$("#fill").onclick=()=>{$("#lUser").value="admin";$("#lPass").value="Admin@123"};
$$(".eye").forEach(b=>b.onclick=()=>{const i=$("#"+b.dataset.t),s=i.type==="password";i.type=s?"text":"password";b.textContent=s?"Hide":"Show"});

/* password strength */
$("#rPass").addEventListener("input",e=>{
  const p=e.target.value,c=[p.length>=8,/[A-Za-z]/.test(p),/\d/.test(p)];
  const s=c.filter(Boolean).length+(p.length>=12)+(/[A-Z]/.test(p)&&/[a-z]/.test(p))+(/[^A-Za-z0-9]/.test(p));
  const n=p?Math.max(1,Math.ceil(s*4/6)):0,col=["","var(--r)","var(--w)","var(--b)","var(--m)"][n];
  $$("#meter b").forEach((b,i)=>b.style.background=i<n?col:"");
  $$("#hints li").forEach(li=>li.classList.toggle("ok",c[li.dataset.k]));
});

/* register + login */
$("#regForm").addEventListener("submit",async e=>{
  e.preventDefault();const m=$("#rMsg");m.className="msg";m.textContent="";busy($("#rBtn"),true,"Create account");
  const r=await api("/auth/register",{method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({username:$("#rUser").value.trim(),password:$("#rPass").value,full_name:$("#rName").value.trim()||null})},"none");
  busy($("#rBtn"),false,"Create account");
  if(r.ok){toast("Account created. Log in to continue.");$("#lUser").value=r.body.username;$("#lPass").value="";e.target.reset();$("#rPass").dispatchEvent(new Event("input"));tab(false);$("#lPass").focus()}
  else{m.className="msg err";m.textContent=errText(r.body&&r.body.detail)}
});
$("#loginForm").addEventListener("submit",async e=>{
  e.preventDefault();const m=$("#lMsg");m.className="msg";m.textContent="";busy($("#lBtn"),true,"Log in");
  const body=new URLSearchParams({username:$("#lUser").value.trim(),password:$("#lPass").value});
  const r=await api("/auth/login",{method:"POST",headers:{"Content-Type":"application/x-www-form-urlencoded"},body},"none");
  busy($("#lBtn"),false,"Log in");
  if(!r.ok){m.className="msg err";m.textContent=errText(r.body&&r.body.detail);return}
  token=r.body.access_token;sessionStorage.setItem("jwt",token);await boot();
});
function logout(msg){token=null;me=null;sessionStorage.removeItem("jwt");clearInterval(tick);show();if(msg)toast(msg,"err")}
$("#logout").onclick=()=>{logout();toast("Logged out")};
function show(){const on=!!me;$("#authView").classList.toggle("hide",on);$("#dashView").classList.toggle("hide",!on)}

/* navigation */
function go(v){$$(".view").forEach(x=>x.classList.toggle("hide",x.id!=="v-"+v));$$("#nav button").forEach(b=>b.classList.toggle("on",b.dataset.v===v));if(v==="users")loadUsers()}
$("#nav").onclick=e=>{const b=e.target.closest("button");if(b)go(b.dataset.v)};

async function boot(){
  if(!token){show();return}
  const r=await api("/users/me");
  if(!r.ok){logout();return}
  me=r.body;const cl=parseJwt(token)||{},admin=me.role==="admin";
  const name=me.full_name||me.username,hr=new Date().getHours();
  $("#welcome").textContent=`${hr<12?"Good morning":hr<18?"Good afternoon":"Good evening"}, ${name.split(" ")[0]}`;
  $("#welcomeSub").textContent=admin?"You have full administrator access.":"You are signed in with standard access.";
  $("#avatar").textContent=name[0].toUpperCase();$("#pName").textContent=name;$("#pUser").textContent="@"+me.username;
  $("#pRole").innerHTML=`<span class="badge ${me.role}">${me.role}</span>`;$("#sRole").innerHTML=`<span class="badge ${me.role}" style="font-size:1rem">${me.role}</span>`;
  $("#pSince").textContent=new Date(me.created_at).toLocaleDateString();
  $("#tokenBox").textContent=token;$("#claims").textContent=JSON.stringify(cl,null,2);
  $("#navUsers").classList.toggle("hide",!admin);$("#tipAdmin").classList.toggle("hide",!admin);
  clearInterval(tick);
  const upd=()=>{const s=Math.max(0,cl.exp-Math.floor(Date.now()/1000));
    $("#pExp").textContent=s?`${Math.floor(s/60)}m ${s%60}s`:"expired";
    $("#sTok").innerHTML=s?'<span class="badge ok">Active</span>':'<span class="badge bad">Expired</span>';
    if(!s){clearInterval(tick);toast("Your token expired. Log in again.","err")}};
  upd();tick=setInterval(upd,1000);
  const st=await api("/stats");if(st.ok){$("#sTotal").textContent=st.body.total_users;$("#sAdmin").textContent=st.body.admins}
  show();go("overview");
}
$("#copyTok").onclick=()=>copy(token,"Token");

/* API tester */
function render(h){
  const c=h.status<300?"c2":h.status<500?"c4":"c5";
  lastText=JSON.stringify(h.body,null,2)??"";
  $("#reqLine").textContent=`${h.label} - ${h.ms} ms`;
  $("#console").innerHTML=`<span class="st ${c}">${h.status}</span>${esc(h.label)}\n\n${h.body===null?"(empty body)":json(h.body)}`;
}
$("#tests").onclick=async e=>{
  const b=e.target.closest("button");if(!b)return;
  const p=b.dataset.p,mode=b.dataset.m||"auth",tag=mode==="anon"?" (no token)":mode==="fake"?" (fake token)":"";
  $$("#tests button").forEach(x=>x.disabled=true);
  $("#console").innerHTML='<span class="spin"></span>Sending request...';
  const t0=performance.now(),r=await api(p,{},mode),h={status:r.status,body:r.body,label:`GET ${p}${tag}`,ms:Math.round(performance.now()-t0)};
  $$("#tests button").forEach(x=>x.disabled=false);
  hist.unshift(h);hist=hist.slice(0,8);render(h);
  $("#hist").innerHTML=hist.map((x,i)=>`<button data-i="${i}"><span class="${x.status<300?"j-s":x.status<500?"j-n":"j-k"}">${x.status}</span> ${esc(x.label.replace("GET ",""))}</button>`).join("");
  toast(`${r.status} ${r.ok?"Request succeeded":r.status===401?"Unauthorized":r.status===403?"Forbidden":"Request failed"}`,r.ok?"":"err");
  if(r.status===401&&mode==="auth")setTimeout(()=>logout("Session ended. Log in again."),1200);
};
$("#hist").onclick=e=>{const b=e.target.closest("button");if(b)render(hist[b.dataset.i])};
$("#copyRes").onclick=()=>lastText?copy(lastText,"Response"):toast("Send a request first","err");

/* users */
async function loadUsers(){
  const r=await api("/admin/users");if(!r.ok){toast(errText(r.body&&r.body.detail),"err");return}
  users=r.body;drawUsers();
}
function drawUsers(){
  const q=$("#q").value.trim().toLowerCase(),rf=$("#rf").value;
  const list=users.filter(u=>(!rf||u.role===rf)&&(!q||u.username.includes(q)||(u.full_name||"").toLowerCase().includes(q)));
  $("#rows").innerHTML=list.map(u=>{const self=u.username===me.username,next=u.role==="admin"?"user":"admin";
    return `<tr><td>@${esc(u.username)}</td><td>${esc(u.full_name||"-")}</td><td><span class="badge ${u.role}">${u.role}</span></td>
    <td>${self?'<span class="hint">This is you</span>':`<button class="btn sm ghost" data-role="${esc(u.username)}" data-next="${next}">Make ${next}</button><button class="btn sm danger" data-del="${esc(u.username)}">Delete</button>`}</td></tr>`}).join("");
  const e=$("#empty");e.classList.toggle("hide",list.length>0);
  e.textContent=users.length>1?"No users match your search. Clear the filters to see everyone.":"No other accounts yet. Register one from the login page to manage it here.";
}
$("#q").oninput=drawUsers;$("#rf").onchange=drawUsers;$("#refresh").onclick=async()=>{await loadUsers();toast("User list refreshed")};
$("#rows").onclick=async e=>{
  const t=e.target.closest("button");if(!t)return;let r,ok;
  if(t.dataset.role){r=await api(`/admin/users/${t.dataset.role}/role`,{method:"PATCH",headers:{"Content-Type":"application/json"},body:JSON.stringify({role:t.dataset.next})});ok=`@${t.dataset.role} is now ${t.dataset.next}`}
  else if(t.dataset.del){if(!await confirmBox("Delete user?",`@${t.dataset.del} will be removed permanently and can no longer log in.`))return;r=await api(`/admin/users/${t.dataset.del}`,{method:"DELETE"});ok=`@${t.dataset.del} deleted`}
  else return;
  if(r.ok){toast(ok);await loadUsers();const s=await api("/stats");if(s.ok){$("#sTotal").textContent=s.body.total_users;$("#sAdmin").textContent=s.body.admins}}else toast(errText(r.body&&r.body.detail),"err");
};

boot();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)