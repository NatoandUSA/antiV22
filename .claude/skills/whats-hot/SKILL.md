---
name: whats-hot
description: Weekly Etsy market scan — what's rising right now, what's losing steam, what seasonal events are coming up. Returns a 5-bullet digest plus 3 niches to investigate this week. Quét thị trường Etsy hàng tuần — niche nào đang lên, niche nào hạ nhiệt, sự kiện mùa vụ nào sắp tới. Trả về 5 bullet + 3 niche đáng đào sâu tuần đó. Use when the user asks "what's hot this week?", "what's trending on Etsy?", "weekly scan", "any new opportunities?", "tuần này có gì hot?", "có gì mới trên Etsy?", "có cơ hội nào mới không?", or wants a recurring Monday-morning style market briefing.
---

# What's Hot? / Có Gì Hot?

You give an Etsy seller a 60-second briefing on the week's market movements. Tight, scannable, action-oriented.

## Step 0: Match the user's language

- English question → respond in English
- Vietnamese question → respond in Vietnamese
- Mixed → follow the dominant language

## Step 1: Confirm the scope (only if needed)

Most users just want the whole market. **Skip this step if the user's message didn't mention any specific country, category, or shop type.**

Only ask if they hinted at a scope:

### English version
- Country (default: US)
- Category, or all categories (default: all)
- Price range (default: any)

### Vietnamese version
- Nước (mặc định: US)
- Category, hoặc tất cả (mặc định: tất cả)
- Khoảng giá (mặc định: bất kỳ)

**Default**: when no signal is given, use US / all categories / any price.

## Step 2: Look up the week

Run these tools all at once (one parallel call) and wait for results:

- `ytrends_scout_opportunities` with the sweet-spot preset, limit 10 — rising niches with low competition + high conversion
- `ytrends_browse_rankings` for movers in the 7-day window, direction up, limit 10 — biggest keyword rank gainers this week
- `ytrends_trend_calendar` for the next 30 days — upcoming seasonal events in the next month

Add `ytrends_browse_rankings` with kind=new, last 7 days, limit 5 — only if the user specifically asked about brand-new keywords.

## Step 3: Pick the 5 most actionable signals

Across all results, pick the 5 best signals to surface this week. Rank by:
1. **Actionable now** — the seller can launch or change something this week
2. **Novel** — wasn't obvious last week
3. **Size of opportunity** — bigger volume or stronger momentum wins ties

Each bullet must:
- Lead with the niche/keyword name (not a metric)
- Include one specific number (% momentum, rank change, days to peak)
- End with a 3-word "why it matters" tag

## Step 4: Write the output

Pick exactly one branch below based on the language from Step 0.

### English output

```
## Etsy weekly scan — week of <YYYY-MM-DD>

**5 things to know:**
1. **<niche>** — <metric>. <three-word tag>
2. **<niche>** — <metric>. <three-word tag>
3. **<niche>** — <metric>. <three-word tag>
4. **<niche>** — <metric>. <three-word tag>
5. **<niche>** — <metric>. <three-word tag>

**3 niches to investigate this week:**
- `<niche>` — <one-line reason>. Run `/should-i-sell <niche>` for a launch decision.
- `<niche>` — <one-line reason>.
- `<niche>` — <one-line reason>.

**Coming up (next 30 days):**
- <event> — <N> days away. Recommended listing start: <YYYY-MM-DD = peak − 6 weeks>.
```

### Vietnamese output

```
## Quét Etsy tuần — tuần ngày <YYYY-MM-DD>

**5 điều cần biết:**
1. **<niche>** — <chỉ số>. <tag 3 từ>
2. **<niche>** — <chỉ số>. <tag 3 từ>
3. **<niche>** — <chỉ số>. <tag 3 từ>
4. **<niche>** — <chỉ số>. <tag 3 từ>
5. **<niche>** — <chỉ số>. <tag 3 từ>

**3 niche đáng đào sâu tuần này:**
- `<niche>` — <lý do 1 dòng>. Chạy `/should-i-sell <niche>` để có kết luận launch.
- `<niche>` — <lý do 1 dòng>.
- `<niche>` — <lý do 1 dòng>.

**Sắp tới (30 ngày tới):**
- <sự kiện> — còn <N> ngày. Nên launch listing trước: <YYYY-MM-DD = peak − 6 tuần>.
```

## Step 5: Adjust for the seller's experience level

- **New seller / Seller mới** — trim to 3 bullets + 1 niche to investigate. Add one sentence: "Stick to your existing niche unless you have capacity for a new one." / "Chỉ mở rộng nếu bạn có sức cho niche mới."
- **Scaling seller** (default if unknown) — full 5 bullets + 3 niches as above.
- **POD seller** — drop the "investigate" section (POD wants to act fast, not investigate). Replace it with: "Top 3 to add to your queue this week: <3 niches with the best volume × low competition>."

## Rules

- **Use seller words** — niche, listing, tags, shop, rank, hot, trending, peers, sell-through.
- **Date the heading** — every output starts with the ISO date so the briefing is dateable when shared.
- **One number per bullet** — every signal cites a specific number, no vague "trending up".
- **Briefing, not a report** — if a bullet runs past one line, trim it.
- **Prefer fresh names** — if you have any way to know which niches were called out previously this month, prefer surfacing different ones. Variety = re-read value.
