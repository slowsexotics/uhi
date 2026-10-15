#!/usr/bin/env python3
"""
UHI Dashboard Server (v0.5)
Serves on localhost:8080.
Local development preview for creator profiles and optional local AI briefings.
Social connections, cloud inference, Telegram, and scheduling are disabled.
"""

import sys
import os
import re
import json
import sqlite3
import tempfile
import subprocess
import urllib.request
import urllib.error
import secrets
import hmac
from urllib.parse import urlsplit, unquote
from http.cookies import SimpleCookie
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from datetime import datetime, timedelta
import uhi_briefing
from uhi_state import DATA_DIR, owned_file, atomic_json, load_settings, save_settings, keychain_set

PORT = 8080
HOST = "127.0.0.1"

BASE_DIR = Path(__file__).resolve().parent.parent
# UHI-owned state only. Existing Togetherland data is never migrated implicitly.
DB_PATH = DATA_DIR / "uhi_data.db"
HTML_PATH = BASE_DIR / "dashboard" / "index.html"
PROFILE_PATH = DATA_DIR / "uhi_profile.md"
CONFIG_PATH = DATA_DIR / "settings.json"
SETUP_STATE_PATH = DATA_DIR / "setup_state.json"

PLATFORMS_CONFIG = {
    "tiktok": {
        "name": "TikTok",
        "doc_url": "https://developers.tiktok.com/",
        "key_label": "Secret Code",
        "steps": [
            "Open the TikTok for Developers portal using the link below.",
            "Create or select your creator application in the Developer Console.",
            "Under App Management, find and copy your Client Key or OAuth secret code.",
            "Paste your secret code into the box below and click 'Test connection'."
        ]
    },
    "youtube": {
        "name": "YouTube",
        "doc_url": "https://console.cloud.google.com/apis/credentials",
        "key_label": "Secret Code",
        "steps": [
            "Open Google Cloud Console Credentials using the link below.",
            "Select your Google project (or create one) and make sure 'YouTube Data API v3' is enabled.",
            "Click 'Create Credentials' at the top, choose 'API key', and copy the generated secret code.",
            "Paste your secret code into the box below and click 'Test connection'."
        ]
    },
    "instagram": {
        "name": "Instagram",
        "doc_url": "https://developers.facebook.com/apps/",
        "key_label": "Secret Code",
        "steps": [
            "Open Meta for Developers using the link below.",
            "Select your app and ensure your Instagram account is linked as a Professional / Creator account.",
            "In your App Dashboard or developer tools, generate an Access Token with 'instagram_basic' permission.",
            "Paste your secret code into the box below and click 'Test connection'."
        ]
    },
    "facebook": {
        "name": "Facebook",
        "doc_url": "https://developers.facebook.com/apps/",
        "key_label": "Secret Code",
        "steps": [
            "Open Meta for Developers using the link below.",
            "Go to Tools → Access Token Tool in the top navigation.",
            "Select your Facebook Page from the dropdown and request 'pages_read_engagement' permission.",
            "Copy the generated Page Access Token, paste it below, and click 'Test connection'."
        ]
    },
    "x": {
        "name": "X (Twitter)",
        "doc_url": "https://developer.x.com/en/portal/dashboard",
        "key_label": "Secret Code",
        "warning": "Social integration is unavailable in this preview; no subscription is required to try UHI.",
        "steps": [
            "Open the X Developer Portal dashboard using the link below.",
            "Subscribe to the Basic API tier or higher (required by X for analytics).",
            "Navigate to Projects & Apps → Keys and Tokens, then generate your secret code.",
            "Paste your secret code into the box below and click 'Test connection' (or click Skip)."
        ]
    }
}

