#!/usr/bin/env python3
import os, sys, time, threading, traceback, json, base64
from typing import List, Dict, Optional, Tuple
from urllib.parse import quote_plus
import requests

# UI libs
try:
    from colorama import init as colorama_init, Fore, Style
    colorama_init()
except Exception:
    class _C: 
        def __getattr__(self, name): return ""
    Fore = Style = _C()

try:
    from rich.console import Console
    from rich.table import Table
    rich_console = Console()
except Exception:
    rich_console = None

try:
    import questionary
    HAS_QUESTIONARY = True
except Exception:
    HAS_QUESTIONARY = False

# Gateway/HTTP library for user accounts
try:
    import discum
except Exception:
    print("Please install discum: pip install discum")
    raise

# Flask + SocketIO for dashboard
try:
    from flask import Flask, render_template_string, request, redirect, url_for, session, jsonify
    from flask_socketio import SocketIO, emit
except Exception:
    print("Please install Flask and Flask-SocketIO: pip install flask flask-socketio eventlet")
    raise

# Remote bot (discord.py)
try:
    import discord
    from discord.ext import commands
except Exception:
    print("discord.py not available; remote bot will be disabled unless installed.")
    discord = None
    commands = None

# ---------- Config ----------
TOKENS_FILE = "token.txt"
API_BASE = "https://discord.com/api/v10"
DEFAULT_STATUS = "Coder X & Hacker X On Top"
HTTP_TIMEOUT = 12
START_DELAY = 0.28

# Dashboard auth defaults (you can change)
DASH_USER = os.getenv("HX_DASH_USER", "Admin X")
DASH_PASS = os.getenv("HX_DASH_PASS", "hackerxontop")
HX_SECRET = os.getenv("HX_SECRET", "CoderX-HackerX-On-Top")
DASH_PORT = int(os.getenv("HX_PORT", "5000"))

# Remote bot config (set REMOTE_BOT_TOKEN env var)
REMOTE_BOT_TOKEN = os.getenv("REMOTE_BOT_TOKEN", None)
AUTHORIZED_CHANNELS = [int(x) for x in os.getenv("AUTHORIZED_CHANNELS","0").split(",") if x.strip().isdigit()]
BOT_COMMAND_PREFIX = "!"

# ---------- Helpers ----------
def now(): return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
def mask_token(t): return t[:6]+"..."+t[-4:] if t and len(t)>12 else t

def read_tokens(file_path=TOKENS_FILE) -> List[str]:
    if not os.path.exists(file_path):
        return []
    out=[]
    with open(file_path,"r",encoding="utf-8") as f:
        for ln in f:
            s=ln.strip()
            if not s or s.startswith("#"): continue
            out.append(s)
    return out

def http_get(url:str, token:str, **kw):
    headers={"Authorization": token,"User-Agent":"Mozilla/5.0"}
    return requests.get(url, headers=headers, timeout=HTTP_TIMEOUT, **kw)

def http_post(url:str, token:str, json_data=None, **kw):
    headers={"Authorization": token,"User-Agent":"Mozilla/5.0","Content-Type":"application/json"}
    return requests.post(url, headers=headers, json=json_data, timeout=HTTP_TIMEOUT, **kw)

def http_patch(url:str, token:str, json_data=None, **kw):
    headers={"Authorization": token,"User-Agent":"Mozilla/5.0","Content-Type":"application/json"}
    return requests.patch(url, headers=headers, json=json_data, timeout=HTTP_TIMEOUT, **kw)

def http_delete(url:str, token:str, **kw):
    headers={"Authorization": token,"User-Agent":"Mozilla/5.0"}
    return requests.delete(url, headers=headers, timeout=HTTP_TIMEOUT, **kw)

