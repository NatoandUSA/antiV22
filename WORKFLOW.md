# 🧭 The 22Etsy workflow — 12 steps

_This file is generated from `src/workflow_spine.py`, the SAME definition the
home page renders. If the two ever disagree, the module wins — regenerate this
file rather than editing it by hand._

> **The old 9-step V30 flow (FEED → RANK → PATTERN MINER → KEYWORD LAB → RE-RANK
> → BUILD → PHOTO → ADS → LEARN) is DEPRECATED.** It never described the real
> process: Pinterest and supplier feasibility were treated as late optional
> badges instead of early gates, and it named Alura/EverBee for evidence when the
> shop actually runs on HeyEtsy exports.

## Rules

- **One canonical route per step.** The dashboard has 104 routes; only 12 are
  workflow steps. Everything else is a support route (listed at the bottom) and
  is deliberately kept off the main path.
- **Status is read from real data.** A step is only ✅ when its output exists on
  disk. Nothing is assumed.
- **Nothing auto-publishes.** `PUBLISH_AUTOMATION` is `False`; a human lists on
  Etsy manually, always.

## The 12 steps

| # | Step | Route | Owner | Needs | Creates | Next |
|---|---|---|---|---|---|---|
| 1 | **MCP / YTrends keyword feed** | `/trending` | Researcher | Live YTrends index (harvest runs on the PC — the VPS IP is blocked) | keyword_data.csv — the master every later step ranks | → 2 |
| 2 | **Pinterest trend signal** | `/pinterest-trends` | Researcher | Pinterest export or capture for the niche | Demand corroboration badge on matching keywords | → 3 |
| 3 | **Supplier feasibility** | `/suppliers` | Owner | Supplier library (CSV import or saved suppliers) | Can we actually make and ship it, at what cost | → 4 |
| 4 | **Find good keyword / Rank** | `/inbox` | Researcher | keyword_data.csv from step 1 | Final action per keyword: Build now / Confirm first / Watch / Skip | → 5 |
| 5 | **Pattern Miner on real Etsy results** | `/pattern-miner` | Researcher | A keyword from step 4 | Why the current winners rank for this keyword | → 6 |
| 6 | **HeyEtsy evidence** | `/imports` | Researcher | HeyEtsy Detail + Etsy Reviews export (Evidence Exporter extension) | Views · sold · favorites · listing age · shop proof, per listing | → 7 |
| 7 | **Open the best 5 / 10 / 20 listings** | `/imports` | Researcher | Imported evidence from step 6 | The actual Etsy listing pages of the winners | → 8 |
| 8 | **Extract the winning pattern** | `/pattern-miner` | Researcher | Evidence + reviews from step 6 | Title · tags · photos · price · personalization · reviews · buyer angle | → 9 |
| 9 | **Generate new keyword candidates** | `/imports` | Researcher | A dissected winner from step 8 | Keywords from the winner's title, real tags and review language | → 10 |
| 10 | **Send candidates to Re-rank / Inbox** | `/rerank` | Researcher | Candidates from step 9 | Candidates in the master tagged winner:<listing_id>, re-ranked | → 11 |
| 11 | **Build listing / design / photo plan** | `/launch-kit` | Seller | A keyword the engine cleared at step 4 or 10 | Title · 13 tags · description · personalization · photo brief | → 12 |
| 12 | **Assign Team Ops + learn Day 3 / Day 7** | `/team/ops` | Manager | A built listing from step 11 | Owned tasks, then the Day 3 / Day 7 keep-fix-drop-scale call | loop / done |

## Why each step exists

### 1. MCP / YTrends keyword feed
- **Route:** `/trending` · **Owner:** Researcher
- **Needs:** Live YTrends index (harvest runs on the PC — the VPS IP is blocked)
- **Creates:** keyword_data.csv — the master every later step ranks
- **Action:** Harvest keywords
- Raw keyword supply. Nothing downstream can rank what was never pulled.

### 2. Pinterest trend signal
- **Route:** `/pinterest-trends` · **Owner:** Researcher
- **Needs:** Pinterest export or capture for the niche
- **Creates:** Demand corroboration badge on matching keywords
- **Action:** Open Pinterest trends
- Second, independent read on demand before spending time on a niche.

### 3. Supplier feasibility
- **Route:** `/suppliers` · **Owner:** Owner
- **Needs:** Supplier library (CSV import or saved suppliers)
- **Creates:** Can we actually make and ship it, at what cost
- **Action:** Check supplier fit
- A keyword you cannot produce profitably is not an opportunity.

### 4. Find good keyword / Rank
- **Route:** `/inbox` · **Owner:** Researcher
- **Needs:** keyword_data.csv from step 1
- **Creates:** Final action per keyword: Build now / Confirm first / Watch / Skip
- **Action:** Open Opportunity Inbox
- The layered L0–L4 engine decides. Work the top of this list, not a hunch.

