# Flutter Job Radar V1

Daily Flutter remote-job radar powered by **Brave Search API** (no Google scraping), **SQLite** dedupe, keyword scoring, and a **Telegram** digest.

## What it does

1. Runs 7 `site:` queries (LinkedIn + Lever + Greenhouse + Ashby + Workable)
2. First run uses `freshness=pm` (last 31 days) and **seeds quietly** (no flood)
3. Later runs use `freshness=pw` (last 7 days) and notify **only new** GREEN/YELLOW matches
4. Scores each result; threshold `score >= 5`
5. Writes `output.html` and sends a Telegram digest with links + snippets

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# fill BRAVE_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
```

### Secrets

| Variable | Where |
|----------|--------|
| `BRAVE_API_KEY` | [Brave Search API](https://brave.com/search/api/) |
| `TELEGRAM_BOT_TOKEN` | [@BotFather](https://t.me/BotFather) |
| `TELEGRAM_CHAT_ID` | Message your bot, then `https://api.telegram.org/bot<TOKEN>/getUpdates` |

## Local run

```bash
# First / dry run without Telegram
python main.py --dry-run

# Normal (auto freshness)
python main.py

# Force daily window
python main.py --freshness pd
```

## GitHub Actions

Workflow: [`.github/workflows/job-radar.yml`](.github/workflows/job-radar.yml)

1. Push this repo to GitHub (prefer **private**)
2. Add repository secrets: `BRAVE_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`
3. Actions → **Flutter Job Radar** → Run workflow (or wait for 07:00 UTC cron)

`jobs.db` persists across runs via the `jobs-db` artifact.

## Scoring (V1, no LLM)

**Positive:** Flutter in title (+5), worldwide/anywhere (+4), EMEA (+4), Turkey (+3), contractor/B2B (+3), remote (+2), senior/lead/mobile (+2)

**Negative:** US-only (−10), EU-only (−8), onsite (−8), junior/intern (−5)

**Buckets**

- **GREEN** — Worldwide / Anywhere / Turkey / EMEA contractor signals
- **YELLOW** — remote-ish but Turkey eligibility unclear
- **RED** — US-only / EU-only / onsite / local employment (not notified)

## Layout

```text
main.py              orchestrator
brave_client.py      Brave Web Search client
queries.py           search templates
scorer.py            keyword score + buckets
store.py             SQLite + URL normalize
notify.py            Telegram digest
render.py            output.html
data/jobs.db         runtime DB (gitignored)
.github/workflows/   daily cron
```

## Out of scope (V2+)

Direct Lever / Greenhouse / Ashby / Workable APIs, LLM eligibility, Playwright.
