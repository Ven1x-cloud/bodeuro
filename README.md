# bodeuro

De officiële munt van waardering — bedacht door twee vrienden voor de
**beste leraar ter wereld**. 1 BDE = €1,00. Altijd.

## Architectuur

| Laag | Waar | Wat |
|---|---|---|
| **Frontend** | GitHub Pages (map `docs/`) | Statische site (HTML/CSS/JS) — donker bank-thema |
| **Backend** | PythonAnywhere (`app.py`) | Flask + SQLite: API onder `/api/*`, sessies, codes, email |

De frontend praat met de backend via JSON-API + sessiecookies (CORS staat
open voor `*.github.io`). De Flask-app serveert `docs/` ook zelf, zodat de
PythonAnywhere-URL als fallback gewoon werkt (zelfde site, zelfde domein).

## Functies

- **Rekening openen**: naam + gebruikersnaam + email + wachtwoord, met
  **email-verificatie** (6-cijferige code)
- **Twee-staps inloggen**: gebruikersnaam + wachtwoord, daarna code per email
- **Bodeuro sturen** op de gebruikersnaam van de ontvanger
- **Opwaarderen** (betaalbaar in complimenten) en **kaart blokkeren**
- **Admin-account** (`admin`): oneindig saldo, oneindig sturen — alleen voor
  de admin zelf zichtbaar
- **Demo-modus**: zonder SMTP-instellingen worden codes op het scherm getoond

## Starten (lokaal)

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python app.py
```

→ `http://localhost:8000` (serveert frontend + API).

## Accounts

| Rol | Gebruikersnaam | Wachtwoord |
|---|---|---|
| Proefrekening | `demo` | `bodeuro` |
| Admin | `admin` | willekeurig gegenereerd bij eerste start → `data/admin_password.txt` (gitignore'd) |

## Deploy

**PythonAnywhere (backend):** code kopiëren naar de webapp-map, `flask` in
de venv, wsgi-punt naar `app`, reload. Zie de sessiegeschiedenis voor de
exacte commando's.

**GitHub Pages (frontend):** repo → Settings → Pages → `main` branch,
map `/docs`.

## Echte emails instellen (SMTP)

Zonder instellingen staat de site in **demo-modus** (codes op het scherm).
Voor echte emails bijv. met Gmail:

1. 2-staps verificatie in op je Google-account
2. **App-wachtwoord** aanmaken
3. `data/smtp.json` op PythonAnywhere aanmaken:

```json
{
  "host": "smtp.gmail.com",
  "port": 587,
  "user": "jouw@gmail.com",
  "password": "xxxx xxxx xxxx xxxx",
  "from": "jouw@gmail.com"
}
```

## Foto's

Zet foto's in [`docs/images/`](docs/images/): `founder-1.jpg`,
`founder-2.jpg`, `teacher.jpg`. Zonder foto's worden placeholders getoond.

> De bodeuro is geen echt geld — wel echt respect.
