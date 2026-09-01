# Flutter Job Radar

Flutter remote-job radar: **Brave Search API** (no Google scraping), **Remotive + RemoteOK** JSON feeds, **SQLite** dedupe, keyword scoring, and a **Telegram** digest.

LinkedIn native job alerts are the **fast lane** for LinkedIn Easy Apply. This radar is the **ATS / index lane**: it sees a listing when Brave crawls it or when an aggregator publishes it — often days after LinkedIn itself.

## What it does

1. Runs 7 Brave `site:` queries (LinkedIn + Lever + Greenhouse + Ashby + Workable)
2. Also pulls Flutter jobs from [Remotive](https://remotive.com/api/remote-jobs?search=flutter) and [RemoteOK](https://remoteok.com/api)
3. First run uses `freshness=pm` (last 31 days) and **seeds quietly** (no flood)
4. Later runs use `freshness=pd` (last 24 hours) by default and notify **only new** GREEN/YELLOW matches whose listing age is **≤ 3 days**
5. Older hits are stored but counted as `late_indexed` (not Telegram “new”) — this is how a 2-week-old LinkedIn post stops looking like a fresh lead
6. Writes `output.html` and sends a Telegram digest with links + snippets

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
3. Actions → **Flutter Job Radar** → Run workflow, or wait for cron at **06:00 / 12:00 / 18:00 UTC** (09:00 / 15:00 / 21:00 TR)

Scheduled runs force `--freshness pd`. Manual `workflow_dispatch` can still pass `auto` / `pw` / `pm`.

`jobs.db` persists across runs via the `jobs-db` artifact.

Brave budget: 3 runs × 7 queries ≈ 630 searches/month, inside the usual $5 free credit.

## Scoring (no LLM)

**Positive:** Flutter in title (+5), worldwide/anywhere (+4), EMEA (+4), Turkey (+3), contractor/B2B (+3), remote (+2), senior/lead/mobile (+2)

**Negative:** US-only (−10), EU-only (−8), onsite (−8), junior/intern (−5)

**Buckets**

- **GREEN** — Worldwide / Anywhere / Turkey / EMEA contractor signals
- **YELLOW** — remote-ish but Turkey eligibility unclear
- **RED** — US-only / EU-only / onsite / local employment (not notified)

Telegram header includes `new=X · late_indexed=Y · freshness=pd`. Each row still shows source + age (`linkedin.com · 2 days ago`).

## Layout

```text
main.py              orchestrator
brave_client.py      Brave Web Search client
aggregators.py       Remotive + RemoteOK
age.py               listing-age parse + 3-day stale gate
queries.py           search templates
scorer.py            keyword score + buckets
store.py             SQLite + URL normalize
notify.py            Telegram digest
render.py            output.html
data/jobs.db         runtime DB (gitignored)
.github/workflows/   3× daily cron
```

## Out of scope (later)

Per-company Lever / Greenhouse / Ashby / Workable APIs, LLM eligibility, Playwright / LinkedIn scrape.
