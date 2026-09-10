"""bodeuro — de bank van de beste leraar ter wereld.

Flask + SQLite: volledige backend op PythonAnywhere.

- Rekening openen: naam + gebruikersnaam + email + wachtwoord,
  met email-verificatie (6-cijferige code).
- Inloggen: gebruikersnaam + wachtwoord, daarna 6-cijferige code
  per email (2FA). Klopt de code? Ingelogd. Nee? Opnieuw inloggen.
- Bodeuro sturen op de gebruikersnaam van de ontvanger.
- Admin-account: oneindig saldo, oneindig sturen — alleen voor
  de admin zelf zichtbaar.
- Demo-modus: zonder SMTP-instellingen worden codes op het scherm
  getoond (zo kan alles getest worden zonder echte emails).
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

from flask import (Flask, flash, g, redirect, render_template, request,
                   send_from_directory, session, url_for)

BASE = Path(__file__).resolve().parent
DATA = BASE / "data"
DB_PATH = DATA / "bodeuro.db"
SECRET_PATH = DATA / "secret.key"
SMTP_PATH = DATA / "smtp.json"
ADMIN_PW_PATH = DATA / "admin_password.txt"

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
    # Migratie: oude databases zonder de nieuwe kolommen
    cols = [r[1] for r in conn.execute("PRAGMA table_info(accounts)")]
    for col, default in (("username", "''"), ("email", "''"),
                         ("is_admin", "0"), ("verified", "0")):
        if col not in cols:
            conn.execute(f"ALTER TABLE accounts ADD COLUMN {col} {default}")
    conn.commit()

    # Oude accounts (vóór de gebruikersnaam-tijd) een login geven
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
        # Proefrekening: username "demo", wachtwoord "bodeuro"
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

    admin_exists = conn.execute(
        "SELECT id FROM accounts WHERE username = 'admin' COLLATE NOCASE"
    ).fetchone()
    if admin_exists is None:
        # Admin: oneindig saldo (only voor de admin zelf zichtbaar).
        # Het wachtwoord is willekeurig en staat in data/admin_password.txt
        # (dat bestand staat in .gitignore en is dus niet openbaar).
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
        print(f"[bodeuro] admin wachtwoord gegenereerd: {admin_pw} "
              f"(opgeslagen in {ADMIN_PW_PATH})")

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
    """Stuur een email. Zonder SMTP-config → demo-modus (code op scherm)."""
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


@app.context_processor
def inject_globals():
    return {"user": current_user(), "smtp_ready": smtp_ready()}


def geld(x):
    s = f"{float(x):,.2f}"
    return s.replace(",", "§").replace(".", ",").replace("§", ".")


def datum(iso):
    dt = datetime.fromisoformat(iso)
    return f"{dt.day} {MAANDEN[dt.month]} {dt.year}"


def tijd(iso):
    return datetime.fromisoformat(iso).strftime("%H:%M")


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


app.jinja_env.filters["geld"] = geld
app.jinja_env.filters["datum"] = datum
app.jinja_env.filters["tijd"] = tijd


# ---------- routes ----------

@app.get("/")
def index():
    u = current_user()
    txs = []
    if u is not None:
        txs = db().execute(
            "SELECT * FROM transactions WHERE account_id = ? ORDER BY id DESC LIMIT 6",
            (u["id"],),
        ).fetchall()
    return render_template("index.html", txs=txs)


@app.get("/inloggen")
def login():
    if session.get("user_id"):
        return redirect(url_for("index"))
    if session.get("pending_login"):
        demo = session.get("demo_code_login") if not smtp_ready() else None
        return render_template("login.html", step=2, demo_code=demo)
    return render_template("login.html", step=1)


@app.post("/inloggen")
def login_step1():
    if session.get("user_id"):
        return redirect(url_for("index"))
    if is_locked():
        flash("⏳ Te veel pogingen. Even pauze (5 minuten) — de leraar kijkt niet mee, "
              "maar het stelsel wel.", "error")
        return redirect(url_for("login"))
    username = request.form.get("username", "").strip().lower()
    password = request.form.get("password", "")
    row = db().execute(
        "SELECT * FROM accounts WHERE username = ? COLLATE NOCASE", (username,)
    ).fetchone()
    if row is None or row["code_hash"] != hash_code(password, row["salt"]):
        bump_fails()
        flash("❌ Foute gebruikersnaam of wachtwoord.", "error")
        return redirect(url_for("login"))
    if not row["verified"]:
        session["verify_email_hint"] = row["email"]
        flash("Je email is nog niet geverifieerd. Dat kan met één code.", "error")
        return redirect(url_for("verify"))
    if row["is_admin"]:
        # De admin heeft geen email op naam — de 2e stap wordt overgeslagen.
        session["user_id"] = row["id"]
        session.pop("pending_login", None)
        session.pop("login_fails", None)
        flash("👑 Welkom, admin. Oneindig saldo geactiveerd (voor jou alleen zichtbaar).", "success")
        return redirect(url_for("index"))
    issue_code(
        row, "login",
        "Jouw bodeuro inlogcode",
        f"Hi {row['naam']},\n\n"
        f"Jouw 6-cijferige bodeuro inlogcode is: "
        f"{'' if False else 'zie onder'}\n\n"
        f"Deze code werkt {CODE_MINUTES} minuten. Niemand anders mag hem gebruiken.\n\n"
        f"— De bodeuro, de bank van de beste leraar ter wereld",
    )
    session["pending_login"] = row["id"]
    flash("📧 Code verstuurd naar je email. Voer hem in om in te loggen.", "success")
    return redirect(url_for("login"))


@app.post("/inloggen/code")
def login_step2():
    uid = session.pop("pending_login", None)
    code = request.form.get("code", "").strip()
    if uid and check_code(uid, "login", code):
        session["user_id"] = uid
        session.pop("demo_code_login", None)
        session.pop("login_fails", None)
        flash("👋 Je bent ingelogd. Welkom terug bij je bodeuro!", "success")
        return redirect(url_for("index"))
    flash("❌ Die code is niet juist (of verlopen). Log opnieuw in.", "error")
    return redirect(url_for("login"))


@app.get("/uitloggen")
def logout():
    session.clear()
    flash("👋 Tot de volgende les. Je bodeuro slaapt veilig.", "success")
    return redirect(url_for("index"))


@app.get("/rekening-openen")
def account():
    if session.get("user_id"):
        return redirect(url_for("index"))
    return render_template("account.html")


@app.post("/rekening-openen")
def create_account():
    if session.get("user_id"):
        return redirect(url_for("index"))
    naam = request.form.get("naam", "").strip()
    username = request.form.get("username", "").strip().lower()
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    klas = request.form.get("klas", "").strip()
    motivatie = request.form.get("motivatie", "").strip()[:160]

    if len(naam) < 2:
        flash("❌ Een naam vereist (minimaal 2 letters).", "error")
        return redirect(url_for("account"))
    if not USERNAME_RE.match(username):
        flash("❌ Gebruikersnaam: 3 t/m 20 tekens, alleen letters, cijfers en _ (geen spaties).", "error")
        return redirect(url_for("account"))
    if not EMAIL_RE.match(email):
        flash("❌ Dat is geen geldig emailadres.", "error")
        return redirect(url_for("account"))
    if len(password) < 6:
        flash("❌ Het wachtwoord moet minimaal 6 tekens zijn.", "error")
        return redirect(url_for("account"))

    d = db()
    if d.execute("SELECT id FROM accounts WHERE username = ? COLLATE NOCASE",
                 (username,)).fetchone():
        flash("❌ Die gebruikersnaam is al bezet. Kies een andere.", "error")
        return redirect(url_for("account"))
    if d.execute("SELECT id FROM accounts WHERE email = ? COLLATE NOCASE",
                 (email,)).fetchone():
        flash("❌ Dat emailadres is al geregistreerd.", "error")
        return redirect(url_for("account"))

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
        "    {code}\n\n"
        f"Deze code werkt {CODE_MINUTES} minuten.\n\n"
        "— De bodeuro, de bank van de beste leraar ter wereld",
    )
    session["verify_email_hint"] = email
    flash(f"📧 We hebben een 6-cijferige code gestuurd naar {email}.", "success")
    return redirect(url_for("verify"))


@app.get("/verifiëren")
def verify():
    if session.get("user_id"):
        return redirect(url_for("index"))
    demo = session.get("demo_code_verify") if not smtp_ready() else None
    return render_template(
        "verify.html",
        email=session.get("verify_email_hint", ""),
        demo_code=demo,
    )


@app.post("/verifiëren")
def verify_post():
    if session.get("user_id"):
        return redirect(url_for("index"))
    email = request.form.get("email", "").strip().lower()
    code = request.form.get("code", "").strip()
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
        session.pop("verify_email_hint", None)
        session.pop("demo_code_verify", None)
        flash(f"🎉 Email geverifieerd! Welkomstbonus van 100,00 BDE gestort. "
              f"Welkom, {account['naam']}!", "success")
        return redirect(url_for("index"))
    flash("❌ Code niet juist. Check je inbox (spam?) of request een nieuwe code.", "error")
    return redirect(url_for("verify"))


@app.post("/verifiëren/resend")
def verify_resend():
    last = session.get("last_resend", 0)
    if time.time() - last < 60:
        flash("⏳ Even geduld — een code is zojuist verstuurd (per 60 sec max. 1x).", "error")
        return redirect(url_for("verify"))
    email = request.form.get("email", "").strip().lower()
    account = db().execute(
        "SELECT * FROM accounts WHERE email = ? COLLATE NOCASE", (email,)
    ).fetchone()
    if account is None:
        flash("❌ We kennen dat emailadres niet (meer).", "error")
    else:
        session["last_resend"] = time.time()
        issue_code(
            account, "verify",
            "Nieuwe verificatiecode voor de bodeuro",
            "Hier is je nieuwe verificatiecode (de oude is ongeldig):\n\n"
            "    {code}\n\n"
            f"Deze code werkt {CODE_MINUTES} minuten.\n\n"
            "— De bodeuro",
        )
        session["verify_email_hint"] = account["email"]
        flash(f"📧 Nieuwe code verstuurd naar {account['email']}.", "success")
    return redirect(url_for("verify"))


@app.post("/sturen")
def sturen():
    u = current_user()
    if u is None:
        flash("Eerst inloggen, dan bodeuro sturen. Zo werkt het.", "error")
        return redirect(url_for("login"))
    if u["card_blocked"]:
        flash("🚫 Je kaart is geblokkeerd — zet hem eerst weer vrij.", "error")
        return redirect(url_for("index"))
    ontvanger = request.form.get("ontvanger", "").strip().lower()
    bedrag = parse_bedrag(request.form.get("bedrag"))
    if not USERNAME_RE.match(ontvanger):
        flash("❌ Vul de gebruikersnaam van de ontvanger in.", "error")
        return redirect(url_for("index"))
    if bedrag is None:
        flash("❌ Geen geldig bedrag ingevuld.", "error")
        return redirect(url_for("index"))
    r = db().execute(
        "SELECT * FROM accounts WHERE username = ? COLLATE NOCASE", (ontvanger,)
    ).fetchone()
    if r is None:
        flash(f"❌ We kennen geen account met gebruikersnaam “{ontvanger}”.", "error")
        return redirect(url_for("index"))
    if r["id"] == u["id"]:
        flash("Je kunt niet naar jezelf sturen — de leraar telt dat niet als respect.", "error")
        return redirect(url_for("index"))

    d = db()
    if not u["is_admin"]:
        if bedrag > u["saldo"]:
            flash(f"⚠️ Saldo onvoldoende: je hebt {geld(u['saldo'])} BDE. "
                  "De leraar keurt geen overschrijdingen goed.", "error")
            return redirect(url_for("index"))
        d.execute("UPDATE accounts SET saldo = saldo - ? WHERE id = ?",
                  (bedrag, u["id"]))
    # Iedereen (ook de admin) ontvangt gewoon op zijn eigen saldo
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
    flash(f"✅ {geld(bedrag)} BDE gestuurd naar {r['naam']}. "
          "De leraar heeft er nota van genomen.", "success")
    return redirect(url_for("index"))


@app.post("/opwaarderen")
def opwaarderen():
    u = current_user()
    if u is None:
        flash("Eerst inloggen, dan opwaarderen.", "error")
        return redirect(url_for("login"))
    bedrag = parse_bedrag(request.form.get("bedrag"))
    if bedrag is None or bedrag > 1000:
        flash("Kies een bedrag tussen 1 en 1000 BDE (betaalbaar in complimenten).", "error")
        return redirect(url_for("index"))
    d = db()
    d.execute("UPDATE accounts SET saldo = saldo + ? WHERE id = ?", (bedrag, u["id"]))
    d.execute(
        "INSERT INTO transactions (account_id, omschrijving, bedrag, icon, "
        "context, created_at) VALUES (?, 'Opwaardering — betaald in complimenten', "
        "?, '💳', 'complimenten', ?)",
        (u["id"], bedrag, now_iso()),
    )
    d.commit()
    flash(f"💳 {geld(bedrag)} BDE opgewaardeerd. De complimenten zijn verrekend.", "success")
    return redirect(url_for("index"))


@app.post("/kaart")
def kaart():
    u = current_user()
    if u is None:
        flash("Eerst inloggen, dan kaartzaken.", "error")
        return redirect(url_for("login"))
    new_state = 0 if u["card_blocked"] else 1
    db().execute("UPDATE accounts SET card_blocked = ? WHERE id = ?",
                 (new_state, u["id"]))
    db().commit()
    if new_state:
        flash("🚫 Kaart geblokkeerd. De leraar is op de hoogte.", "success")
    else:
        flash("✅ Kaart weer vrij. Je mag betalen in waardering.", "success")
    return redirect(url_for("index"))


# ---------- assets ----------

@app.get("/images/<path:filename>")
def images(filename):
    return send_from_directory(BASE / "images", filename)


# Initialiseer de database bij import (idempotent), zodat ook de
# WSGI-server op PythonAnywhere alles automatisch klaarmaakt.
init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=False)