def get_latest_snapshots():
    owned_file(DB_PATH)
    if not DB_PATH.exists():
        return {}

    try:
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='snapshots';")
        if not cursor.fetchone():
            conn.close()
            return {}

        cursor.execute("""
            SELECT s.id, s.date, s.platform, s.followers, s.views, s.engagement, s.top_post
            FROM snapshots s
            INNER JOIN (
                SELECT platform, MAX(id) AS max_id
                FROM snapshots
                GROUP BY platform
            ) latest ON s.id = latest.max_id
            ORDER BY s.platform ASC
        """)
        rows = cursor.fetchall()
        platforms = {}
        for row in rows:
            p_name = row["platform"]
            platforms[p_name] = {
                "id": row["id"],
                "platform": p_name,
                "date": row["date"],
                "followers": row["followers"],
                "views": row["views"],
                "engagement": row["engagement"],
                "top_post": row["top_post"] or "None"
            }
        conn.close()
        return platforms
    except Exception as e:
        print(f"Error reading database {DB_PATH}: {e}", file=sys.stderr)
        return {}

def get_latest_briefing():
    owned_file(DB_PATH)
    if DB_PATH.exists():
        try:
            conn = sqlite3.connect(str(DB_PATH))
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='briefings';")
            if cursor.fetchone():
                cursor.execute("SELECT * FROM briefings ORDER BY id DESC LIMIT 1;")
                row = cursor.fetchone()
                if row:
                    text = row["content"] if "content" in row.keys() else (row["text"] if "text" in row.keys() else None)
                    b_date = row["created_at"] if "created_at" in row.keys() else (row["date"] if "date" in row.keys() else None)
                    conn.close()
                    if text:
                        return {"available": True, "text": text, "date": b_date}
            conn.close()
        except Exception:
            pass

    return {
        "available": False,
        "text": None,
        "date": None
    }

def get_profile_data():
    profile = uhi_briefing.read_profile()
    if profile is None:
        profile = uhi_briefing.validate_profile({})
    # Compatibility field for the existing profile editor; never read shared Markdown.
    return dict(profile, raw="\n".join(f"## {key}\n{value}" for key,value in profile.items()))

def save_profile_data(data):
    try:
        profile = uhi_briefing.save_profile(data)
        return True, "Creator profile saved.", profile
    except (ValueError, OSError, sqlite3.Error):
        return False, "Profile was not saved. Check the values and UHI storage permissions.", None

def get_accounts_status():
    platforms = ["tiktok", "youtube", "instagram", "facebook", "x"]
    results = {}
    for p in platforms:
        connected = False
        last_sync = None
        cfg = PLATFORMS_CONFIG.get(p, {})
        results[p] = {
            "platform": p,
            "name": cfg.get("name", p.capitalize()),
            "connected": connected,
            "last_sync": last_sync,
            "warning": cfg.get("warning"),
            "doc_url": cfg.get("doc_url", "#"),
            "key_label": cfg.get("key_label", "API Key"),
            "steps": cfg.get("steps", [])
        }

    return results

import threading

LOCAL_AI_SETUP_STATE = {
    "status": "idle",
    "progress": 0,
    "message": "",
    "error": None
}

def check_ollama_binary():
    candidates = [
        "/usr/local/bin/ollama",
        "/opt/homebrew/bin/ollama",
        str(Path.home() / "Applications" / "Ollama.app" / "Contents" / "Resources" / "ollama"),
        "/Applications/Ollama.app/Contents/Resources/ollama",
        str(Path.home() / "UHI" / "bin" / "ollama"),
        str(BASE_DIR / "bin" / "ollama")
    ]
    for c in candidates:
        if os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    import shutil
    return shutil.which("ollama")

def get_local_ai_status():
    try:
        _, model = uhi_briefing.inference_configuration()
        return {"ready":False, "configured":True, "model":model, "status":"configured", "progress":0,
                "message":"Local backend configured. Model availability is checked when generating; no model is started automatically."}
    except uhi_briefing.BriefingError as e:
        return {"ready":False, "configured":False, "status":"configuration_required", "progress":0, "message":str(e)}

def start_local_ai_setup():
    return False, "Model downloads and service startup require separate approval. Nothing was changed."

