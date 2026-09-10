# bodeuro

De officiële munt van waardering — bedacht door twee vrienden voor de
**beste leraar ter wereld**. 1 BDE = €1,00. Altijd.

Dark-themed bank-website (Flask + SQLite) met:

- **Rekening openen**: naam + gebruikersnaam + email + wachtwoord,
  met **email-verificatie** (6-cijferige code)
- **Twee-staps inloggen**: gebruikersnaam + wachtwoord, daarna een
  6-cijferige **code per email**
- **Bodeuro sturen** op de gebruikersnaam van de ontvanger
- **Opwaarderen** (betaalbaar in complimenten) en **kaart blokkeren**
- **Admin-account** (`admin`): oneindig saldo en oneindig sturen —
  alleen voor de admin zelf zichtbaar
- **Demo-modus**: zonder SMTP-instellingen worden codes op het scherm
  getoond, zodat alles getest kan worden zonder echte emails

## Starten

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python app.py
```

En ga naar `http://localhost:8000`.

## Accounts

| Rol | Gebruikersnaam | Wachtwoord |
|---|---|---|
| Proefrekening | `demo` | `bodeuro` |
| Admin | `admin` | willekeurig gegenereerd bij eerste start, staat in `data/admin_password.txt` (niet openbaar, gitignore'd) |

## Echte emails instellen (SMTP)

Zonder instellingen staat de site in **demo-modus** (codes op het
scherm). Voor echte emails bijv. met Gmail:

1. Schakel 2-staps verificatie in op je Google-account
2. Maak een **app-wachtwoord** aan (Google Security → App-wachtwoorden)
3. Maak `data/smtp.json` aan:

```json
{
  "host": "smtp.gmail.com",
  "port": 587,
  "user": "jouw@gmail.com",
  "password": "xxxx xxxx xxxx xxxx",
  "from": "jouw@gmail.com"
}
```

`data/` staat in `.gitignore`, dus je wachtwoord komt nooit op GitHub.
Alternatief: omgevingvariabelen `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`,
`SMTP_PASSWORD`, `MAIL_FROM`.

## Foto's

Zet foto's in [`images/`](images/):

- `founder-1.jpg` — oprichter 1
- `founder-2.jpg` — oprichter 2
- `teacher.jpg` — de beste leraar ter wereld

Zonder foto's worden placeholders getoond.

## Data

Accounts, transacties en codes staan in `data/bodeuro.db` (SQLite,
wordt automatisch aangemaakt, gitignore'd).

> De bodeuro is geen echt geld — wel echt respect.