# ---------- Account client ----------
class AccountClient:
    def __init__(self, token:str, index:int, status_text: str = DEFAULT_STATUS):
        self.token=token
        self.index=index
        self.status_text=status_text
        self.client = None
        self.ready=False
        self.username=None
        self.discriminator=None
        self.user_id=None
        self.guilds_cache=[]
        self.current_vc_channel=None
        try:
            self.client = discum.Client(token=self.token, log=False)
            self._register_handlers()
        except Exception as e:
            print(f"[{index}] discum init err: {e}")

    def _register_handlers(self):
        if not self.client: return
        client=self.client
        idx=self.index
        status_text=self.status_text

        def on_ready(resp):
            try:
                sess = client.gateway.session
                user = getattr(sess, "user", None)
                if user:
                    self.username=user.get("username"); self.discriminator=user.get("discriminator"); self.user_id=user.get("id")
                self.ready=True
                print(f"{now()} ✅ [{idx}] Logged in: {self.username}#{self.discriminator}")
                try:
                    payload = {"op":3,"d":{"since":0,"activities":[{"name":status_text,"type":4,"state":status_text}],"status":"online","afk":False}}
                    client.gateway.send(payload)
                except Exception as e:
                    print(f"[{idx}] presence send failed: {e}")
                # notify global
                GlobalState.log_event(f"[{idx}] READY - {self.username}#{self.discriminator}")
            except Exception:
                pass

        def on_close(resp):
            print(f"[{idx}] gateway closed")

        client.gateway.command(on_ready)
        client.gateway.command(on_close)

    def start(self):
        if not self.client:
            return
        def run():
            try:
                self.client.gateway.run(auto_reconnect=True)
            except TypeError:
                self.client.gateway.run()
            except Exception as e:
                print(f"[{self.index}] gateway.run error: {e}")
        threading.Thread(target=run, daemon=True).start()

    def stop(self):
        try:
            if self.client:
                self.client.gateway.close()
        except: pass

    # REST wrappers
    def fetch_self(self):
        try:
            r = http_get(f"{API_BASE}/users/@me", self.token)
            if r.status_code==200:
                d=r.json()
                self.username=d.get("username"); self.discriminator=d.get("discriminator"); self.user_id=d.get("id")
                self.ready=True
                return d
        except: pass
        return None

    def fetch_guilds(self):
        try:
            r=http_get(f"{API_BASE}/users/@me/guilds", self.token)
            if r.status_code==200:
                self.guilds_cache=r.json()
                return self.guilds_cache
        except:
            pass
        return []

    def accept_invite(self, invite):
        code=invite.strip().rstrip("/").split("/")[-1]
        try:
            r=http_post(f"{API_BASE}/invites/{code}", self.token)
            return (r.status_code in (200,201,204), r.text)
        except Exception as e:
            return (False,str(e))

    def leave_guild(self, guild_id):
        try:
            r=http_delete(f"{API_BASE}/users/@me/guilds/{guild_id}", self.token)
            return (r.status_code in (200,204), r.text)
        except Exception as e:
            return (False,str(e))

    def send_message(self, channel_id, message):
        try:
            r=http_post(f"{API_BASE}/channels/{channel_id}/messages", self.token, {"content":message})
            return (r.status_code in (200,201), r.text)
        except Exception as e:
            return (False,str(e))

    def get_channel_info(self, channel_id):
        try:
            r=http_get(f"{API_BASE}/channels/{channel_id}", self.token)
            if r.status_code==200: return r.json()
        except:
            pass
        return None

    def join_vc(self, channel_id, guild_id=None):
        if not guild_id:
            info=self.get_channel_info(channel_id)
            guild_id = info.get("guild_id") if info else None
        if not guild_id: return (False, "guild not found")
        try:
            # Try patch first
            payload={"channel_id":channel_id,"self_mute":False,"self_deaf":False}
            r=http_patch(f"{API_BASE}/guilds/{guild_id}/voice-states/@me", self.token, payload)
            if r.status_code in (200,204):
                self.current_vc_channel=channel_id
                return (True, "joined via PATCH")
        except Exception as e:
            pass
        # fallback to OP 4 via gateway
        try:
            if self.client:
                op4={"op":4,"d":{"guild_id":guild_id,"channel_id":channel_id,"self_mute":False,"self_deaf":False}}
                self.client.gateway.send(op4)
                self.current_vc_channel=channel_id
                return (True, "joined via OP4")
        except Exception as e:
            return (False,str(e))
        return (False,"unknown error")

    def leave_vc(self, guild_id=None):
        if guild_id:
            try:
                r=http_patch(f"{API_BASE}/guilds/{guild_id}/voice-states/@me", self.token, {"channel_id":None})
                if r.status_code in (200,204):
                    self.current_vc_channel=None
                    return (True,"left via PATCH")
            except:
                pass
        # op4 fallback
        try:
            if self.client:
                op4={"op":4,"d":{"guild_id":None,"channel_id":None,"self_mute":False,"self_deaf":False}}
                self.client.gateway.send(op4)
                self.current_vc_channel=None
                return (True,"left via OP4")
        except Exception as e:
            return (False,str(e))
        return (False,"unknown")

    def react_to_message(self, channel_id, message_id, emoji):
        try:
            enc = quote_plus(emoji)
            url=f"{API_BASE}/channels/{channel_id}/messages/{message_id}/reactions/{enc}/@me"
            r = requests.put(url, headers={"Authorization":self.token,"User-Agent":"Mozilla/5.0"}, timeout=HTTP_TIMEOUT)
            return (r.status_code in (200,204), r.text)
        except Exception as e:
            return (False,str(e))