def get_snapshot_counts():
    owned_file(DB_PATH)
    total = 0
    old = 0
    if DB_PATH.exists():
        try:
            conn = sqlite3.connect(str(DB_PATH))
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='snapshots';")
            if cursor.fetchone():
                cursor.execute("SELECT count(*) FROM snapshots;")
                row = cursor.fetchone()
                total = row[0] if row else 0
                cutoff = (datetime.now() - timedelta(days=30)).isoformat()
                cursor.execute("SELECT count(*) FROM snapshots WHERE date < ?;", (cutoff,))
                row_old = cursor.fetchone()
                old = row_old[0] if row_old else 0
            conn.close()
        except Exception as e:
            print(f"Error checking snapshot counts: {e}", file=sys.stderr)
    return total, old

def clear_old_snapshots():
    owned_file(DB_PATH)
    if not DB_PATH.exists():
        return 0, 0, "Database file does not exist."
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='snapshots';")
        if not cursor.fetchone():
            conn.close()
            return 0, 0, "Snapshots table does not exist."
        cutoff = (datetime.now() - timedelta(days=30)).isoformat()
        cursor.execute("SELECT count(*) FROM snapshots WHERE date < ?;", (cutoff,))
        row = cursor.fetchone()
        count = row[0] if row else 0
        cursor.execute("DELETE FROM snapshots WHERE date < ?;", (cutoff,))
        conn.commit()
        cursor.execute("SELECT count(*) FROM snapshots;")
        rem_row = cursor.fetchone()
        remaining = rem_row[0] if rem_row else 0
        conn.close()
        return count, remaining, f"Cleared {count} snapshot(s) older than 30 days."
    except Exception as e:
        print(f"Error clearing old snapshots: {e}", file=sys.stderr)
        return 0, 0, f"Error clearing snapshots: {e}"

def get_openclaw_cron_info():
    # Compatibility interface: this installation never discovers shared cron jobs.
    return {"found": False, "enabled": False, "next_run_ms": None}

def update_openclaw_cron(time_str, tz=None):
    return False, "Automatic scheduling is not configured for this UHI installation."

def get_system_specs():
    # Generic read-only OS metadata. No private files, commands, or guessed hardware.
    import platform
    return {"arch": platform.machine(), "os_name": platform.system(),
            "os_version": platform.release(), "ram_bytes": None, "ram_gb": None,
            "recommended_model": ""}

def get_onboarding_status():
    settings = get_uhi_settings()
    return {"status": "ok", "onboarded": settings.get("onboarded", False),
            "profile": get_profile_data(), "system_specs": get_system_specs(),
            "model": settings.get("model", "")}

def save_onboarding_data(data):
    try:
        if not isinstance(data, dict): raise ValueError()
        if data.get("api_key"):
            return False, "Cloud inference is not configured. No secret was saved.", {}
        for key in ("name", "niche", "goal", "model"):
            if key in data and not isinstance(data[key], str): raise ValueError()
        model = data.get("model", "").strip()
        if model and not re.fullmatch(r"ollama/[A-Za-z0-9_.:/-]{1,150}", model):
            return False, "This UHI build supports an explicitly configured local assistant. Cloud inference is not connected.", {}
        name = data.get("name", "").strip()
        payload = {"title": f"{name}'s Profile" if name else "My Creator Profile"}
        if "name" in data: payload["identity"] = name
        if "niche" in data: payload["niche"] = data["niche"]
        if "goal" in data: payload["goals"] = data["goal"]
        for key in uhi_briefing.PROFILE_FIELDS:
            if key in data: payload[key] = data[key]
        profile = uhi_briefing.save_profile(payload, {"onboarded":True, "model":model})
        return True, "Creator profile saved. You can generate briefings once local inference is approved.", {
            "onboarded":True, "profile":profile, "model":model}
    except (ValueError, OSError, sqlite3.Error):
        return False, "Setup was not saved. Check the values and UHI storage permissions.", {}

