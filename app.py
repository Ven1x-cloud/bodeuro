"""bodeuro — backend (Flask + SQLite) op PythonAnywhere.

Architectuur:
- GitHub Pages serveert de statische frontend (map `docs/`)
- Deze Flask-app is de backend: JSON-API onder /api/*, met sessie
  cookies + CORS zodat de frontend cross-origin mag praten
- Deze app serveert `docs/` óók zelf, zodat de PythonAnywhere-URL
  als fallback gewoon blijft werken (zelfde frontend, zelfde domein)
"""
import hashlib
import json
import os
import re
import secrets
import smtplib
import sqlite3
import time
from datetime import datetime, timedelta
from email.message import EmailMessage
from pathlib import Path

from flask import (Flask, after_this_request, flash, g, jsonify, redirect,
                   request, send_from_directory, session, url_for)
from werkzeug.exceptions import abort

BASE = Path(__file__).resolve().parent
DATA = BASE / "data"
DB_PATH = DATA / "bodeuro.db"
SECRET_PATH = DATA / "secret.key"
SMTP_PATH = DATA / "smtp.json"
ADMIN_PW_PATH = DATA / "admin_password.txt"
FRONTEND_DIR = BASE / "docs"

CODE_MINUTES = 10
USERNAME_RE = re.compile(r"^[a-z0-9_]{3,20}$")
EMAIL_RE = re.compile(r"^[\w.+-]+@[\w-]+\.[\w.-]+$")

app = Flask(__name__)


def load_secret():
    """Stabiele secret: sessies overleven een server-herstart."""
    DATA.mkdir(exist_ok=True)
    if SECRET_PATH.exists():
        return SECRET_PATH.read_text().strip()
    s = secrets.token_hex(32)
    SECRET_PATH.write_text(s)
    return s


app.secret_key = load_secret()

# Cookies mogen cross-site (GitHub Pages -> PythonAnywhere)
app.config.update(
    SESSION_COOKIE_SAMESITE="None",
    SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE", "1") == "1",
    SESSION_COOKIE_HTTPONLY=True,
)

# Wie mag onze API cross-origin oproepen?
ALLOWED_ORIGINS = {
    "https://ven1x-cloud.github.io",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
}
_extra = os.environ.get("CORS_ORIGIN", "")
if _extra.strip():
    ALLOWED_ORIGINS.add(_extra.strip())


@app.after_request
def add_cors(resp):
    origin = request.headers.get("Origin", "")
    if origin in ALLOWED_ORIGINS:
        resp.headers["Access-Control-Allow-Origin"] = origin
        resp.headers["Access-Control-Allow-Credentials"] = "true"
        resp.headers.add("Vary", "Origin")
        if request.method == "OPTIONS":
            resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
            resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return resp


MAANDEN = {1: "jan", 2: "feb", 3: "mrt", 4: "apr", 5: "mei", 6: "jun",
           7: "jul", 8: "aug", 9: "sep", 10: "okt", 11: "nov", 12: "dec"}


# ---------- database ----------

def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def now_iso():
    return datetime.now().isoformat(timespec="seconds")


def hash_code(code, salt):
    return hashlib.pbkdf2_hmac("sha256", code.encode(), salt.encode(), 120_000).hex()


def new_card_number():
    digits = "".join(secrets.choice("0123456789") for _ in range(16))
    return " ".join(digits[i:i + 4] for i in range(0, 16, 4))


