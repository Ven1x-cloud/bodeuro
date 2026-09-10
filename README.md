# bodeuro

De officiële munt van waardering — bedacht door twee vrienden voor de
**beste leraar ter wereld**. 1 BDE = €1,00. Altijd.

Dark-themed bank-website voor de bodeuro (bode + euro in één, zonder
dubbele e). Met echte Python-backend (Flask + SQLite): inloggen,
rekening openen, saldo, transacties, bodeuro sturen en kaart blokkeren.

## Starten

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python app.py
```

En ga naar `http://localhost:8000`.

## Proefrekening

Naam `Demo` · code `bodeuro` — of open een eigen rekening via
"Open een rekening" (je krijgt 100 BDE welkomstbonus).

## Foto's

Zet foto's in [`images/`](images/):

- `founder-1.jpg` — oprichter 1
- `founder-2.jpg` — oprichter 2
- `teacher.jpg` — de beste leraar ter wereld

Zonder foto's worden placeholders getoond.

## Data

Accounts en transacties staan in `data/bodeuro.db` (SQLite, wordt
automatisch aangemaakt, staat in `.gitignore`).

> De bodeuro is geen echt geld — wel echt respect.
