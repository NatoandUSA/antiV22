# YTrends MCP + Composite Scoring
## Opportunity Shortlister Skill Specification

**Project**: 22etsy-agent (Etsy POD / Embroidery Automation Tool)  
**Version**: 1.0  
**Date**: July 14, 2026  
**Status**: Production-Ready Specification

---

## Table of Contents

1. Executive Summary
2. Context & Background
3. YTrends MCP Tools Overview
4. Composite Scoring Formula
5. Full Skill Specification: `ytrends-opportunity-shortlister`
6. Configurable Weights & Presets
7. Advanced Features
8. Integration Recommendations
9. Verdict Thresholds & Output Schema
10. Next Steps

---

## 1. Executive Summary

This document defines a production-grade **Opportunity Shortlister** skill that integrates the powerful **YTrends MCP server** (https://mcp.trends.ytuong.ai/mcp) with the 22etsy-agent architecture.

The skill delivers:
- Structured JSON data from 13 MCP tools + 3 workflow skills
- A transparent, weighted **Composite Opportunity Score (0–100)**
- Clear **GO / CONDITIONAL / WATCH / SKIP** verdicts
- Explainable rationale suitable for Publish Gate governance
- Configurable weights with category presets
- Advanced features: time-decay on private data, IP risk penalties, and category-specific tuning

This replaces fragmented HTML scraping with clean, live, decision-oriented intelligence.

---

## 2. Context & Background

### Previous State
- User provided 16 static HTML exports from YTrends (Hidden Gems, Trending Keywords, Category rankings, Age Spy, Newest listings, Market Pulse, etc.).
- Existing 22etsy-agent had partial YTuong/HeyEtsy integration for trending + competitor research.
- Need for better structured data, opportunity scoring, and dashboard integration ("dashbarpod").

### New Capability
The YTrends **MCP (Model Context Protocol)** server exposes 13 tools that return clean JSON:
- Full keyword profiles, hidden gems, hot listings, competition analysis, niche briefs, seasonal calendars, etc.
- Three ready-made workflow skills (`/should-i-sell`, `/whats-hot`, `/holiday-prep`).

This enables a much stronger, live, and structured Opportunity Shortlister.

---

## 3. YTrends MCP Tools Overview

### Keywords
- `research_keyword` — Full profile (demand, competition, price, conversion, momentum, rank)
- `get_keyword_rank` — Rank, tier, and history
- `find_trending_keywords` — Strong recent sales/views momentum
- `search` — Quick keyword/tag discovery

### Listings
- `find_hot_listings` — Breakout listings beating niche averages
- `find_hidden_gems` — Underserved high-conversion, low-competition niches
- `browse_new_listings` — Newly created listings (filterable)

### Market Intelligence
- `browse_rankings` — Top-ranked, movers, newest keywords
- `market_snapshot` — Aggregate stats (listings, sellers, revenue, categories)
- `analyze_competition` — Seller concentration, price skew, top-seller share

### Discovery
- `explore_niche` — End-to-end niche brief + recommended action (highest value single tool)
- `scout_opportunities` — High-opportunity niches matching filters
- `trend_calendar` — Seasonal events, prep windows, Q4 deadlines

### Workflow Skills (Claude Code Plugins)
- `/should-i-sell` — GO / CONDITIONAL / NO-GO verdict with reasons
- `/whats-hot` — Weekly 60-second market briefing
- `/holiday-prep` — Seasonal launch timeline with rank-lag math

**Recommendation**: Prioritize `explore_niche`, `find_hidden_gems`, `scout_opportunities`, `research_keyword`, and `analyze_competition` for the shortlister.

---

## 4. Composite Scoring Formula

### Overall Opportunity Score (0–100)

$$
\text{Overall Score} = (M \times 0.32) + (C \times 0.28) + (O \times 0.15) + (P \times 0.15) + (F \times 0.10)
$$

### Component Definitions

| Component              | Weight | Description                                      | Primary MCP Sources                     |
|------------------------|--------|--------------------------------------------------|-----------------------------------------|
| **Market Potential (M)**   | 32%    | Demand + Velocity + Conversion                   | `research_keyword`, `explore_niche`     |
| **Competition Health (C)** | 28%    | Low competition = higher score                   | `analyze_competition`, `find_hidden_gems` |
| **Opportunity Signal (O)** | 15%    | Hidden Gem / "Enter Now" signals                 | `explore_niche`, `find_hidden_gems`     |
| **Private Boost (P)**      | 15%    | Historical sales, margins, personalization       | Internal private data                   |
| **Feasibility & Risk (F)** | 10%    | Design room, seasonality, IP risk                | Internal + `trend_calendar`             |

### Sub-Formulas

**Market Potential (M)**
$$
M = (D \times 0.40) + (V \times 0.35) + (CR \times 0.25)
$$

**Competition Health (C)**
$$
C = 100 - \text{Competition Intensity}
$$

**Private Boost (P)** — Includes optional time-decay (see Advanced Features).

---

## 5. Full Skill Specification: `ytrends-opportunity-shortlister`

### Purpose
Analyze one or more niches using YTrends MCP data + private signals. Return scored, explainable verdicts ready for human review in the Publish Gate.

### Inputs

#### Single Niche Mode (Primary)
```json
{
  "niche": "spiritual advice linen apron",
  "category_hint": "Home & Living",
  "include_spy": true,
  "private_data": {
    "past_performance_score": 72,
    "avg_margin_pct": 68,
    "design_feasibility": 85,
    "ip_risk_level": "low",
    "seasonality_alignment": 78,
    "personalization_lift": 12,
    "last_sale_date": "2026-05-15"
  }
}
```

#### Batch Mode
```json
{
  "candidates": ["niche one", "niche two"],
  "max_results": 15,
  "min_score_threshold": 60,
  "category_hint": "Home & Living"
}
```

### Outputs (Structured JSON)

```json
{
  "niche": "spiritual advice linen apron",
  "overall_score": 79.1,
  "verdict": "CONDITIONAL",
  "sub_scores": {
    "market_potential": 79.3,
    "competition_health": 75,
    "opportunity_signal": 88,
    "private_boost": 75,
    "feasibility_risk": 82
  },
  "rationale": [
    "Strong momentum and above-average conversion",
    "Low competition + Hidden Gem signals",
    "Strong private performance in similar niches"
  ],
  "recommended_actions": [
    "Run spy enrichment on top hot listings",
    "Prioritize personalization in title/tags"
  ],
  "mcp_data_summary": { ... },
  "next_tool_calls": ["find_hot_listings", "analyze_competition"]
}
```

### Prompt Structure for Claude (Researcher Role)

```markdown
You are an expert Etsy POD/Embroidery Researcher using the YTrends MCP.

Task: Analyze the niche "{niche}" using the ytrends-opportunity-shortlister skill.

Steps:
1. Call the necessary MCP tools (`explore_niche`, `research_keyword`, `find_hidden_gems`, `analyze_competition`).
2. Apply the composite scoring formula with the provided private_data.
3. Return ONLY the structured JSON output defined in the skill spec.
4. Be conservative on IP risk and feasibility.

Private signals:
{paste private_data here}

Output: Strict JSON only. No extra text.
```

### Core Python Scoring Function

```python
from dataclasses import dataclass
from typing import Dict, Any, Optional
from datetime import datetime

@dataclass
class ScoringWeights:
    market: float = 0.32
    competition: float = 0.28
    opportunity: float = 0.15
    private: float = 0.15
    feasibility: float = 0.10


def calculate_composite_score(
    mcp_data: Dict[str, Any],
    private_data: Dict[str, Any],
    weights: ScoringWeights = ScoringWeights(),
    category: Optional[str] = None
) -> Dict[str, Any]:

    # 1. Market Potential
    demand = mcp_data.get("demand", 50)
    velocity = mcp_data.get("velocity", 50)
    conversion = mcp_data.get("conversion", 50)
    market = (demand * 0.40) + (velocity * 0.35) + (conversion * 0.25)

    # 2. Competition Health
    comp_intensity = mcp_data.get("competition_intensity", 50)
    competition = max(0, 100 - comp_intensity)

    # 3. Opportunity Signal
    explore_verdict = mcp_data.get("explore_niche_verdict", "neutral").lower()
    is_hidden_gem = mcp_data.get("is_hidden_gem", False)

    if "enter now" in explore_verdict or is_hidden_gem:
        opportunity = 88
    elif "conditional" in explore_verdict:
        opportunity = 72
    elif "study" in explore_verdict or "weak" in explore_verdict:
        opportunity = 35
    else:
        opportunity = 55

    # 4. Private Boost (with optional time decay)
    past_perf = private_data.get("past_performance_score", 50)
    margin = private_data.get("avg_margin_pct", 55)
    personalization = private_data.get("personalization_lift", 0)

    # Time decay example
    last_sale = private_data.get("last_sale_date")
    if last_sale:
        days_ago = (datetime.now() - datetime.fromisoformat(last_sale)).days
        decay = 0.5 ** (days_ago / 90)  # 90-day half-life
        past_perf *= decay

    private_boost = min(100, (past_perf * 0.6) + (margin * 0.25) + (personalization * 1.5))

    # 5. Feasibility & Risk
    design = private_data.get("design_feasibility", 60)
    seasonality = private_data.get("seasonality_alignment", 60)
    ip_risk = private_data.get("ip_risk_level", "medium").lower()

    ip_penalty = {"low": 0, "medium": -12, "high": -30}.get(ip_risk, -15)
    feasibility = max(0, (design * 0.45) + (seasonality * 0.35) + 20 + ip_penalty)

    # Weighted Overall
    overall = (
        market * weights.market +
        competition * weights.competition +
        opportunity * weights.opportunity +
        private_boost * weights.private +
        feasibility * weights.feasibility
    )

    # Verdict
    if overall >= 80:
        verdict = "GO"
    elif overall >= 65:
        verdict = "CONDITIONAL"
    elif overall >= 50:
        verdict = "WATCH"
    else:
        verdict = "SKIP"

    return {
        "overall_score": round(overall, 1),
        "verdict": verdict,
        "sub_scores": {
            "market_potential": round(market, 1),
            "competition_health": round(competition, 1),
            "opportunity_signal": round(opportunity, 1),
            "private_boost": round(private_boost, 1),
            "feasibility_risk": round(feasibility, 1)
        },
        "rationale": _generate_rationale(market, competition, opportunity, private_boost, feasibility, ip_risk),
        "weights_used": weights.__dict__
    }


def _generate_rationale(m, c, o, p, f, ip_risk):
    reasons = []
    if m > 75: reasons.append("Strong demand + momentum from YTrends MCP")
    if c > 70: reasons.append("Favorable low-competition landscape")
    if o > 80: reasons.append("Positive Hidden Gem / Enter Now signals")
    if p > 70: reasons.append("Strong private sales history in similar niches")
    if f < 55: reasons.append(f"Feasibility or IP risk concerns ({ip_risk})")
    return reasons if reasons else ["Balanced profile across metrics"]
```

---

## 6. Configurable Weights & Presets

**File**: `config/scoring_weights.json`

```json
{
  "default": {
    "market": 0.32,
    "competition": 0.28,
    "opportunity": 0.15,
    "private": 0.15,
    "feasibility": 0.10
  },
  "presets": {
    "home_living": {
      "market": 0.30,
      "competition": 0.30,
      "opportunity": 0.18,
      "private": 0.14,
      "feasibility": 0.08
    },
    "clothing_apparel": {
      "market": 0.35,
      "competition": 0.25,
      "opportunity": 0.12,
      "private": 0.18,
      "feasibility": 0.10
    },
    "spiritual_gifts": {
      "market": 0.28,
      "competition": 0.32,
      "opportunity": 0.20,
      "private": 0.12,
      "feasibility": 0.08
    }
  },
  "advanced": {
    "time_decay_half_life_days": 90,
    "ip_risk_penalties": {
      "low": 0,
      "medium": -12,
      "high": -30
    },
    "min_score_for_spy_enrichment": 65
  }
}
```

**Usage**:
```python
weights = ScoringWeights(**config["presets"]["spiritual_gifts"])
```

---

## 7. Advanced Features

| Feature                    | Implementation                                                                 | Benefit |
|---------------------------|----------------------------------------------------------------------------------|--------|
| **Time-Decay on Private Data** | Apply exponential decay (`0.5 ** (days_ago / half_life)`) to `past_performance_score` | Older wins lose influence over time |
| **Category-Specific Presets**  | `presets` object in config (Home & Living, Clothing, Spiritual, etc.)           | Different niches emphasize different signals |
| **IP Risk Penalty Rules**      | Tiered penalties (`low=0`, `medium=-12`, `high=-30`) applied to Feasibility score | Strong governance and risk control |
| **Explainable Output**         | Always returns sub-scores + human-readable rationale list                       | Excellent for Publish Gate audits and learning |
| **Spy Enrichment Trigger**     | If score ≥ `min_score_for_spy_enrichment`, automatically suggest `find_hot_listings` | Seamless handoff to Listing Generator |

---

## 8. Integration Recommendations

### Workflow Placement
1. **Researcher** calls `ytrends-opportunity-shortlister` (single or batch)
2. Skill returns scored verdicts + rationale
3. Human reviews in **Publish Gate**
4. Approved niches → `Listing Generator` (with spy enrichment from `find_hot_listings`)
5. Post-launch → feed sales data back into private performance signals (learning loop)

### Dashboard Ideas ("dashbarpod")
- **Quick Wins** widget: Top Hidden Gems / Scout Opportunities
- **Niche Brief Panel**: When a niche is selected, show full `explore_niche` brief + composite score breakdown
- **Weekly Momentum**: Powered by `/whats-hot` style output or `find_trending_keywords`
- **Seasonal Prep**: `trend_calendar` data with launch windows highlighted
- **Score History**: Track how scores correlate with actual sales over time

### Governance
- All scoring runs should be logged with raw MCP JSON + final explanation.
- Human approval remains mandatory before any listing is generated or published.

---

## 9. Verdict Thresholds

| Overall Score | Verdict       | Action                                      | Notes |
|---------------|---------------|---------------------------------------------|-------|
| 80 – 100      | **GO**        | Proceed to Listing Generator                | Strong across most dimensions |
| 65 – 79       | **CONDITIONAL** | Proceed with extra spy work + differentiation | Good fundamentals, needs strong angle |
| 50 – 64       | **WATCH**     | Monitor or deprioritize                     | Marginal — only pursue with very strong private data |
| 0 – 49        | **SKIP**      | Do not pursue                               | Weak fundamentals or high risk |

---

## 10. Next Steps

1. Implement `ytrends-opportunity-shortlister` skill using the Python function and config above.
2. Add config loader so weights and presets are externalized and tunable.
3. Wire MCP tool calls into the skill (or accept pre-fetched data).
4. Build dashboard widgets for score visualization and rationale display.
5. Begin logging scoring runs + outcomes to strengthen the private learning loop.

---

**Document Version**: 1.0  
**Maintained by**: 22etsy-agent Team  
**License**: Internal use only

---

*This specification is ready for implementation. It provides a clear, governable, and continuously improvable foundation for opportunity discovery using live YTrends MCP data.*