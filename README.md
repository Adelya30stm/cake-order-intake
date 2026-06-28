# 🎂 Cake Order Intake Automation

> **Gmail → AI → Notion + Auto-reply**
> Automatically processes customer cake orders from Squarespace forms: reads the email, extracts order details with AI, creates a rich order card in Notion, and sends a warm reply to the customer — all within seconds.

---

## How it works

```
Customer fills out Squarespace form
          ↓
Squarespace sends email → your Gmail inbox
          ↓
Script reads it via IMAP (every 15 min)
          ↓
        ┌─────────────────────────────┐
        ↓                             ↓
 Notion ORDER DETAILS card     Auto-reply to customer
 (Date, Cake Size, Flavor,     (warm, professional,
  Design, Delivery, Notes)      written by AI)
```

---

## Features

- **AI-powered parsing** — GPT-4o-mini reads any free-form order email and extracts structured fields (name, email, phone, cake size, flavor, design, delivery address, budget)
- **Rich Notion cards** — each order becomes a detailed page with `ORDER DETAILS` sections, not just a table row
- **Smart filtering** — only processes real order emails (filtered by sender + keywords), ignores newsletters and marketing
- **Auto-reply** — sends a personalized confirmation to the customer from your bakery email
- **Safe mode** — `DRY_RUN=true` logs everything without sending or writing anything
- **Easy toggle** — `REPLY_MODE=off` to pause auto-replies while still creating Notion cards

---

## Tech stack

| Component | Tool |
|---|---|
| Email reading | Gmail IMAP |
| Email sending | Gmail SMTP (App Password) |
| AI parsing | OpenAI gpt-4o-mini |
| Order storage | Notion API |
| Web server | FastAPI + uvicorn |
| Hosting | Heroku (optional) |

---

## Quick start

### 1. Clone & install

```bash
git clone https://github.com/Adelya30stm/cake-order-intake.git
cd cake-order-intake
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure

```bash
cp .env.example .env
```

Edit `.env` with your credentials:

```env
OPENAI_API_KEY=sk-...
NOTION_TOKEN=ntn_...
NOTION_DATABASE_ID=your-database-id
GMAIL_ADDRESS=your-bakery@gmail.com
GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx
SENDER_FILTER=form-submission@squarespace.info
BUSINESS_NAME=Your Bakery Name
REPLY_MODE=off       # start with off, enable when ready
DRY_RUN=true         # start with true, disable when tested
```

### 3. Set up credentials

**Gmail App Password:**
1. Enable 2-Step Verification: [myaccount.google.com/security](https://myaccount.google.com/security)
2. Create App Password: [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords) → name it anything → copy the 16-char code

**Notion Integration:**
1. Create integration: [notion.so/my-integrations](https://www.notion.so/my-integrations) → New integration
2. Copy the token (`ntn_...`)
3. Open your Notion database → `•••` → Connections → add your integration
4. Copy the database ID from the URL (32 chars after the last `/`)

**OpenAI API Key:**
[platform.openai.com/api-keys](https://platform.openai.com/api-keys)

### 4. Run locally

```bash
# Load env vars
export $(grep -v '^#' .env | xargs)

# Test run (DRY_RUN=true — nothing is sent or written)
python -c "from app.main import run_once; import json; print(json.dumps(run_once(), indent=2))"

# Or start the web server
uvicorn app.main:app --reload
# Visit http://127.0.0.1:8000/process
```

---

## Deploy to Heroku

```bash
heroku login
heroku create your-bakery-intake
heroku git:remote -a your-bakery-intake

# Set environment variables
heroku config:set \
  OPENAI_API_KEY=sk-... \
  NOTION_TOKEN=ntn_... \
  NOTION_DATABASE_ID=... \
  GMAIL_ADDRESS=your-bakery@gmail.com \
  GMAIL_APP_PASSWORD="xxxx xxxx xxxx xxxx" \
  SENDER_FILTER=form-submission@squarespace.info \
  BUSINESS_NAME="Your Bakery" \
  REPLY_MODE=off \
  DRY_RUN=true

git push heroku main

# Add scheduler (runs every 10 min)
heroku addons:create scheduler:standard
heroku addons:open scheduler
# Command: python -c "from app.main import run_once; import json; print(json.dumps(run_once()))"
```

Once tested, go live:
```bash
heroku config:set DRY_RUN=false REPLY_MODE=send
```

---

## Project structure

```
app/
├── main.py           FastAPI app + run_once() pipeline
├── ai_parser.py      OpenAI → structured CakeOrder
├── notion_client.py  Creates rich ORDER DETAILS pages in Notion
├── gmail_client.py   IMAP reader + SMTP sender
└── models.py         CakeOrder Pydantic model
cake_order_autoreply.py   Standalone logic sandbox (no dependencies)
.env.example              Template for all required env vars
Procfile                  Heroku web dyno config
requirements.txt          Python dependencies
```

---

## Environment variables

| Variable | Description | Default |
|---|---|---|
| `OPENAI_API_KEY` | OpenAI API key | required |
| `OPENAI_MODEL` | Model to use | `gpt-4o-mini` |
| `NOTION_TOKEN` | Notion integration token | required |
| `NOTION_DATABASE_ID` | Target Notion database | required |
| `GMAIL_ADDRESS` | Gmail inbox (sender too) | required |
| `GMAIL_APP_PASSWORD` | Gmail App Password | required |
| `SENDER_FILTER` | Only process emails from this address | `form-submission@squarespace.info` |
| `ORDER_KEYWORDS` | Keywords to detect order emails | `cake,order,...` |
| `BUSINESS_NAME` | Shown in auto-reply signature | `My Bakery` |
| `REPLY_MODE` | `send` to reply, `off` to skip | `off` |
| `DRY_RUN` | `true` = log only, nothing sent/written | `true` |
| `MAX_PER_RUN` | Max emails per run (0 = unlimited) | `10` |

---

## License

MIT — use it, fork it, bake something great 🎂