# ---------- Global state & manager ----------
class GlobalState:
    logs = []
    socketio = None
    @classmethod
    def log_event(cls, msg):
        ts = now()
        entry = f"[{ts}] {msg}"
        cls.logs.append(entry)
        # emit via socketio if available
        try:
            if cls.socketio:
                cls.socketio.emit("log", {"line":entry}, broadcast=True)
        except Exception:
            pass
        print(entry)

class MultiManager:
    def __init__(self, tokens:List[str], default_status: str = DEFAULT_STATUS):
        self.tokens = tokens
        self.accounts: Dict[int, AccountClient] = {}
        self.default_status = default_status
        for i, t in enumerate(tokens, start=1):
            acc = AccountClient(t, i, default_status)
            self.accounts[i]=acc
        self.start_all()

    def start_all(self):
        for i,acc in self.accounts.items():
            acc.start()
            time.sleep(START_DELAY)
        # try to fetch self for those not ready
        time.sleep(1)
        for acc in self.accounts.values():
            if not acc.ready:
                acc.fetch_self()

    def stop_all(self):
        for acc in self.accounts.values():
            try: acc.stop()
            except: pass

    def list_tokens(self):
        out=[]
        for i,acc in sorted(self.accounts.items()):
            out.append({"index":i,"username":f"{acc.username}#{acc.discriminator}" if acc.username else None,"id":acc.user_id,"token":mask_token(acc.token)})
        return out

    def list_servers(self, seq:Optional[int]=None):
        res={}
        if seq:
            acc=self.accounts.get(seq)
            if not acc: return {}
            res[seq]=acc.fetch_guilds()
            return res
        for i,acc in self.accounts.items():
            res[i]=acc.fetch_guilds()
        return res

    def join_server(self, invite:str, all_tokens:bool=True):
        ids = self.accounts.keys() if all_tokens else [min(self.accounts.keys())]
        results=[]
        for i in ids:
            acc=self.accounts[i]
            ok,msg=acc.accept_invite(invite)
            results.append((i,ok,msg))
            GlobalState.log_event(f"[{i}] joinserver -> {ok} {msg}")
        return results

    def leave_server(self, guild_id:str, all_tokens:bool=True):
        ids = self.accounts.keys() if all_tokens else [min(self.accounts.keys())]
        results=[]
        for i in ids:
            acc=self.accounts[i]
            ok,msg=acc.leave_guild(guild_id)
            results.append((i,ok,msg))
            GlobalState.log_event(f"[{i}] leaveserver -> {ok} {msg}")
        return results

    def send_message(self, seq:int, channel_id:str, message:str):
        acc=self.accounts.get(seq)
        if not acc: return (False, "invalid token index")
        ok,msg=acc.send_message(channel_id, message)
        GlobalState.log_event(f"[{seq}] message -> {ok} {msg}")
        return (ok,msg)

    def send_message_all(self, channel_id:str, message:str):
        res=[]
        for i,acc in self.accounts.items():
            ok,msg=acc.send_message(channel_id,message)
            res.append((i,ok,msg))
            GlobalState.log_event(f"[{i}] message -> {ok} {msg}")
        return res

    def check_tokens(self):
        report={}
        for i,acc in self.accounts.items():
            try:
                r=http_get(f"{API_BASE}/users/@me", acc.token)
                if r.status_code==200:
                    d=r.json()
                    report[i]={"status":"valid","username":d.get("username"),"id":d.get("id")}
                else:
                    report[i]={"status":"invalid","code":r.status_code,"body":r.text[:400]}
            except Exception as e:
                report[i]={"status":"error","error":str(e)}
        GlobalState.log_event("check_tokens executed")
        return report

    def broadcast_status(self, text:str):
        for i,acc in self.accounts.items():
            try:
                if acc.client:
                    payload={"op":3,"d":{"since":0,"activities":[{"name":text,"type":4,"state":text}],"status":"online","afk":False}}
                    acc.client.gateway.send(payload)
                    GlobalState.log_event(f"[{i}] OP3 status sent")
                else:
                    http_patch(f"{API_BASE}/users/@me/settings", acc.token, {"custom_status":{"text":text}})
                    GlobalState.log_event(f"[{i}] REST status attempted")
            except Exception as e:
                GlobalState.log_event(f"[{i}] status error: {e}")

    def joinvc_all(self, channel_id:str):
        # try to resolve guild via any account
        gid=None
        for acc in self.accounts.values():
            info=acc.get_channel_info(channel_id)
            if info and info.get("guild_id"):
                gid=info.get("guild_id"); break
        out=[]
        for i,acc in self.accounts.items():
            ok,msg=acc.join_vc(channel_id, guild_id=gid)
            out.append((i,ok,msg))
            GlobalState.log_event(f"[{i}] joinvc -> {ok} {msg}")
        return out

    def leavevc_all(self, channel_id:Optional[str]=None):
        gid=None
        if channel_id:
            for acc in self.accounts.values():
                info=acc.get_channel_info(channel_id)
                if info and info.get("guild_id"):
                    gid=info.get("guild_id"); break
        out=[]
        for i,acc in self.accounts.items():
            ok,msg=acc.leave_vc(guild_id=gid)
            out.append((i,ok,msg))
            GlobalState.log_event(f"[{i}] leavevc -> {ok} {msg}")
        return out

    def joinvc_one(self, seq:int, channel_id:str):
        acc=self.accounts.get(seq)
        if not acc: return (False,"invalid index")
        info=acc.get_channel_info(channel_id); gid=info.get("guild_id") if info else None
        ok,msg=acc.join_vc(channel_id, guild_id=gid)
        GlobalState.log_event(f"[{seq}] joinvc_one -> {ok} {msg}")
        return (ok,msg)

    def leavevc_one(self, seq:int, channel_id:Optional[str]=None):
        acc=self.accounts.get(seq)
        if not acc: return (False,"invalid index")
        gid=None
        if channel_id:
            info=acc.get_channel_info(channel_id)
            gid=info.get("guild_id") if info else None
        ok,msg=acc.leave_vc(guild_id=gid)
        GlobalState.log_event(f"[{seq}] leavevc_one -> {ok} {msg}")
        return (ok,msg)

    def listvc(self):
        return {i:acc.current_vc_channel for i,acc in self.accounts.items()}

