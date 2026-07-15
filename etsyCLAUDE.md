# CLAUDE.md — 22etsy-agent

## What this project is
9-agent Python pipeline for Etsy embroidery / POD business intelligence.
Owner is a solo operator. Code must be simple, stable, and cheap to run — no clever abstractions.

## Tech stack (do not deviate without asking)
- Python 3.11+, FastAPI, PostgreSQL, SQLAlchemy, APScheduler
- Anthropic SDK for agent LLM calls
- Deployment target: single VPS (Ubuntu). No Docker Swarm/K8s. Keep it one-server simple.
- Config via .env only. Never hardcode keys. Never print or log API keys.

## Hard business rules (never break)
1. NEVER build anything that connects directly to Etsy, Amazon Seller Central,
   eBay, or OTA (Booking/Airbnb/Agoda) accounts to take actions.
   Agents may READ public data and PRODUCE recommendations only.
2. Every output that could become a listing, price change, or message
   must be written to the database / a report for MANUAL review. No auto-publish.
3. External API spend for Trend Hunter must stay under $1/day.
   Prefer free sources first: pytrends, Reddit JSON, Pinterest scraping via Firecrawl.
   Cache aggressively (24h minimum for trend data).

## Agent pipeline conventions
- All agents inherit from BaseAgent (agents/base.py). Follow its interface:
  run() -> AgentResult, never raise uncaught exceptions to the scheduler.
- Each agent writes results to its own table + a shared runs log table.
- Scoring agents must return a 0–100 score plus a one-line verdict
  (Kill / Weak / Test / Strong), matching the Opportunity Scoring agent format.
- Listing outputs must pass the etsy-listing-reviewer skill gates before
  being marked "ready". Amazon outputs use amazon-fbm-listing-reviewer.
- Embroidery design suggestions must follow stitch-safe rules:
  bold shapes, readable text, max ~6 colors, no gradients, no tiny details.

## Code style
- Small files. One agent = one module. No file over ~300 lines without reason.
- Type hints everywhere. Pydantic models for all API and agent I/O.
- SQLAlchemy 2.0 style (select(), session.execute). No raw SQL unless necessary.
- Errors: log with context, store failed runs in DB, never silently pass.
- Tests only for scoring logic and parsers. Don't test boilerplate.

## Token efficiency rules
- Be concise. No preamble, no recap of what you just did.
- Read only the files needed for the task. Never read whole folders.
- Do not re-read files already in context this session.
- For small edits, show the diff only, not the entire file.
- When the task is done, stop. No unsolicited extras or refactors.
- Ask before any action that reads more than 5 files or rewrites more than 2.
- Prefer editing existing files over creating new ones.

## When unsure
Ask one short question instead of guessing. Wrong assumptions about
Etsy/Amazon policy compliance are expensive; questions are cheap.
