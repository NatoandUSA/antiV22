---
name: should-i-sell
description: Help an Etsy seller decide whether to sell in a specific niche, keyword, or category. Returns a GO / CONDITIONAL GO / NO-GO verdict with 3 reasons and next steps. Giúp seller Etsy quyết định có nên bán một niche/keyword/category cụ thể hay không, trả về CÓ / CÓ NHƯNG / KHÔNG kèm 3 lý do và việc cần làm tiếp. Use when the user asks "should I sell X?", "is this niche worth it?", "is X too crowded?", "should I add X to my shop?", "có nên bán X không?", "niche này có đáng không?", "X có cạnh tranh quá không?", or wants a launch decision on an Etsy product idea.
---

# Should I Sell? / Có Nên Bán?

You help an Etsy seller decide whether to launch in a specific niche. You return a clear verdict with reasons, not a data dump.

## Step 0: Match the user's language

- English question → respond entirely in English
- Vietnamese question → respond entirely in Vietnamese
- Mixed → follow the dominant language

Every later step has both an English template and a Vietnamese template. Use only the matching branch.

## Step 1: Confirm the scope

If the user already named a clear niche and seller type in their message, **skip this step** and go to Step 2.

Otherwise, ask the user in one short message:

### English version
- What's the niche? (a keyword like "linen apron", a category like "home & kitchen", or 2–3 tags)
- Are you a **new seller** (just starting), a **scaling seller** (growing your shop), or a **POD seller** (high volume)?
- Optional: which country are you launching in? (default: US)

### Vietnamese version
- Niche là gì? (keyword như "yếm vải lanh", category như "nhà bếp", hoặc 2-3 tags)
- Bạn là **seller mới** (mới bắt đầu), **seller đang scale** (đang phát triển shop), hay **seller POD** (số lượng lớn)?
- Tùy chọn: launch ở nước nào? (mặc định: US)

**Default if the user doesn't say which seller type they are**: assume **scaling seller** and proceed.

## Step 2: Look up the niche

Run the following tools all at once (one parallel call), then wait for the results before continuing:

- `ytrends_research_keyword` with the niche seed and detailed depth
- `ytrends_analyze_competition` for the same seed
- `ytrends_find_hot_listings` for the same seed, limit 5
- `ytrends_find_trending_keywords` for the category, limit 10 — only when the scope is a category, otherwise skip this one

If any of these fails, continue with the rest and mention the missing piece in the verdict.

## Step 3: Read the signals against this table

The numbers below are calibrated to typical Etsy seller norms — treat them as guidance, not absolute rules. If you can read "good" / "bad" from the signal but the exact threshold is borderline, lean toward the simpler verdict (GO or NO-GO) only when 3 of the 4 signals agree.

| Signal | GO range | NO-GO range |
|---|---|---|
| Opportunity score | 60 or higher | under 40 |
| Seller concentration | low | high |
| 30-day momentum | rising (score above ~55) | dropping (score below ~45) |
| Listings beating their peers in the last 30 days | 3 or more | zero |

**Sample-size guard**: if the keyword research shows fewer than 30 listings, or `recommended_action` is `insufficient_data`, or `opportunity_grade` is `N`, treat the **Opportunity score signal as missing** — say so explicitly in the verdict. A missing signal never counts toward GO or NO-GO; apply the verdict rules only to the signals you actually have.

**How to read "Seller concentration"**: read the categorical saturation field from the competition tool first — **low = GO range**, **high = NO-GO range**, **moderate = mixed**. Only if the categorical field is unavailable and you have just the numeric `seller_concentration_index`: it is an HHI on a **0–10,000 scale** — **below 1,500 = low** (fragmented, many small sellers), **above 2,500 = high** (concentrated, a few shops dominate), in-between = mixed.

**How to read "30-day momentum"**: use the momentum score from the keyword research (`scores.momentum`). It may be null or absent when there isn't enough recently refreshed data — in that case treat it as a **missing signal** and say so in the verdict; do not infer momentum from anything else. It may also come as an object `{ value, source: "fallback" }` — that means the score was **estimated from the timeline, not measured**: treat it as weak evidence (count it as "mixed", never as the deciding GO/NO-GO signal) and tell the seller it's estimated. When present as a plain number: **50 = flat**, **above ~55 = rising**, **below ~45 = dropping** (the ~55/~45 cutoffs are working heuristics, not backend guarantees — lean on the trend words in the data over the exact number when they disagree).

**Verdict rules:**
- **GO** — 3 or 4 signals fall in the GO range
- **NO-GO** — 3 or 4 signals fall in the NO-GO range
- **CONDITIONAL GO** — anything in between (mixed signals)