### 5. Pattern Miner on real Etsy results
- **Route:** `/pattern-miner` · **Owner:** Researcher
- **Needs:** A keyword from step 4
- **Creates:** Why the current winners rank for this keyword
- **Action:** Mine the pattern
- Read the real SERP before designing anything.

### 6. HeyEtsy evidence
- **Route:** `/imports` · **Owner:** Researcher
- **Needs:** HeyEtsy Detail + Etsy Reviews export (Evidence Exporter extension)
- **Creates:** Views · sold · favorites · listing age · shop proof, per listing
- **Action:** Import evidence
- Third-party estimates, capped at CONFIRM_FIRST — never treated as real Etsy sales.

### 7. Open the best 5 / 10 / 20 listings
- **Route:** `/imports` · **Owner:** Researcher
- **Needs:** Imported evidence from step 6
- **Creates:** The actual Etsy listing pages of the winners
- **Action:** Open winner listings
- Look at the real listings. The evidence card links straight to them.

### 8. Extract the winning pattern
- **Route:** `/pattern-miner` · **Owner:** Researcher
- **Needs:** Evidence + reviews from step 6
- **Creates:** Title · tags · photos · price · personalization · reviews · buyer angle
- **Action:** Read the winning pattern
- Turn a winner into a repeatable recipe instead of a screenshot.

### 9. Generate new keyword candidates
- **Route:** `/imports` · **Owner:** Researcher
- **Needs:** A dissected winner from step 8
- **Creates:** Keywords from the winner's title, real tags and review language
- **Action:** See derived candidates
- New keywords grounded in something that already sells, not guesswork.

### 10. Send candidates to Re-rank / Inbox
- **Route:** `/rerank` · **Owner:** Researcher
- **Needs:** Candidates from step 9
- **Creates:** Candidates in the master tagged winner:<listing_id>, re-ranked
- **Action:** Send to Re-rank / Inbox
- Closes the loop back to step 4. One click — no retyping. Capped at CONFIRM_FIRST; the frozen engine still decides.

### 11. Build listing / design / photo plan
- **Route:** `/launch-kit` · **Owner:** Seller
- **Needs:** A keyword the engine cleared at step 4 or 10
- **Creates:** Title · 13 tags · description · personalization · photo brief
- **Action:** Open Launch Kit
- English-only output. Nothing is ever auto-published.

### 12. Assign Team Ops + learn Day 3 / Day 7
- **Route:** `/team/ops` · **Owner:** Manager
- **Needs:** A built listing from step 11
- **Creates:** Owned tasks, then the Day 3 / Day 7 keep-fix-drop-scale call
- **Action:** Assign and track
- Work only counts once someone owns it and the result is measured.

## The closed loop (steps 8 → 9 → 10 → 4)

This is the loop that used to be open, and the reason the tool felt like it ran
back and forth:

```
  6/7  import a winner  ──►  8  extract the pattern
                                   │  title · real tags · review language
                                   ▼
                             9  candidates generated automatically
                                   │  shown on /imports AND /pattern-miner
                                   ▼
                            10  ONE CLICK: Send to Re-rank / Inbox
                                   │  tagged winner:<listing_id>
                                   ▼
                             4  ranked again by the frozen L0–L4 engine
```

Before V37.7 step 10 did not exist as an action: the candidates were computed
and stored, `candidates_for_rerank()` had no production caller, and staff
**retyped keywords by hand**. Every push is capped at `CONFIRM_FIRST` and is
recorded in `data/imports/rerank_pushes/` with the source listing, the reason
and an evidence summary, so any keyword in the Inbox can be traced back to the
listing that justified it.

## Advanced / support routes

Real tools, but **not** workflow steps. Kept off the main path on purpose.

- **Research + discovery:** `/opportunities` · `/gems` · `/newest` · `/research` · `/research-queue` · `/longtail` · `/keyword-lab` · `/should-sell` · `/shortlist` · `/winners` · `/etsy-spy` · `/spy` · `/kw-history`
- **Evidence + imports:** `/import-file` · `/score-import` · `/listings` · `/shops` · `/enrich-leads` · `/imports/add`
- **Build + design:** `/draft-listing` · `/photo-brief` · `/design-skill-bridge` · `/design-analyzer` · `/grade` · `/analyze` · `/ads-plan`
- **Team + admin:** `/team` · `/team/calendar` · `/me/tasks` · `/admin/users` · `/admin/tasks` · `/admin/reviews` · `/admin/activity` · `/launchpad` · `/confirm`
- **Monitoring:** `/alerts` · `/trackers` · `/profit` · `/status` · `/daily-brief` · `/build-queue` · `/feedback`
- **Reference:** `/workflow` · `/how-to-use` · `/cheatsheet` · `/training`

## Guardrails

- `PUBLISH_AUTOMATION = False` — no publish path exists in code.
- No automation connects to Etsy, Amazon, eBay or OTA accounts to take actions.
- L0–L4 ranking math is owner-gated; `ranking_engine.py` is unchanged.
- Honest-nulls: a missing measurement stays blank and is never scored as zero.