# ---------- Initialize manager ----------
TOKENS = read_tokens(TOKENS_FILE)
if not TOKENS:
    print("No tokens found in token.txt — create the file and add one token per line.")
    # keep running so dashboard can start but manager empty
manager = MultiManager(TOKENS) if TOKENS else MultiManager([])

# ---------- Flask dashboard with SocketIO ----------
app = Flask(__name__)
app.secret_key = os.getenv("HX_FLASK_SECRET","hackerxsecret")
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")
GlobalState.socketio = socketio

# Basic templates (kept inline for single-file convenience)
LOGIN_PAGE = """
<!doctype html>
<title>Hacker X Login</title>
<style>
body{background:#0b0011;color:#e9d9ff;font-family:Segoe UI,Roboto,Arial;}
.container{max-width:760px;margin:40px auto;padding:20px;border-radius:8px;background:#100016;box-shadow:0 6px 18px rgba(0,0,0,.6);}
input{width:100%;padding:8px;margin:6px 0;border-radius:6px;border:1px solid #31122b;background:#120014;color:#fff}
button{background:#9911ff;color:#fff;padding:8px 12px;border:none;border-radius:6px}
small{color:#cdb3ff}
</style>
<div class="container">
  <h2>Hacker X Dashboard Login</h2>
  <form method="post" action="/login">
    <label>Username</label><input name="username" placeholder="username"/>
    <label>Password</label><input type="password" name="password" placeholder="password"/>
    <div style="margin-top:8px"><button type="submit">Login</button></div>
  </form>
  <hr/>
  <h4>Or use secret token</h4>
  <form method="post" action="/token_login">
    <input name="secret" placeholder="Secret token"/>
    <div style="margin-top:8px"><button type="submit">Use Token</button></div>
  </form>
  <p><small>Default user/pass:  Admin X / hackerxontop — Default secret token: CoderX-HackerX-On-Top </small></p>
</div>
"""