def init_db():
    DATA.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS accounts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        naam TEXT NOT NULL,
        username TEXT NOT NULL DEFAULT '',
        email TEXT NOT NULL DEFAULT '',
        klas TEXT NOT NULL DEFAULT '',
        salt TEXT NOT NULL,
        code_hash TEXT NOT NULL,
        card_number TEXT NOT NULL,
        klantnr TEXT NOT NULL,
        saldo REAL NOT NULL DEFAULT 0,
        card_blocked INTEGER NOT NULL DEFAULT 0,
        is_admin INTEGER NOT NULL DEFAULT 0,
        verified INTEGER NOT NULL DEFAULT 0,
        motivatie TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        account_id INTEGER NOT NULL REFERENCES accounts(id),
        omschrijving TEXT NOT NULL,
        bedrag REAL NOT NULL,
        icon TEXT NOT NULL DEFAULT '💸',
        context TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS codes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        account_id INTEGER NOT NULL REFERENCES accounts(id),
        purpose TEXT NOT NULL,
        salt TEXT NOT NULL,
        code_hash TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        used INTEGER NOT NULL DEFAULT 0
    );
    """)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(accounts)")]
    for col, default in (("username", "''"), ("email", "''"),
                         ("is_admin", "0"), ("verified", "0")):
        if col not in cols:
            conn.execute(f"ALTER TABLE accounts ADD COLUMN {col} {default}")
    conn.commit()
    conn.execute(
        "UPDATE accounts SET "
        "username = lower(replace(naam, ' ', '_')), "
        "email = lower(replace(naam, ' ', '_')) || '@bodeuro.nl', "
        "verified = 1 "
        "WHERE username IS NULL OR username = ''"
    )
    conn.commit()

    n = conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]
    if n == 0:
        salt = secrets.token_hex(16)
        conn.execute(
            "INSERT INTO accounts (naam, username, email, klas, salt, code_hash, "
            "card_number, klantnr, saldo, verified, created_at) VALUES "
            "('Demo', 'demo', 'demo@bodeuro.nl', 'Proefklas', ?, ?, "
            "'5301 1480 2026 0001', 'BD-2026-0000', 3482.50, 1, ?)",
            (salt, hash_code("bodeuro", salt), now_iso()),
        )
        demo_tx = [
            ("Einde-periode bonus", 250, "🎓", "klaskring", "2026-09-08T15:04:00"),
            ("Koffie voor de pauze", -3.5, "☕", "automaat", "2026-09-08T10:32:00"),
            ("Huiswerk gecontroleerd", 45, "📝", "batch 1–24", "2026-09-07T14:18:00"),
            ("Klasuitje — betaald door de klas", -120, "🚌", "groepstransactie", "2026-09-05T09:00:00"),
            ("Vraag na de les beantwoord", 10, "💬", "direct", "2026-09-04T12:41:00"),
            ("Rente: 100% dankbaarheid", 84.25, "🏦", "maandelijks", "2026-09-01T00:00:00"),
            ("Rekening geopend — welkomstbonus", 100, "🎁", "", "2026-08-28T09:00:00"),
        ]
        conn.executemany(
            "INSERT INTO transactions (account_id, omschrijving, bedrag, icon, "
            "context, created_at) VALUES (1, ?, ?, ?, ?, ?)",
            demo_tx,
        )
        conn.commit()

    if conn.execute("SELECT id FROM accounts WHERE username = 'admin' COLLATE NOCASE").fetchone() is None:
        admin_pw = "BD-" + "".join(
            secrets.choice("abcdefghjkmnpqrstuvwxyz23456789") for _ in range(12)
        )
        salt = secrets.token_hex(16)
        conn.execute(
            "INSERT INTO accounts (naam, username, email, klas, salt, code_hash, "
            "card_number, klantnr, saldo, is_admin, verified, created_at) VALUES "
            "('Bodeuro Admin', 'admin', 'admin@bodeuro.nl', 'Directie', ?, ?, "
            "'7700 0000 0000 2026', 'BD-ADMIN-∞', 0, 1, 1, ?)",
            (salt, hash_code(admin_pw, salt), now_iso()),
        )
        conn.commit()
        ADMIN_PW_PATH.write_text(admin_pw)
        print(f"[bodeuro] admin wachtwoord gegenereerd: {admin_pw}")

    conn.close()


# ---------- email (SMTP) ----------

def smtp_cfg():
    cfg = {}
    if SMTP_PATH.exists():
        try:
            cfg = json.loads(SMTP_PATH.read_text())
        except json.JSONDecodeError:
            cfg = {}
    return {
        "host": os.environ.get("SMTP_HOST") or cfg.get("host", ""),
        "port": int(os.environ.get("SMTP_PORT") or cfg.get("port", 587)),
        "user": os.environ.get("SMTP_USER") or cfg.get("user", ""),
        "password": os.environ.get("SMTP_PASSWORD") or cfg.get("password", ""),
        "from": (os.environ.get("MAIL_FROM") or cfg.get("from")
                 or os.environ.get("SMTP_USER") or cfg.get("user", "")),
    }


def smtp_ready():
    cfg = smtp_cfg()
    return bool(cfg["host"] and cfg["user"] and cfg["password"])


def send_mail(to, subject, text):
    if not smtp_ready():
        return False, "demo"
    cfg = smtp_cfg()
    msg = EmailMessage()
    msg["From"] = cfg["from"] or cfg["user"]
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(text)
    with smtplib.SMTP(cfg["host"], cfg["port"], timeout=20) as s:
        s.starttls()
        s.login(cfg["user"], cfg["password"])
        s.send_message(msg)
    return True, "ok"


# ---------- codes (6 cijfers) ----------

def issue_code(account, purpose, subject, body_template):
    code = f"{secrets.randbelow(1000000):06d}"
    salt = secrets.token_hex(16)
    exp = (datetime.now() + timedelta(minutes=CODE_MINUTES)).isoformat(timespec="seconds")
    d = db()
    d.execute("UPDATE codes SET used = 1 WHERE account_id = ? AND purpose = ? "
              "AND used = 0", (account["id"], purpose))
    d.execute("INSERT INTO codes (account_id, purpose, salt, code_hash, expires_at) "
              "VALUES (?, ?, ?, ?, ?)",
              (account["id"], purpose, salt, hash_code(code, salt), exp))
    d.commit()
    ok, how = send_mail(account["email"], subject,
                        body_template.replace("{code}", code))
    if how == "demo":
        session[f"demo_code_{purpose}"] = code
    return code, how


def check_code(account_id, purpose, code):
    row = db().execute(
        "SELECT * FROM codes WHERE account_id = ? AND purpose = ? AND used = 0 "
        "ORDER BY id DESC LIMIT 1", (account_id, purpose)
    ).fetchone()
    if row is None:
        return False
    if datetime.fromisoformat(row["expires_at"]) < datetime.now():
        return False
    if row["code_hash"] != hash_code(code, row["salt"]):
        return False
    db().execute("UPDATE codes SET used = 1 WHERE id = ?", (row["id"],))
    db().commit()
    return True


# ---------- helpers ----------

def current_user():
    uid = session.get("user_id")
    if uid is None:
        return None
    return db().execute("SELECT * FROM accounts WHERE id = ?", (uid,)).fetchone()


def geld(x):
    s = f"{float(x):,.2f}"
    return s.replace(",", "§").replace(".", ",").replace("§", ".")


def parse_bedrag(raw):
    try:
        v = round(float(str(raw).replace(",", ".").strip()), 2)
    except (TypeError, ValueError):
        return None
    return v if v > 0 else None


def is_locked():
    return session.get("locked_until", 0) > time.time()


def bump_fails():
    fails = session.get("login_fails", 0) + 1
    session["login_fails"] = fails
    if fails >= 5:
        session["locked_until"] = time.time() + 300
        session["login_fails"] = 0
        return True
    return False


def get_json():
    return request.get_json(silent=True) or {}


def tx_row(t):
    when = f"{datetime.fromisoformat(t['created_at']).day} " \
           f"{MAANDEN[datetime.fromisoformat(t['created_at']).month]} " \
           f"{datetime.fromisoformat(t['created_at']).year} · " \
           f"{t['created_at'][11:16]}"
    if t["context"]:
        when += f" · {t['context']}"
    return {
        "omschrijving": t["omschrijving"],
        "bedrag": t["bedrag"],
        "icon": t["icon"],
        "when": when,
    }


# ---------- API ----------

@app.get("/api/me")
def api_me():
    u = current_user()
    if u is None:
        return jsonify(user=None, txs=[], smtp_ready=smtp_ready())
    txs = [tx_row(t) for t in db().execute(
        "SELECT * FROM transactions WHERE account_id = ? ORDER BY id DESC LIMIT 6",
        (u["id"],)).fetchall()]
    user = {
        "naam": u["naam"],
        "username": u["username"],
        "email": u["email"],
        "klas": u["klas"],
        "is_admin": bool(u["is_admin"]),
        "card_number": u["card_number"],
        "klantnr": u["klantnr"],
        "saldo": u["saldo"],
        "card_blocked": bool(u["card_blocked"]),
    }
    return jsonify(user=user, txs=txs, smtp_ready=smtp_ready())


@app.post("/api/signup")
def api_signup():
    if session.get("user_id"):
        return jsonify(ok=False, error="Je bent al ingelogd."), 409
    d0 = get_json()
    naam = (d0.get("naam") or "").strip()
    username = (d0.get("username") or "").strip().lower()
    email = (d0.get("email") or "").strip().lower()
    password = d0.get("password") or ""
    klas = (d0.get("klas") or "").strip()
    motivatie = (d0.get("motivatie") or "").strip()[:160]

    if len(naam) < 2:
        return jsonify(ok=False, error="Een naam vereist (minimaal 2 letters).")
    if not USERNAME_RE.match(username):
        return jsonify(ok=False, error="Gebruikersnaam: 3 t/m 20 tekens, alleen letters, cijfers en _.")
    if not EMAIL_RE.match(email):
        return jsonify(ok=False, error="Dat is geen geldig emailadres.")
    if len(password) < 6:
        return jsonify(ok=False, error="Het wachtwoord moet minimaal 6 tekens zijn.")

    d = db()
    if d.execute("SELECT id FROM accounts WHERE username = ? COLLATE NOCASE",
                 (username,)).fetchone():
        return jsonify(ok=False, error="Die gebruikersnaam is al bezet.")
    if d.execute("SELECT id FROM accounts WHERE email = ? COLLATE NOCASE",
                 (email,)).fetchone():
        return jsonify(ok=False, error="Dat emailadres is al geregistreerd.")

    salt = secrets.token_hex(16)
    cur = d.execute(
        "INSERT INTO accounts (naam, username, email, klas, salt, code_hash, "
        "card_number, klantnr, saldo, verified, motivatie, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 0, ?, ?)",
        (naam, username, email, klas, salt, hash_code(password, salt),
         new_card_number(), f"BD-2026-{secrets.randbelow(9999):04d}",
         motivatie, now_iso()),
    )
    d.commit()
    issue_code(
        {"id": cur.lastrowid, "email": email, "naam": naam}, "verify",
        "Verifieer je email bij de bodeuro",
        "Welkom bij de bodeuro!\n\n"
        "Voer deze code in om je emailadres te verifiëren:\n\n"
        "{code}\n\n"
        f"Deze code werkt {CODE_MINUTES} minuten.\n\n"
        "— De bodeuro, de bank van de beste leraar ter wereld",
    )
    resp = {"ok": True, "message": f"📧 We stuurden een code naar {email}."}
    if not smtp_ready():
        resp["demo_code"] = session.get("demo_code_verify", "")
    return jsonify(resp), 201


@app.post("/api/verify")
def api_verify():
    if session.get("user_id"):
        return jsonify(ok=False, error="Je bent al ingelogd.")
    d0 = get_json()
    email = (d0.get("email") or "").strip().lower()
    code = (d0.get("code") or "").strip()
    account = db().execute(
        "SELECT * FROM accounts WHERE email = ? COLLATE NOCASE", (email,)
    ).fetchone()
    if account and check_code(account["id"], "verify", code):
        d = db()
        d.execute("UPDATE accounts SET verified = 1 WHERE id = ?", (account["id"],))
        d.execute("UPDATE accounts SET saldo = saldo + 100 WHERE id = ?",
                  (account["id"],))
        d.execute(
            "INSERT INTO transactions (account_id, omschrijving, bedrag, icon, "
            "context, created_at) VALUES (?, 'Rekening geopend — welkomstbonus', "
            "100, '🎁', 'direct', ?)",
            (account["id"], now_iso()),
        )
        d.commit()
        session["user_id"] = account["id"]
        session.pop("demo_code_verify", None)
        return jsonify(ok=True, message=f"🎉 Email geverifieerd! Welkomstbonus van "
                                        f"100,00 BDE gestort. Welkom, {account['naam']}!")
    return jsonify(ok=False, error="Code niet juist. Check je inbox (spam?) of "
                                   "request een nieuwe code.")


@app.post("/api/verify/resend")
def api_verify_resend():
    last = session.get("last_resend", 0)
    if time.time() - last < 60:
        return jsonify(ok=False, error="⏳ Even geduld — max. 1 code per minuut.")
    email = (get_json().get("email") or "").strip().lower()
    account = db().execute(
        "SELECT * FROM accounts WHERE email = ? COLLATE NOCASE", (email,)
    ).fetchone()
    if account is None:
        return jsonify(ok=False, error="We kennen dat emailadres niet (meer).")
    session["last_resend"] = time.time()
    issue_code(
        account, "verify",
        "Nieuwe verificatiecode voor de bodeuro",
        "Hier is je nieuwe verificatiecode (de oude is ongeldig):\n\n"
        "{code}\n\n"
        f"Deze code werkt {CODE_MINUTES} minuten.\n\n"
        "— De bodeuro",
    )
    session["verify_email_hint"] = account["email"]
    resp = {"ok": True, "message": f"📧 Nieuwe code verstuurd naar {account['email']}."}
    if not smtp_ready():
        resp["demo_code"] = session.get("demo_code_verify", "")
    return jsonify(resp)


@app.post("/api/login")
def api_login():
    if session.get("user_id"):
        return jsonify(ok=True, step="done", message="Je bent al ingelogd.")
    if is_locked():
        return jsonify(ok=False, error="⏳ Te veel pogingen. Even pauze (5 minuten).")
    d0 = get_json()
    username = (d0.get("username") or "").strip().lower()
    password = d0.get("password") or ""
    row = db().execute(
        "SELECT * FROM accounts WHERE username = ? COLLATE NOCASE", (username,)
    ).fetchone()
    if row is None or row["code_hash"] != hash_code(password, row["salt"]):
        bump_fails()
        return jsonify(ok=False, error="Foute gebruikersnaam of wachtwoord.")
    if not row["verified"]:
        session["verify_email_hint"] = row["email"]
        return jsonify(ok=False, code="unverified",
                       error="Je email is nog niet geverifieerd.")
    if row["is_admin"]:
        session["user_id"] = row["id"]
        session.pop("pending_login", None)
        session.pop("login_fails", None)
        return jsonify(ok=True, step="done",
                       message="👑 Welkom, admin. Oneindig saldo geactiveerd.")
    issue_code(
        row, "login",
        "Jouw bodeuro inlogcode",
        f"Hi {row['naam']},\n\n"
        "Jouw 6-cijferige bodeuro inlogcode is:\n\n"
        "{code}\n\n"
        f"Deze code werkt {CODE_MINUTES} minuten. Niemand anders mag hem gebruiken.\n\n"
        "— De bodeuro, de bank van de beste leraar ter wereld",
    )
    session["pending_login"] = row["id"]
    resp = {"ok": True, "step": "code",
            "message": "📧 Code verstuurd naar je email."}
    if not smtp_ready():
        resp["demo_code"] = session.get("demo_code_login", "")
    return jsonify(resp)


@app.post("/api/login/code")
def api_login_code():
    uid = session.pop("pending_login", None)
    code = (get_json().get("code") or "").strip()
    if uid and check_code(uid, "login", code):
        session["user_id"] = uid
        session.pop("demo_code_login", None)
        session.pop("login_fails", None)
        return jsonify(ok=True, message="👋 Je bent ingelogd.")
    return jsonify(ok=False, error="Die code is niet juist (of verlopen). Log opnieuw in.")


@app.post("/api/logout")
def api_logout():
    session.clear()
    return jsonify(ok=True, message="👋 Tot de volgende les.")


@app.post("/api/transfer")
def api_transfer():
    u = current_user()
    if u is None:
        return jsonify(ok=False, error="Eerst inloggen, dan bodeuro sturen.")
    if u["card_blocked"]:
        return jsonify(ok=False, error="🚫 Je kaart is geblokkeerd — zet hem eerst weer vrij.")
    d0 = get_json()
    ontvanger = (d0.get("ontvanger") or "").strip().lower()
    bedrag = parse_bedrag(d0.get("bedrag"))
    if not USERNAME_RE.match(ontvanger):
        return jsonify(ok=False, error="Vul de gebruikersnaam van de ontvanger in.")
    if bedrag is None:
        return jsonify(ok=False, error="Geen geldig bedrag ingevuld.")
    r = db().execute(
        "SELECT * FROM accounts WHERE username = ? COLLATE NOCASE", (ontvanger,)
    ).fetchone()
    if r is None:
        return jsonify(ok=False, error=f"We kennen geen account met gebruikersnaam “{ontvanger}”.")
    if r["id"] == u["id"]:
        return jsonify(ok=False, error="Je kunt niet naar jezelf sturen — de leraar "
                                       "telt dat niet als respect.")
    d = db()
    if not u["is_admin"]:
        if bedrag > u["saldo"]:
            return jsonify(ok=False, error=f"⚠️ Saldo onvoldoende: je hebt {geld(u['saldo'])} BDE.")
        d.execute("UPDATE accounts SET saldo = saldo - ? WHERE id = ?",
                  (bedrag, u["id"]))
    d.execute("UPDATE accounts SET saldo = saldo + ? WHERE id = ?",
              (bedrag, r["id"]))
    d.execute(
        "INSERT INTO transactions (account_id, omschrijving, bedrag, icon, "
        "context, created_at) VALUES (?, ?, ?, '📤', ?, ?)",
        (u["id"], f"Bodeuro gestuurd naar {r['naam']}", -bedrag,
         f"naar {r['username']}", now_iso()),
    )
    d.execute(
        "INSERT INTO transactions (account_id, omschrijving, bedrag, icon, "
        "context, created_at) VALUES (?, ?, ?, '📥', ?, ?)",
        (r["id"], f"Ontvangen van {u['naam']}", bedrag,
         f"van {u['username']}", now_iso()),
    )
    d.commit()
    return jsonify(ok=True, message=f"✅ {geld(bedrag)} BDE gestuurd naar {r['naam']}.")


@app.post("/api/topup")
def api_topup():
    u = current_user()
    if u is None:
        return jsonify(ok=False, error="Eerst inloggen, dan opwaarderen.")
    bedrag = parse_bedrag(get_json().get("bedrag"))
    if bedrag is None or bedrag > 1000:
        return jsonify(ok=False, error="Kies een bedrag tussen 1 en 1000 BDE.")
    d = db()
    d.execute("UPDATE accounts SET saldo = saldo + ? WHERE id = ?", (bedrag, u["id"]))
    d.execute(
        "INSERT INTO transactions (account_id, omschrijving, bedrag, icon, "
        "context, created_at) VALUES (?, 'Opwaardering — betaald in complimenten', "
        "?, '💳', 'complimenten', ?)",
        (u["id"], bedrag, now_iso()),
    )
    d.commit()
    return jsonify(ok=True, message=f"💳 {geld(bedrag)} BDE opgewaardeerd.")


@app.post("/api/card")
def api_card():
    u = current_user()
    if u is None:
        return jsonify(ok=False, error="Eerst inloggen, dan kaartzaken.")
    new_state = 0 if u["card_blocked"] else 1
    db().execute("UPDATE accounts SET card_blocked = ? WHERE id = ?",
                 (new_state, u["id"]))
    db().commit()
    return jsonify(
        ok=True,
        blocked=bool(new_state),
        message=("🚫 Kaart geblokkeerd. De leraar is op de hoogte."
                 if new_state else "✅ Kaart weer vrij."),
    )


# ---------- assets + statische frontend ----------

@app.get("/images/<path:filename>")
def images(filename):
    return send_from_directory(FRONTEND_DIR / "images", filename)


if FRONTEND_DIR.exists():
    @app.get("/")
    def index_page():
        return send_from_directory(FRONTEND_DIR, "index.html")

    @app.get("/<path:filename>")
    def frontend_files(filename):
        if filename.startswith("api/"):
            abort(404)
        if (FRONTEND_DIR / filename).is_file():
            return send_from_directory(FRONTEND_DIR, filename)
        return send_from_directory(FRONTEND_DIR, "index.html")


init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=False)