def get_uhi_settings():
    settings = load_settings()
    total, old = get_snapshot_counts()
    return dict(settings, cron_installed=False, cron_type="none",
                cron_detail="Manual briefings; automatic scheduling is not configured.",
                next_run_ms=None, total_snapshots=total, old_snapshots=old)

def save_uhi_settings(updates):
    try:
        save_settings(updates)
        return True, "UHI preferences saved. Automatic scheduling is not configured.", get_uhi_settings()
    except (ValueError, OSError, sqlite3.Error):
        return False, "Could not save UHI preferences. Check the values and storage permissions.", {}

CHECKLIST_ITEMS_META = [
    {
        "id": "connect_platform",
        "order": 1,
        "title": "Connect at least one platform",
        "description": "Social account connections are unavailable in this preview.",
        "icon": "share",
        "target": "tab:connect",
        "action_text": "Connect Account"
    },
    {
        "id": "creator_profile",
        "order": 2,
        "title": "Fill out your creator profile",
        "description": "Tell UHI who you are, what you create, and your growth goals.",
        "icon": "user",
        "target": "tab:profile",
        "action_text": "Edit Profile"
    },
    {
        "id": "briefing_time",
        "order": 3,
        "title": "Set your briefing time",
        "description": "Save a preferred time; automatic scheduling is unavailable.",
        "icon": "clock",
        "target": "tab:settings#setting-item-briefing-time",
        "action_text": "Set Time"
    },
    {
        "id": "ai_model",
        "order": 4,
        "title": "Choose your AI model",
        "description": "Optional explicitly configured local Ollama model; cloud providers are unavailable.",
        "icon": "cpu",
        "target": "tab:settings#setting-item-model",
        "action_text": "Choose AI"
    },
    {
        "id": "telegram",
        "order": 5,
        "title": "Connect Telegram for notifications",
        "description": "Telegram delivery is unavailable in this preview.",
        "icon": "send",
        "target": "tab:settings#setting-item-telegram",
        "action_text": "Setup Telegram"
    },
    {
        "id": "keep_awake",
        "order": 6,
        "title": "Keep your computer awake",
        "description": "Automatic briefings are unavailable; no sleep settings are changed.",
        "icon": "sun",
        "target": "modal:keep_awake",
        "action_text": "Mac Guide"
    },
    {
        "id": "auto_start",
        "order": 7,
        "title": "Turn on auto-start",
        "description": "Automatic startup is unavailable; start this preview manually.",
        "icon": "zap",
        "target": "modal:auto_start",
        "action_text": "Mac Guide"
    }
]

def load_raw_setup_state():
    owned_file(SETUP_STATE_PATH)
    if not SETUP_STATE_PATH.exists():
        return {"version":"1.1", "dismissed":False, "manual_overrides":{}}
    data = json.loads(SETUP_STATE_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, dict): raise ValueError("UHI setup state is corrupted.")
    return data

def save_setup_state_to_disk(state_data):
    atomic_json(SETUP_STATE_PATH, state_data)

def get_setup_state(override_mode=None):
    raw = load_raw_setup_state()
    profile = get_profile_data()
    settings = get_uhi_settings()
    status = {"creator_profile": bool(profile.get("niche") or profile.get("activities")),
              "ai_model": get_local_ai_status().get("configured", False)}
    items = []
    for meta in CHECKLIST_ITEMS_META:
        optional = meta['id'] not in status
        items.append(dict(meta, done=status.get(meta['id'], False), optional=optional,
                          status_text="Optional / not connected" if optional else ("Saved ✓" if status[meta['id']] else "To do")))
    count = sum(status.values())
    return {"version":"1.1", "updated_at":datetime.now().isoformat(), "test_mode":"live",
            "dismissed":bool(raw.get("dismissed",False)), "dismissed_completed_count":raw.get("dismissed_completed_count",0),
            "completed_count":count, "total_count":2, "percent":50*count, "all_done":count==2,
            "items":items, "manual_overrides":{}}

