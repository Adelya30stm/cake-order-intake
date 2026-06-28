# Cake Order Intake — Heroku deploy

Gmail (Squarespace form submission) → FastAPI on Heroku → OpenAI parses the order
→ creates a card in Notion → sends the customer an auto-reply.

```
app/
  main.py          FastAPI app + run_once() pipeline
  ai_parser.py     OpenAI → CakeOrder JSON
  notion_client.py creates the Notion order card
  gmail_client.py  Gmail OAuth read / send / mark-read
  models.py        CakeOrder model
Procfile           web: uvicorn app.main:app ...
requirements.txt   dependencies
runtime.txt        python-3.12.8
```

## 1. Local test first
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # fill in your secrets
export $(grep -v '^#' .env | xargs)   # load env vars
uvicorn app.main:app --reload
# open http://127.0.0.1:8000/process  (DRY_RUN=true → only logs, sends nothing)
```

## 2. Get the credentials
- **OpenAI:** platform.openai.com → API keys → `OPENAI_API_KEY`.
- **Notion:** notion.so/my-integrations → New integration → copy the secret →
  open your **Orders** database → ••• → Connections → add the integration →
  copy the 32-char `NOTION_DATABASE_ID` from the database URL.
- **Gmail (App Password — no OAuth):**
  1. Turn on 2-Step Verification: https://myaccount.google.com/security
  2. Create an App Password: https://myaccount.google.com/apppasswords
     (Mail → Other) → 16 characters.
  3. Set `GMAIL_ADDRESS` (your inbox) and `GMAIL_APP_PASSWORD`.
  That's the only Gmail setup — nothing to configure inside Gmail beyond this.

## 3. Deploy to Heroku
```bash
heroku login
heroku create merenga-cake-intake
git init && git add . && git commit -m "cake order intake"
heroku git:remote -a merenga-cake-intake

# set config vars
heroku config:set OPENAI_API_KEY=... NOTION_TOKEN=... NOTION_DATABASE_ID=... \
  GMAIL_ADDRESS=you@gmail.com GMAIL_APP_PASSWORD="xxxx xxxx xxxx xxxx" \
  BUSINESS_NAME="merenga cakes" REPLY_MODE=send DRY_RUN=true

git push heroku main           # or: git push heroku master
heroku open                    # health check at /
```

## 4. Run on a schedule
A one-off dyno runs the pipeline directly (no URL/curl needed).
```bash
heroku addons:create scheduler:standard
heroku addons:open scheduler
# Add a job, frequency "every 10 minutes", with this command:
python -c "from app.main import run_once; import json; print(json.dumps(run_once()))"
```
The `web` process (Procfile) is only for the health check and manual testing at
`/process` — the scheduled job above does the real work.

## 5. Go live
1. Keep `DRY_RUN=true`, hit `/process`, check the logs (`heroku logs --tail`).
2. When the parsed orders look right: `heroku config:set DRY_RUN=false`.
3. New customer emails now auto-create Notion cards and send replies.
