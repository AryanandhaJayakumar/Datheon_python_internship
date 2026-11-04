"""
SecureVault - User Authentication & RBAC with JWT
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

# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------
# In production set SECRET_KEY as an environment variable. If it is missing, a
# random key is generated on every start (all old tokens become invalid).
SECRET_KEY = os.getenv("SECRET_KEY", secrets.token_hex(32))
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

app = FastAPI(
    title="SecureVault API",
    description="JWT authentication with bcrypt password hashing and role-based access control.",
    version="1.0.0",
    swagger_ui_parameters={"persistAuthorization": True, "displayRequestDuration": True},
)


# --------------------------------------------------------------------------
# Schemas
# --------------------------------------------------------------------------
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


# --------------------------------------------------------------------------
# In-memory user store (swap for a real database in production)
# --------------------------------------------------------------------------
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


# --------------------------------------------------------------------------
# JWT helpers and dependencies
# --------------------------------------------------------------------------
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


# --------------------------------------------------------------------------
# Auth endpoints
# --------------------------------------------------------------------------
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


# --------------------------------------------------------------------------
# Protected endpoints
# --------------------------------------------------------------------------
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


# --------------------------------------------------------------------------
# Admin-only endpoints (RBAC)
# --------------------------------------------------------------------------
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


# --------------------------------------------------------------------------
# Frontend (served at "/")
# --------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def home():
    return HTML_PAGE


HTML_PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SecureVault - JWT Auth & RBAC</title>
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;700&family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
:root{--bg:#0a1020;--panel:#111a30;--panel2:#16213d;--line:#243252;--ink:#e8eefc;--muted:#8a99bd;
--a1:#22d3ee;--a2:#34d399;--warn:#fbbf24;--bad:#fb7185;--ok:#34d399}
*{box-sizing:border-box;margin:0}
body{font-family:Inter,system-ui,sans-serif;background:var(--bg);color:var(--ink);min-height:100vh;
background-image:radial-gradient(900px 500px at 85% -10%,rgba(34,211,238,.14),transparent),radial-gradient(700px 400px at -10% 110%,rgba(52,211,153,.12),transparent)}
h1,h2,h3{font-family:"Space Grotesk",sans-serif;letter-spacing:-.01em}
.top{display:flex;justify-content:space-between;align-items:center;padding:18px 28px;border-bottom:1px solid var(--line);backdrop-filter:blur(8px)}
.brand{display:flex;align-items:center;gap:10px;font-family:"Space Grotesk";font-weight:700;font-size:1.25rem}
.brand i{width:34px;height:34px;border-radius:10px;background:linear-gradient(135deg,var(--a1),var(--a2));display:grid;place-items:center;font-style:normal;color:#04222a}
.top a{color:var(--muted);text-decoration:none;font-size:.9rem;margin-left:16px}.top a:hover{color:var(--a1)}
.wrap{max-width:1150px;margin:0 auto;padding:32px 24px 60px}
.card{background:linear-gradient(180deg,var(--panel),var(--panel2));border:1px solid var(--line);border-radius:18px;padding:24px}
.hide{display:none!important}
/* auth */
.auth{display:grid;grid-template-columns:1.1fr 1fr;gap:40px;align-items:center;min-height:70vh}
.pitch h1{font-size:clamp(2rem,4.5vw,3.3rem);line-height:1.05}
.pitch h1 span{background:linear-gradient(90deg,var(--a1),var(--a2));-webkit-background-clip:text;background-clip:text;color:transparent}
.pitch p{color:var(--muted);margin:16px 0 22px;line-height:1.65;max-width:460px}
.chips{display:flex;flex-wrap:wrap;gap:8px}
.chip{font-size:.78rem;padding:6px 12px;border:1px solid var(--line);border-radius:99px;color:var(--muted);background:rgba(255,255,255,.03)}
.tabs{display:grid;grid-template-columns:1fr 1fr;background:var(--bg);border-radius:12px;padding:4px;margin-bottom:20px}
.tabs button{font:inherit;font-weight:600;background:none;border:0;color:var(--muted);padding:10px;border-radius:9px;cursor:pointer}
.tabs button.on{background:var(--panel2);color:var(--ink);box-shadow:0 0 0 1px var(--line)}
form{display:grid;gap:14px}
label{font-size:.78rem;font-weight:600;color:var(--muted);display:grid;gap:6px}
input{font:inherit;color:var(--ink);background:var(--bg);border:1.5px solid var(--line);border-radius:11px;padding:12px 14px;outline:none;transition:.2s;width:100%}
input:focus{border-color:var(--a1);box-shadow:0 0 0 4px rgba(34,211,238,.14)}
.btn{font:inherit;font-weight:600;border:0;border-radius:11px;padding:12px 18px;cursor:pointer;color:#04222a;background:linear-gradient(135deg,var(--a1),var(--a2));transition:.2s}
.btn:hover{transform:translateY(-2px);box-shadow:0 10px 24px -10px var(--a1)}
.btn.sm{padding:8px 14px;font-size:.85rem}
.btn.ghost{background:transparent;color:var(--ink);border:1.5px solid var(--line)}
.btn.ghost:hover{border-color:var(--a1);color:var(--a1);box-shadow:none}
.btn.danger{background:transparent;color:var(--bad);border:1.5px solid var(--line)}.btn.danger:hover{border-color:var(--bad);box-shadow:none}
.msg{font-size:.85rem;min-height:1.2em}.msg.err{color:var(--bad)}.msg.ok{color:var(--ok)}
.hint{font-size:.8rem;color:var(--muted);text-align:center}.hint a{color:var(--a1);cursor:pointer}
/* dashboard */
.grid{display:grid;grid-template-columns:1fr 1fr;gap:20px}
.span2{grid-column:1/-1}
.row{display:flex;justify-content:space-between;align-items:center;gap:12px}
.profile{display:flex;gap:16px;align-items:center}
.avatar{width:62px;height:62px;border-radius:18px;background:linear-gradient(135deg,var(--a1),var(--a2));display:grid;place-items:center;font-family:"Space Grotesk";font-weight:700;font-size:1.7rem;color:#04222a}
.badge{font-size:.72rem;font-weight:700;text-transform:uppercase;letter-spacing:.08em;padding:4px 10px;border-radius:99px}
.badge.admin{background:rgba(251,191,36,.15);color:var(--warn)}.badge.user{background:rgba(34,211,238,.15);color:var(--a1)}
.kv{display:grid;grid-template-columns:auto 1fr;gap:6px 14px;margin-top:16px;font-size:.9rem}.kv b{color:var(--muted);font-weight:500}
h3{font-size:1.05rem;margin-bottom:12px}
.mono{font-family:"JetBrains Mono",monospace;font-size:.76rem}
.token{word-break:break-all;color:var(--a1);background:var(--bg);padding:12px;border-radius:10px;border:1px solid var(--line);max-height:96px;overflow:auto}
.claims{margin-top:10px;color:var(--muted);white-space:pre-wrap}
.tests{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:12px}
.console{background:#060b18;border:1px solid var(--line);border-radius:12px;padding:14px;min-height:150px;max-height:260px;overflow:auto;white-space:pre-wrap;word-break:break-word}
.s2{color:var(--ok)}.s4{color:var(--bad)}
table{width:100%;border-collapse:collapse;font-size:.9rem}
th{text-align:left;color:var(--muted);font-weight:500;font-size:.78rem;text-transform:uppercase;letter-spacing:.06em;padding:8px 10px}
td{padding:11px 10px;border-top:1px solid var(--line)}
td .btn{margin-right:6px}
.scroll{overflow-x:auto}
@media(max-width:820px){.auth,.grid{grid-template-columns:1fr}}
</style>
</head>
<body>
<div class="top">
  <div class="brand"><i>&#128274;</i>SecureVault</div>
  <div><a href="/docs">Swagger</a><a href="/redoc">ReDoc</a><a id="logout" class="hide" href="#">Log out</a></div>
</div>

<div class="wrap">
  <!-- Logged-out view -->
  <section id="authView" class="auth">
    <div class="pitch">
      <h1>Secure every route with <span>JWT &amp; roles</span>.</h1>
      <p>Register an account, log in to receive a signed token, then watch protected and admin-only endpoints accept or reject your requests.</p>
      <div class="chips"><span class="chip">bcrypt hashing</span><span class="chip">OAuth2 Bearer</span><span class="chip">30 min tokens</span><span class="chip">RBAC</span></div>
    </div>
    <div class="card">
      <div class="tabs"><button id="tabLogin" class="on">Log in</button><button id="tabReg">Register</button></div>
      <form id="loginForm">
        <label>Username<input id="lUser" autocomplete="username" required></label>
        <label>Password<input id="lPass" type="password" autocomplete="current-password" required></label>
        <div class="msg" id="lMsg"></div>
        <button class="btn">Log in</button>
        <div class="hint">Demo admin: <a id="fill">admin / Admin@123</a></div>
      </form>
      <form id="regForm" class="hide">
        <label>Full name<input id="rName" autocomplete="name"></label>
        <label>Username<input id="rUser" autocomplete="username" required minlength="3"></label>
        <label>Password (8+ chars, letters &amp; numbers)<input id="rPass" type="password" autocomplete="new-password" required minlength="8"></label>
        <div class="msg" id="rMsg"></div>
        <button class="btn">Create account</button>
        <div class="hint">New accounts always receive the <b>user</b> role.</div>
      </form>
    </div>
  </section>

  <!-- Logged-in view -->
  <section id="dashView" class="grid hide">
    <div class="card">
      <div class="profile">
        <div class="avatar" id="avatar">?</div>
        <div><h2 id="pName"></h2><div class="hint" style="text-align:left" id="pUser"></div></div>
      </div>
      <div class="kv"><b>Role</b><span><span class="badge" id="pRole"></span></span><b>Member since</b><span id="pSince"></span><b>Token expires</b><span id="pExp"></span></div>
    </div>
    <div class="card">
      <h3>Your JWT</h3>
      <div class="token mono" id="tokenBox"></div>
      <div class="claims mono" id="claims"></div>
    </div>
    <div class="card span2">
      <h3>Endpoint tester</h3>
      <div class="tests">
        <button class="btn sm ghost" data-p="/users/me">GET /users/me</button>
        <button class="btn sm ghost" data-p="/protected/data">GET /protected/data</button>
        <button class="btn sm ghost" data-p="/admin/users">GET /admin/users (admin)</button>
        <button class="btn sm danger" data-p="/users/me" data-anon="1">GET /users/me without token</button>
        <button class="btn sm danger" data-p="/users/me" data-bad="1">GET /users/me with fake token</button>
      </div>
      <div class="console mono" id="console">Click a button to call the API. Try the admin endpoint as a regular user to see a 403.</div>
    </div>
    <div class="card span2 hide" id="adminCard">
      <div class="row"><h3>Admin panel &middot; users</h3><button class="btn sm ghost" id="refresh">Refresh</button></div>
      <div class="scroll"><table><thead><tr><th>User</th><th>Name</th><th>Role</th><th>Actions</th></tr></thead><tbody id="rows"></tbody></table></div>
      <div class="msg" id="aMsg"></div>
    </div>
  </section>
</div>

<script>
const $=s=>document.querySelector(s);
const esc=s=>String(s??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
let token=sessionStorage.getItem("jwt")||null, me=null, tick=null;

function parseJwt(t){try{return JSON.parse(atob(t.split(".")[1].replace(/-/g,"+").replace(/_/g,"/")))}catch(e){return null}}
function errText(d){return Array.isArray(d)?d.map(x=>x.loc.slice(-1)+": "+x.msg).join(" | "):(d||"Something went wrong")}

async function api(path,opt={},withToken=true,fakeToken=null){
  const h={...(opt.headers||{})};
  if(fakeToken)h.Authorization="Bearer "+fakeToken; else if(withToken&&token)h.Authorization="Bearer "+token;
  const r=await fetch(path,{...opt,headers:h});
  let body=null;try{body=r.status===204?null:await r.json()}catch(e){}
  return {ok:r.ok,status:r.status,body};
}

/* tabs */
$("#tabLogin").onclick=()=>{$("#tabLogin").classList.add("on");$("#tabReg").classList.remove("on");$("#loginForm").classList.remove("hide");$("#regForm").classList.add("hide")};
$("#tabReg").onclick=()=>{$("#tabReg").classList.add("on");$("#tabLogin").classList.remove("on");$("#regForm").classList.remove("hide");$("#loginForm").classList.add("hide")};
$("#fill").onclick=()=>{$("#lUser").value="admin";$("#lPass").value="Admin@123"};

/* register */
$("#regForm").addEventListener("submit",async e=>{
  e.preventDefault();const m=$("#rMsg");m.className="msg";m.textContent="";
  const r=await api("/auth/register",{method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({username:$("#rUser").value.trim(),password:$("#rPass").value,full_name:$("#rName").value.trim()||null})},false);
  if(r.ok){m.className="msg ok";m.textContent="Account created. You can log in now.";$("#lUser").value=r.body.username;$("#lPass").value="";setTimeout(()=>$("#tabLogin").click(),900)}
  else{m.className="msg err";m.textContent=errText(r.body.detail)}
});

/* login */
$("#loginForm").addEventListener("submit",async e=>{
  e.preventDefault();const m=$("#lMsg");m.className="msg";m.textContent="";
  const body=new URLSearchParams({username:$("#lUser").value.trim(),password:$("#lPass").value});
  const r=await api("/auth/login",{method:"POST",headers:{"Content-Type":"application/x-www-form-urlencoded"},body},false);
  if(!r.ok){m.className="msg err";m.textContent=errText(r.body.detail);return}
  token=r.body.access_token;sessionStorage.setItem("jwt",token);await boot();
});

/* logout */
$("#logout").onclick=e=>{e.preventDefault();token=null;me=null;sessionStorage.removeItem("jwt");clearInterval(tick);show()};

function show(){
  const on=!!me;
  $("#authView").classList.toggle("hide",on);$("#dashView").classList.toggle("hide",!on);$("#logout").classList.toggle("hide",!on);
}

async function boot(){
  if(!token){show();return}
  const r=await api("/users/me");
  if(!r.ok){token=null;sessionStorage.removeItem("jwt");show();return}
  me=r.body;
  const claims=parseJwt(token)||{};
  $("#avatar").textContent=(me.full_name||me.username)[0].toUpperCase();
  $("#pName").textContent=me.full_name||me.username;$("#pUser").textContent="@"+me.username;
  const b=$("#pRole");b.textContent=me.role;b.className="badge "+me.role;
  $("#pSince").textContent=new Date(me.created_at).toLocaleDateString();
  $("#tokenBox").textContent=token;
  $("#claims").textContent="Decoded payload:\n"+JSON.stringify(claims,null,2);
  clearInterval(tick);
  const upd=()=>{const s=Math.max(0,claims.exp-Math.floor(Date.now()/1000));
    $("#pExp").textContent=s?`${Math.floor(s/60)}m ${s%60}s`:"expired";
    if(!s){clearInterval(tick)}};
  upd();tick=setInterval(upd,1000);
  $("#adminCard").classList.toggle("hide",me.role!=="admin");
  if(me.role==="admin")loadUsers();
  show();
}

/* endpoint tester */
document.querySelectorAll(".tests button").forEach(b=>b.onclick=async()=>{
  const p=b.dataset.p;
  const r=b.dataset.anon?await api(p,{},false):b.dataset.bad?await api(p,{},true,"not.a.valid.token"):await api(p);
  const tag=b.dataset.anon?" (no token)":b.dataset.bad?" (fake token)":"";
  $("#console").innerHTML=`<span class="${r.status<300?"s2":"s4"}">${r.status}</span> GET ${esc(p)}${tag}\n\n${esc(JSON.stringify(r.body,null,2))}`;
  if(r.status===401&&!b.dataset.anon&&!b.dataset.bad)setTimeout(boot,1200);
});

/* admin panel */
async function loadUsers(){
  const r=await api("/admin/users");if(!r.ok)return;
  $("#rows").innerHTML=r.body.map(u=>{
    const self=u.username===me.username;
    const next=u.role==="admin"?"user":"admin";
    return `<tr><td>@${esc(u.username)}</td><td>${esc(u.full_name||"-")}</td>
      <td><span class="badge ${u.role}">${u.role}</span></td>
      <td>${self?'<span class="hint">you</span>':`<button class="btn sm ghost" data-role="${esc(u.username)}" data-next="${next}">Make ${next}</button><button class="btn sm danger" data-del="${esc(u.username)}">Delete</button>`}</td></tr>`;
  }).join("");
}
$("#refresh").onclick=loadUsers;
$("#rows").addEventListener("click",async e=>{
  const t=e.target,m=$("#aMsg");m.className="msg";m.textContent="";
  let r;
  if(t.dataset.role)r=await api(`/admin/users/${t.dataset.role}/role`,{method:"PATCH",headers:{"Content-Type":"application/json"},body:JSON.stringify({role:t.dataset.next})});
  else if(t.dataset.del){if(!confirm("Delete user "+t.dataset.del+"?"))return;r=await api(`/admin/users/${t.dataset.del}`,{method:"DELETE"})}
  else return;
  if(r.ok){m.className="msg ok";m.textContent="Done.";loadUsers()}else{m.className="msg err";m.textContent=errText(r.body&&r.body.detail)}
});

boot();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)