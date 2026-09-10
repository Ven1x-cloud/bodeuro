"""bodeuro — de bank van de beste leraar ter wereld.

Flask + SQLite. De superheld is ingespannen: echte login, echte
rekeningaanvraag, echt saldo, echte transacties.
"""
import hashlib
import secrets
import sqlite3
from datetime import datetime
from pathlib import Path

from flask import (Flask, flash, g, redirect, render_template, request,
                   send_from_directory, session, url_for)

BASE = Path(__file__).resolve().parent
DATA = BASE / "data"
DB_PATH = DATA / "bodeuro.db"
SECRET_PATH = DATA / "secret.key"

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
        klas TEXT NOT NULL DEFAULT '',
        salt TEXT NOT NULL,
        code_hash TEXT NOT NULL,
        card_number TEXT NOT NULL,
        klantnr TEXT NOT NULL,
        saldo REAL NOT NULL DEFAULT 0,
        card_blocked INTEGER NOT NULL DEFAULT 0,
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
    """)
    conn.commit()
    n = conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]
    if n == 0:
        # Proefrekening: naam "Demo", code "bodeuro"
        salt = secrets.token_hex(16)
        conn.execute(
            "INSERT INTO accounts (naam, klas, salt, code_hash, card_number, "
            "klantnr, saldo, created_at) VALUES ('Demo', 'Proefklas', ?, ?, "
            "'5301 1480 2026 0001', 'BD-2026-0000', 3482.50, ?)",
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
    conn.close()


# ---------- helpers ----------

def current_user():
    uid = session.get("user_id")
    if uid is None:
        return None
    return db().execute("SELECT * FROM accounts WHERE id = ?", (uid,)).fetchone()


@app.context_processor
def inject_globals():
    return {"user": current_user()}


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
    return render_template("login.html")


@app.post("/inloggen")
def login_post():
    if session.get("user_id"):
        return redirect(url_for("index"))
    naam = request.form.get("naam", "").strip()
    code = request.form.get("code", "")
    row = db().execute(
        "SELECT * FROM accounts WHERE naam = ? COLLATE NOCASE", (naam,)
    ).fetchone()
    if row is not None and row["code_hash"] == hash_code(code, row["salt"]):
        session["user_id"] = row["id"]
        flash(f"👋 Welkom terug, {row['naam']}!", "success")
        return redirect(url_for("index"))
    flash("❌ Deze combinatie kennen we niet. Controleer naam en secrete code.", "error")
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
    klas = request.form.get("klas", "").strip()
    code = request.form.get("code", "")
    motivatie = request.form.get("motivatie", "").strip()[:160]

    if len(naam) < 2:
        flash("❌ Een naam vereist (minimaal 2 letters). Zo heet het bij een bank.", "error")
        return redirect(url_for("account"))
    if len(code) < 4:
        flash("❌ De secrete code moet minimaal 4 tekens zijn. De leraar is streng.", "error")
        return redirect(url_for("account"))
    exists = db().execute(
        "SELECT id FROM accounts WHERE naam = ? COLLATE NOCASE", (naam,)
    ).fetchone()
    if exists:
        flash("❌ Deze naam is al klant. Log in met je secrete code.", "error")
        return redirect(url_for("login"))

    salt = secrets.token_hex(16)
    cur = db().execute(
        "INSERT INTO accounts (naam, klas, salt, code_hash, card_number, klantnr, "
        "saldo, motivatie, created_at) VALUES (?, ?, ?, ?, ?, ?, 100, ?, ?)",
        (naam, klas, salt, hash_code(code, salt), new_card_number(),
         f"BD-2026-{secrets.randbelow(9999):04d}", motivatie, now_iso()),
    )
    db().execute(
        "INSERT INTO transactions (account_id, omschrijving, bedrag, icon, context, "
        "created_at) VALUES (?, 'Rekening geopend — welkomstbonus', 100, '🎁', 'direct', ?)",
        (cur.lastrowid, now_iso()),
    )
    db().commit()
    session["user_id"] = cur.lastrowid
    flash(
        f"🎉 Welkom bij bodeuro, {naam}! Jouw welkomstbonus van 100,00 BDE staat erop. "
        "Je eigen kaartnummer is op de site te zien.",
        "success",
    )
    return redirect(url_for("index"))


@app.post("/sturen")
def sturen():
    u = current_user()
    if u is None:
        flash("Eerst inloggen, dan bodeuro sturen. Zo werkt het.", "error")
        return redirect(url_for("login"))
    if u["card_blocked"]:
        flash("🚫 Je kaart is geblokkeerd — zet hem eerst weer vrij.", "error")
        return redirect(url_for("index"))
    ontvanger = request.form.get("ontvanger", "").strip()
    bedrag = parse_bedrag(request.form.get("bedrag"))
    if not ontvanger:
        flash("Naar wie stuur je eigenlijk?", "error")
        return redirect(url_for("index"))
    if bedrag is None:
        flash("Geen geldig bedrag ingevuld.", "error")
        return redirect(url_for("index"))
    if bedrag > u["saldo"]:
        flash(f"⚠️ Saldo onvoldoende: je hebt {geld(u['saldo'])} BDE. De leraar keurt geen overschrijdingen goed.", "error")
        return redirect(url_for("index"))
    db().execute("UPDATE accounts SET saldo = saldo - ? WHERE id = ?", (bedrag, u["id"]))
    db().execute(
        "INSERT INTO transactions (account_id, omschrijving, bedrag, icon, context, "
        "created_at) VALUES (?, ?, ?, '📤', 'direct', ?)",
        (u["id"], f"Bodeuro gestuurd naar {ontvanger}", -bedrag, now_iso()),
    )
    db().commit()
    flash(f"✅ {geld(bedrag)} BDE gestuurd naar {ontvanger}. De leraar heeft er nota van genomen.", "success")
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
    db().execute("UPDATE accounts SET saldo = saldo + ? WHERE id = ?", (bedrag, u["id"]))
    db().execute(
        "INSERT INTO transactions (account_id, omschrijving, bedrag, icon, context, "
        "created_at) VALUES (?, 'Opwaardering — betaald in complimenten', ?, '💳', 'complimenten', ?)",
        (u["id"], bedrag, now_iso()),
    )
    db().commit()
    flash(f"💳 {geld(bedrag)} BDE opgewaardeerd. De complimenten zijn verrekend.", "success")
    return redirect(url_for("index"))


@app.post("/kaart")
def kaart():
    u = current_user()
    if u is None:
        flash("Eerst inloggen, dan kaartzaken.", "error")
        return redirect(url_for("login"))
    new_state = 0 if u["card_blocked"] else 1
    db().execute("UPDATE accounts SET card_blocked = ? WHERE id = ?", (new_state, u["id"]))
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
# WSGI-server op PythonAnywhere automatisch de proefrekening krijgt.
init_db()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=False)