def update_setup_item(item_id, done_status):
    raw = load_raw_setup_state()
    if "manual_overrides" not in raw or not isinstance(raw["manual_overrides"], dict):
        raw["manual_overrides"] = {}
    raw["manual_overrides"][item_id] = bool(done_status)
    save_setup_state_to_disk(raw)
    return get_setup_state()

def set_setup_dismissed(dismissed_bool):
    raw = load_raw_setup_state()
    curr_state = get_setup_state()
    raw["dismissed"] = bool(dismissed_bool)
    if dismissed_bool:
        raw["dismissed_completed_count"] = curr_state["completed_count"]
    save_setup_state_to_disk(raw)
    return get_setup_state()

def set_setup_test_mode(mode_str):
    raw = load_raw_setup_state()
    raw["test_mode"] = mode_str
    save_setup_state_to_disk(raw)
    return get_setup_state()

def get_stored_telegram_token():
    return ""  # Delivery is disabled; never query credentials.

def save_stored_telegram_token(token):
    return keychain_set("telegram-bot", token)

def test_telegram_bot_token(token):
    return False, "Telegram is not configured for isolated UHI. No token was saved or message sent."

def update_config_delivery_target(target_id):
    return False

def find_telegram_chat(token=None):
    return False, "Telegram pairing requires a separately approved isolated delivery integration."

def simulate_telegram_bot_action(action, query=None, state_mode=None):
    return False, "Telegram reply memory is not connected. Use dashboard feedback."