DASH_TEMPLATE = """
<!doctype html>
<html>
<head>
<title>Hacker X Dashboard</title>
<style>
body{background:#070006;color:#f3ddff;font-family:Segoe UI, Roboto, Arial;padding:12px}
.header{display:flex;justify-content:space-between;align-items:center}
.panel{background:#0f0016;padding:12px;border-radius:8px;margin-top:12px}
.token{padding:8px;border-bottom:1px dashed #2b0930}
.btn{background:#9a11ff;color:#fff;padding:6px 10px;border-radius:6px;border:none}
.logbox{background:#020005;color:#d7c6ff;padding:10px;height:280px;overflow:auto;border-radius:6px}
</style>
<script src="//cdnjs.cloudflare.com/ajax/libs/socket.io/4.4.1/socket.io.min.js"></script>
</head>
<body>
<div class="header">
  <h1>Hacker X Dashboard</h1>
  <div><form method="post" action="/logout"><button class="btn">Logout</button></form></div>
</div>

<div class="panel">
  <h3>Tokens</h3>
  <div>
    {% for t in tokens %}
      <div class="token"><strong>{{t.index}}.</strong> {{t.username or '(not ready)'}} — id: {{t.id}} — vc: {{t.in_vc}} </div>
    {% endfor %}
  </div>
</div>

<div class="panel">
  <h3>Actions</h3>
  <form id="cmdform" method="post" action="/action">
    <input name="cmd" placeholder='Command (e.g. joinserver https://discord.gg/codex --all)' style="width:80%;padding:8px;border-radius:6px;border:1px solid #2b0930;background:#100016;color:#fff"/>
    <button class="btn" type="submit">Run</button>
  </form>
</div>

<div class="panel">
  <h3>Live Logs</h3>
  <div id="logs" class="logbox"></div>
</div>

<script>
var socket = io();
socket.on('connect', () => { console.log('ws connected') });
socket.on('log', (data) => {
  var box=document.getElementById('logs');
  box.innerText = data.line + "\\n" + box.innerText;
});
</script>
</body>
</html>
"""

@app.route("/", methods=["GET"])
def index():
    if not session.get("authed"):
        return render_template_string(LOGIN_PAGE)
    tokens = []
    for i,acc in manager.accounts.items():
        tokens.append({"index":i,"username":f"{acc.username}#{acc.discriminator}" if acc.username else None,"id":acc.user_id,"in_vc":acc.current_vc_channel,"ready":acc.ready})
    return render_template_string(DASH_TEMPLATE, tokens=tokens)

@app.route("/login", methods=["POST"])
def login():
    u=request.form.get("username","")
    p=request.form.get("password","")
    if u==DASH_USER and p==DASH_PASS:
        session["authed"]=True
        GlobalState.log_event("Dashboard login success (user/pass)")
        return redirect(url_for("index"))
    return "Invalid creds", 401

@app.route("/token_login", methods=["POST"])
def token_login():
    s=request.form.get("secret","")
    if s==HX_SECRET:
        session["authed"]=True
        GlobalState.log_event("Dashboard login success (secret token)")
        return redirect(url_for("index"))
    return "Invalid token", 401

@app.route("/logout", methods=["POST"])
def logout():
    session.clear(); return redirect(url_for("index"))

@app.route("/action", methods=["POST"])
def action():
    if not session.get("authed"): return "Auth required",401
    cmd = request.form.get("cmd","").strip()
    GlobalState.log_event(f"WEB CMD: {cmd}")
    parts=cmd.split()
    if not parts: return redirect(url_for("index"))
    c=parts[0].lower()
    try:
        if c=="joinserver":
            invite=parts[1]; all_flag="--all" in parts
            manager.join_server(invite, all_tokens=all_flag)
        elif c=="leaveserver":
            gid=parts[1]; manager.leave_server(gid, all_tokens="--all" in parts)
        elif c=="joinvc_all":
            ch=parts[1]; manager.joinvc_all(ch)
        elif c=="leavevc_all":
            ch=parts[1] if len(parts)>1 else None; manager.leavevc_all(ch)
        elif c=="message":
            seq=int(parts[1]); ch=parts[2]; msg=" ".join(parts[3:]); manager.send_message(seq,ch,msg)
        elif c=="message_all":
            ch=parts[1]; msg=" ".join(parts[2:]); manager.send_message_all(ch,msg)
        elif c=="check_tokens":
            report=manager.check_tokens(); return jsonify(report)
        elif c=="status":
            text=" ".join(parts[1:]) if len(parts)>1 else DEFAULT_STATUS; manager.broadcast_status(text)
        else:
            GlobalState.log_event(f"WEB: Unknown command {cmd}")
    except Exception as e:
        GlobalState.log_event(f"WEB ACTION ERR: {e}")
    return redirect(url_for("index"))