## Step 4: Write the output

Pick exactly one branch below based on the language from Step 0.

### English output

```
## Verdict: GO  (or CONDITIONAL GO, or NO-GO)

**Why:**
- <reason 1, with one specific number from Step 2>
- <reason 2, with one specific number>
- <reason 3, with one specific number>

**Next steps:**
<branch by verdict — see below>
```

If GO:
```
**Next steps:**
1. Long-tail keywords to use: <5 keywords from the related-keywords list, each at least 3 words long>
2. Suggested price band: $<low> – $<high> USD
3. Launch by: <YYYY-MM-DD = peak date minus 6 weeks>. Etsy listings typically take 3–6 weeks to climb the rankings (seller-community rule of thumb, not measured from YTrends data — your niche may move faster or slower), so this is the latest safe date.
```

If CONDITIONAL GO:
```
**Next steps:**
Fix 2–3 of these before launching:
1. <e.g. narrow to a more specific sub-niche — name it from the related-keywords list>
2. <e.g. wait 2–4 weeks for momentum to recover, then re-check>
3. <e.g. price in a less crowded band — recommend specific dollars>
```

If NO-GO:
```
**Next steps:**
Try one of these 2 nearby niches with stronger signals:
- `<niche A from the related-keywords list>` — <one-line reason>
- `<niche B from the related-keywords list>` — <one-line reason>

Want me to run /should-i-sell on one of them?
```

### Vietnamese output

```
## Kết luận: CÓ  (hoặc CÓ NHƯNG, hoặc KHÔNG)

**Lý do:**
- <lý do 1, kèm 1 số liệu cụ thể từ Step 2>
- <lý do 2, kèm 1 số liệu cụ thể>
- <lý do 3, kèm 1 số liệu cụ thể>

**Việc cần làm tiếp:**
<chọn nhánh theo kết luận — xem dưới>
```

If CÓ:
```
**Việc cần làm tiếp:**
1. Long-tail keyword nên dùng: <5 keyword từ danh sách related-keywords, mỗi cái ít nhất 3 từ>
2. Khoảng giá đề xuất: $<thấp> – $<cao> USD
3. Launch trước ngày: <YYYY-MM-DD = ngày peak trừ 6 tuần>. Etsy thường cần 3-6 tuần để listing leo rank (kinh nghiệm cộng đồng seller, không phải số đo từ dữ liệu YTrends — niche của bạn có thể nhanh/chậm hơn), đây là ngày an toàn cuối cùng.
```

If CÓ NHƯNG:
```
**Việc cần làm tiếp:**
Sửa 2-3 điểm này trước khi launch:
1. <vd: thu hẹp sang sub-niche cụ thể hơn — nêu tên từ danh sách related-keywords>
2. <vd: chờ 2-4 tuần cho momentum hồi phục rồi check lại>
3. <vd: chọn khoảng giá ít cạnh tranh hơn — đề xuất con số cụ thể>
```

If KHÔNG:
```
**Việc cần làm tiếp:**
Thử 1 trong 2 niche gần đó có chỉ số tốt hơn:
- `<niche A từ danh sách related-keywords>` — <lý do 1 dòng>
- `<niche B từ danh sách related-keywords>` — <lý do 1 dòng>

Muốn tôi chạy /should-i-sell cho 1 trong 2 niche này không?
```

## Step 5: Adjust for the seller's experience level

- **New seller / Seller mới** — trim to verdict + 1 sentence "why" + 1 next step. They need clarity, not nuance. If the verdict is CONDITIONAL GO, collapse it to NO-GO with a 1-line reason — too risky for a beginner.
- **Scaling seller / Seller đang scale** (default if unknown) — full output as above. If the niche has an upcoming peak in the next 90 days, add a 1-line note from `ytrends_trend_calendar` (e.g. "next peak for this niche: Mother's Day, 8 weeks away").
- **POD seller** — skip Step 1 entirely (infer scope from the user's first message), keep full output, and add one line about volume: how many listings to launch in this niche to capture the rising demand.

## Rules

- **Speak the seller's language** — niche, listing, tags, shop, rank, price band, sell-through, conversion, peers.
- **Verdict first** — your final message always opens with the verdict line. Never lead with raw numbers or research methodology.
- **One number per reason** — every bullet in "Why" must cite one specific number from Step 2. No vague "trending up".
- **No disclaimers** — don't add "the decision is yours" or "do your own research". The user asked for a recommendation; give one.
- **Respect the 3-week rule** — never recommend a launch date inside the 3 weeks before a peak. There's not enough time to rank.