class UhiDashboardHandler(BaseHTTPRequestHandler):
    # Browser session capability, tied to this server process; never persisted/logged.
    def setup(self):
        super().setup()
        if hasattr(self.connection, "settimeout"):
            self.connection.settimeout(15)

    def log_message(self, format, *args):
        pass  # URLs, request bodies and downstream errors can contain secrets.

    def end_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; object-src 'none'; base-uri 'none'")
        super().end_headers()

    def respond_json(self, code, payload):
        body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def allowed_request(self, mutate=False, require_session=True):
        port = self.server.server_address[1]
        allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
        hosts = self.headers.get_all("Host", [])
        if len(hosts) != 1 or hosts[0] not in allowed_hosts:
            self.respond_json(403, {"status":"error", "message":"Invalid dashboard host."})
            return False
        origins = self.headers.get_all("Origin", [])
        if len(origins) > 1 or (origins and origins[0] != "http://" + hosts[0]):
            self.respond_json(403, {"status":"error", "message":"Dashboard origin was rejected."})
            return False
        if self.headers.get("Sec-Fetch-Site", "none") not in ("none", "same-origin"):
            self.respond_json(403, {"status":"error", "message":"Open UHI directly to use the dashboard."})
            return False
        if require_session:
            cookie = SimpleCookie()
            try:
                cookie.load(self.headers.get("Cookie", ""))
                token = cookie['uhi_session'].value if 'uhi_session' in cookie else ''
            except Exception:
                token = ''
            if not hmac.compare_digest(token, self.server.session_token):
                self.respond_json(401, {"status":"error", "message":"Open the UHI dashboard to establish a session."})
                return False
        if mutate:
            csrf = self.headers.get_all("X-UHI-CSRF", [])
            if len(csrf) != 1 or not hmac.compare_digest(csrf[0], self.server.session_token):
                self.respond_json(403, {"status":"error", "message":"Refresh UHI before saving changes."})
                return False
        return True

    def do_OPTIONS(self):
        # No cross-origin API access; no wildcard CORS responses.
        self.respond_json(405, {"status":"error", "message":"Cross-origin requests are not supported."})

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        path = urlsplit(self.path).path
        pages = ("/", "/index.html", "/profile", "/connect", "/settings", "/onboarding")
        if not self.allowed_request(require_session=path not in pages):
            return
        try:
            if path in pages:
                self.serve_html()
            elif path.startswith('/assets/') or path.startswith('/screenshots/'):
                self.serve_asset(path)
            elif path == '/api/creator/briefings':
                self.respond_json(200, {"status":"ok", "briefings":uhi_briefing.history()})
            elif path == '/api/stats':
                self.respond_json(200, {"status":"ok", "platforms":get_latest_snapshots(), "briefing":get_latest_briefing()})
            elif path == '/api/profile':
                self.respond_json(200, {"status":"ok", "profile":get_profile_data()})
            elif path == '/api/accounts':
                self.respond_json(200, {"status":"ok", "accounts":get_accounts_status()})
            elif path == '/api/settings':
                self.respond_json(200, {"status":"ok", "settings":get_uhi_settings()})
            elif path == '/api/onboarding/status':
                self.respond_json(200, get_onboarding_status())
            elif path == '/api/system-specs':
                self.respond_json(200, {"status":"ok", "specs":get_system_specs()})
            elif path == '/api/ai/runtime-status':
                self.respond_json(200, get_local_ai_status())
            elif path == '/api/setup-state':
                self.respond_json(200, {"status":"ok", **get_setup_state()})
            elif path == '/api/telegram/status':
                self.respond_json(200, {"configured":False, "has_token":False, "enabled":False, "target":"", "message":"Telegram delivery and reply memory are not connected."})
            elif path == '/health':
                self.respond_json(200, {"status":"ok"})
            else:
                self.respond_json(404, {"status":"error", "message":"Page not found."})
        except Exception:
            self.respond_json(500, {"status":"error", "message":"UHI could not read its saved state. Check storage or restore your UHI backup."})

    def serve_asset(self, path):
        decoded = unquote(path, errors='strict')
        folder = 'assets' if decoded.startswith('/assets/') else 'screenshots'
        dashboard_root = (BASE_DIR / 'dashboard').resolve()
        root = (dashboard_root / folder).resolve()
        if root.parent != dashboard_root:
            self.respond_json(404, {"status":"error", "message":"Asset not found."})
            return
        candidate = (BASE_DIR / 'dashboard' / decoded.lstrip('/')).resolve()
        types = {'.png':'image/png', '.jpg':'image/jpeg', '.jpeg':'image/jpeg', '.svg':'image/svg+xml', '.css':'text/css', '.js':'text/javascript'}
        if root not in candidate.parents or not candidate.is_file() or candidate.suffix not in types:
            self.respond_json(404, {"status":"error", "message":"Asset not found."})
            return
        body = candidate.read_bytes()
        self.send_response(200)
        self.send_header('Content-Type', types[candidate.suffix])
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        if self.command != 'HEAD': self.wfile.write(body)

    def read_payload(self):
        lengths = self.headers.get_all('Content-Length', [])
        if self.headers.get('Transfer-Encoding') or len(lengths) != 1:
            raise ValueError('A fixed JSON body is required.')
        length = int(lengths[0])
        if length < 0 or length > 65536:
            raise ValueError('Request is too large.')
        if self.headers.get('Content-Type', '').split(';')[0].strip() != 'application/json':
            raise ValueError('Send JSON data.')
        raw = self.rfile.read(length)
        if len(raw) != length: raise ValueError('Incomplete request.')
        data = json.loads(raw)
        if not isinstance(data, dict): raise ValueError('Expected a JSON object.')
        return data

    def do_POST(self):
        if not self.allowed_request(mutate=True): return
        try:
            data = self.read_payload()
        except (ValueError, UnicodeError):
            self.respond_json(400, {"status":"error", "message":"Invalid or oversized JSON request."})
            return
        path = urlsplit(self.path).path
        try:
            if path == '/api/creator/briefings/generate':
                result = uhi_briefing.generate(data.get('request_id'))
                self.respond_json(200, {"status":"ok", "briefing":result})
            elif path == '/api/creator/briefings/feedback':
                result = uhi_briefing.save_feedback(data.get('briefing_id'), data.get('event_id'),
                    data.get('response',''), data.get('feedback',''), data.get('completion_status'))
                self.respond_json(200, {"status":"ok", "briefing":result})
            elif path == '/api/profile':
                ok, message, _ = save_profile_data(data)
                self.respond_json(200 if ok else 500, {"status":"ok" if ok else "error", "message":message, "profile":get_profile_data() if ok else None})
            elif path == '/api/settings':
                ok, message, settings = save_uhi_settings(data)
                self.respond_json(200 if ok else 400, {"status":"ok" if ok else "error", "message":message, "settings":settings})
            elif path == '/api/onboarding/save':
                ok, message, result = save_onboarding_data(data)
                self.respond_json(200 if ok else 400, {"status":"ok" if ok else "error", "message":message, "data":result})
            elif path == '/api/onboarding/reset':
                ok, message, _ = save_uhi_settings({"onboarded":False})
                self.respond_json(200 if ok else 500, {"status":"ok" if ok else "error", "message":message})
            elif path == '/api/setup-state/update':
                if 'dismissed' in data:
                    if type(data['dismissed']) is not bool: raise ValueError()
                    state = set_setup_dismissed(data['dismissed'])
                elif 'item_id' in data:
                    if data['item_id'] not in {i['id'] for i in CHECKLIST_ITEMS_META} or type(data.get('done')) is not bool: raise ValueError()
                    state = update_setup_item(data['item_id'], data['done'])
                else: raise ValueError()
                self.respond_json(200, {"status":"ok", "state":state})
            elif path in ('/api/accounts/test', '/api/telegram/test-bot', '/api/telegram/find-chat', '/api/telegram/simulate', '/api/ai/setup-runtime', '/api/setup-state/test-mode'):
                self.respond_json(409, {"status":"error", "success":False, "message":"This integration is not enabled for isolated UHI. No external action was performed."})
            elif path == '/api/settings/clear-old-snapshots':
                self.respond_json(409, {"status":"error", "message":"Analytics deletion is unavailable in protected development."})
            else:
                self.respond_json(404, {"status":"error", "message":"Action not found."})
        except uhi_briefing.BriefingError as e:
            self.respond_json(409, {"status":"error", "message":str(e)})
        except ValueError:
            self.respond_json(400, {"status":"error", "message":"Check the submitted values."})
        except Exception:
            self.respond_json(500, {"status":"error", "message":"UHI could not save this operation. Check storage permissions and try again."})

    def serve_html(self):
        def safe_json(value):
            return json.dumps(value, ensure_ascii=True).replace('<', r'\u003c').replace('>', r'\u003e').replace('&', r'\u0026')
        content = HTML_PATH.read_text(encoding='utf-8')
        bootstrap = '<script>\n' + '\n'.join([
            'window.INITIAL_SPECS = ' + safe_json(get_system_specs()) + ';',
            'window.INITIAL_ONBOARDING = ' + safe_json(get_onboarding_status()) + ';',
            'window.INITIAL_SETUP_STATE = ' + safe_json(get_setup_state()) + ';',
            'window.UHI_CSRF = ' + safe_json(self.server.session_token) + ';',
            # Existing fetch callers retain their interface; all mutations carry CSRF.
            "const uhiFetch = window.fetch.bind(window); window.fetch = (input, options = {}) => { const url = new URL(typeof input === 'string' ? input : input.url, location.href); if (url.origin === location.origin) { const headers = new Headers(options.headers); headers.set('X-UHI-CSRF', window.UHI_CSRF); options = {...options, headers}; } return uhiFetch(input, options); };"
        ]) + '\n</script>'
        content = content.replace('</head>', bootstrap + '\n</head>', 1).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(content)))
        self.send_header('Set-Cookie', f'uhi_session={self.server.session_token}; HttpOnly; SameSite=Strict; Path=/')
        self.end_headers()
        if self.command != 'HEAD': self.wfile.write(content)


def run():
    httpd = HTTPServer((HOST, PORT), UhiDashboardHandler)
    uhi_briefing.recover_interrupted()
    httpd.session_token = secrets.token_urlsafe(32)
    httpd.timeout = 15
    print(f"UHI Dashboard: http://{HOST}:{PORT}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()

if __name__ == '__main__':
    run()