# socket events
@socketio.on("connect")
def ws_connect():
    # only allow if session authed? socketio uses cookies; rely on same session
    sid = request.sid
    GlobalState.log_event(f"WS connect {sid}")
    emit("log", {"line": f"[{now()}] Connected to websocket."})

# ---------- Remote control bot ----------
remote_bot_thread = None

def start_remote_bot():
    if not REMOTE_BOT_TOKEN or discord is None:
        GlobalState.log_event("Remote bot disabled (no token or discord.py missing).")
        return

    intents = discord.Intents.default()
    intents.messages = True
    intents.guilds = True

    bot = commands.Bot(command_prefix=BOT_COMMAND_PREFIX, intents=intents)

    @bot.event
    async def on_ready():
        GlobalState.log_event(f"Remote control bot ready as {bot.user}")

    def is_auth_channel(ctx):
        return (not AUTHORIZED_CHANNELS) or (ctx.channel.id in AUTHORIZED_CHANNELS)

    @bot.command(name="run")
    async def run_cmd(ctx, *args):
        if not is_auth_channel(ctx):
            await ctx.reply("Not authorized.")
            return
        cmd = " ".join(args)
        await ctx.reply(f"Executing: `{cmd}`")
        GlobalState.log_event(f"REMOTE CMD: {cmd} from {ctx.author}")
        # simple mapping
        parts = cmd.split()
        if not parts:
            await ctx.reply("No command")
            return
        c=parts[0].lower()
        try:
            if c=="joinserver":
                invite=parts[1]; all_flag="--all" in parts
                manager.join_server(invite, all_tokens=all_flag); await ctx.reply("joinserver executed.")
            elif c=="leaveserver":
                gid=parts[1]; manager.leave_server(gid, all_tokens="--all" in parts); await ctx.reply("leaveserver executed.")
            elif c=="joinvc_all":
                ch=parts[1]; manager.joinvc_all(ch); await ctx.reply("joinvc_all executed.")
            elif c=="leavevc_all":
                ch=parts[1] if len(parts)>1 else None; manager.leavevc_all(ch); await ctx.reply("leavevc_all executed.")
            elif c=="message":
                seq=int(parts[1]); ch=parts[2]; msg=" ".join(parts[3:]); manager.send_message(seq,ch,msg); await ctx.reply("message executed.")
            elif c=="check_tokens":
                report=manager.check_tokens(); await ctx.reply(f"check result: {report}")
            else:
                await ctx.reply("Unknown command")
        except Exception as e:
            await ctx.reply(f"Error: {e}")

    try:
        bot.run(REMOTE_BOT_TOKEN)
    except Exception as e:
        GlobalState.log_event(f"Remote bot run error: {e}")

# run remote bot in separate thread
if REMOTE_BOT_TOKEN:
    remote_bot_thread = threading.Thread(target=start_remote_bot, daemon=True)
    remote_bot_thread.start()

# ---------- CLI (interactive) ----------
def print_banner():
    print(Fore.MAGENTA + "\n" + "="*60 + Style.RESET_ALL)
    print(Fore.MAGENTA + "HACKER X - MULTI DISCORD TOOL".center(60) + Style.RESET_ALL)
    print(Fore.MAGENTA + "Theme: Purple & Red  — Use user tokens at your own risk".center(60) + Style.RESET_ALL)
    print(Fore.MAGENTA + "="*60 + "\n" + Style.RESET_ALL)
    print("Commands:")
    print("Server Commands:")
    print(" listserver <seq|all> | joinserver <invite> [--all] | leaveserver <guild> [--all]")
    print("Vc Commands:")
    print(" listvc | joinvc_all <ch> | leavevc_all [ch] | joinvc <seq> <ch> | leavevc <seq> [ch]")
    print("Message Commands:")
    print(" message <seq> <channel_id> <message> | message_all <channel_id> <message>")
    print("React Commands:")
    print(" react <seq> <channel_id> <mid> <emoji> | react_all <channel_id> <mid> <emoji>")
    print("Nuke Commands:")
    print(" spam <seq> <channel_id> <message> <amount> [delay] | raid <channel_id> <message> <amount> [delay]")
    print("Token Manager Commands:")
    print(" editprofile <seq> <username|-> <about|-> <avatar_url|->")
    print("Info Commands:")
    print(" check_tokens | list | status <text> | help | exit\n")

def cli_loop():
    print_banner()
    while True:
        try:
            raw=input(Fore.GREEN + "tool> " + Style.RESET_ALL).strip()
            if not raw: continue
            parts=raw.split(); cmd=parts[0].lower()
            if cmd=="help":
                print_banner(); continue
            if cmd=="list":
                arr = manager.list_tokens()
                for a in arr:
                    print(f"{a['index']}. {a['username']} id:{a['id']} token:{a['token']}")
                continue
            if cmd=="listserver":
                if len(parts)>=2:
                    if parts[1].lower()=="all":
                        res=manager.list_servers(None)
                        print(res)
                    else:
                        seq=int(parts[1]); print(manager.list_servers(seq))
                else:
                    print("Usage: listserver <seq|all>")
                continue
            if cmd=="joinserver":
                if len(parts)>=2:
                    invite=parts[1]; all_flag="--all" in parts
                    print(manager.join_server(invite, all_tokens=all_flag))
                else:
                    print("Usage: joinserver <invite> [--all]")
                continue
            if cmd=="leaveserver":
                if len(parts)>=2:
                    gid=parts[1]; all_flag="--all" in parts
                    print(manager.leave_server(gid, all_tokens=all_flag))
                else:
                    print("Usage: leaveserver <guild_id> [--all]")
                continue
            if cmd=="listvc":
                print(manager.listvc()); continue
            if cmd=="joinvc_all":
                if len(parts)>=2:
                    print(manager.joinvc_all(parts[1]))
                else:
                    print("Usage: joinvc_all <vc_channel_id>")
                continue
            if cmd=="leavevc_all":
                ch=parts[1] if len(parts)>=2 else None
                print(manager.leavevc_all(ch)); continue
            if cmd=="joinvc":
                if len(parts)>=3:
                    seq=int(parts[1]); ch=parts[2]; print(manager.joinvc_one(seq,ch))
                else:
                    print("Usage: joinvc <seq> <vc_channel_id>")
                continue
            if cmd=="leavevc":
                if len(parts)>=2:
                    seq=int(parts[1]); ch=parts[2] if len(parts)>=3 else None
                    print(manager.leavevc_one(seq,ch))
                else:
                    print("Usage: leavevc <seq> [vc_channel_id]")
                continue
            if cmd=="message":
                if len(parts)>=4:
                    seq=int(parts[1]); ch=parts[2]; msg=" ".join(parts[3:])
                    print(manager.send_message(seq,ch,msg))
                else:
                    print("Usage: message <seq> <channel_id> <message>")
                continue
            if cmd=="message_all":
                if len(parts)>=3:
                    ch=parts[1]; msg=" ".join(parts[2:]); print(manager.send_message_all(ch,msg))
                else:
                    print("Usage: message_all <channel_id> <message>")
                continue
            if cmd=="check_tokens":
                print(manager.check_tokens()); continue
            if cmd=="status":
                text=" ".join(parts[1:]) if len(parts)>1 else DEFAULT_STATUS
                manager.broadcast_status(text); continue
            if cmd=="exit":
                print("Shutting down..."); manager.stop_all(); time.sleep(1); os._exit(0)
            print("Unknown command. Type help.")
        except KeyboardInterrupt:
            print("\nCtrl-C — exiting."); manager.stop_all(); break
        except Exception as e:
            print("CLI Error:",e); traceback.print_exc()

# run CLI in thread so Flask and bot can run
cli_thread = threading.Thread(target=cli_loop, daemon=True)
cli_thread.start()

# ---------- Start Flask + SocketIO server ----------
def run_dashboard():
    GlobalState.log_event(f"Starting dashboard on port {DASH_PORT}")
    socketio.run(app, host="0.0.0.0", port=DASH_PORT)

flask_thread = threading.Thread(target=run_dashboard, daemon=True)
flask_thread.start()

# Keep main thread alive
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("Exiting...")
    manager.stop_all()
    sys.exit(0)