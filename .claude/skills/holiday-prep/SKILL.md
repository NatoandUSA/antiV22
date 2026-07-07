---
name: holiday-prep
description: Build a launch timeline for an Etsy seasonal event (Mother's Day, Father's Day, Halloween, Black Friday, Christmas, Valentine's, etc.) with hard deadline gating and the 3–6 week rank-lag math baked in. Returns the latest safe launch date for each event plus rising tied niches. Lập timeline launch cho sự kiện mùa vụ Etsy (Mother's Day, Father's Day, Halloween, Black Friday, Christmas, Valentine's, v.v.) có sẵn quy tắc deadline cứng và rank-lag 3-6 tuần. Trả về ngày launch muộn nhất an toàn cho mỗi sự kiện kèm các niche đang lên. Use when the user asks "am I ready for Q4?", "when should I launch for Mother's Day?", "Christmas prep?", "holiday timeline", "Black Friday plan", "tôi đã sẵn sàng Q4 chưa?", "bao giờ nên launch cho lễ X?", "chuẩn bị mùa lễ".
---

# Holiday Prep / Chuẩn Bị Mùa Lễ

You build an Etsy seller's seasonal launch timeline. The key fact: listings need **3–6 weeks** to climb the Etsy rankings, so launching in the same week as a holiday is too late. This skill does that math for the seller.

> The 3–6 week rank-lag and the Sept 15 / Oct 1 deadlines below are **Etsy seller-community rules of thumb, not measurements from YTrends data**. Treat them as planning guardrails: a niche can rank faster or slower depending on competition and listing quality. When you state a deadline in the output, keep it — but if the seller pushes back, say plainly that these are community heuristics.

## Step 0: Match the user's language

- English question → respond in English
- Vietnamese question → respond in Vietnamese
- Mixed → follow the dominant language

## Step 1: Confirm the scope

If the user already named a specific event in their message (e.g. "Mother's Day", "Q4", "Halloween"), **skip this step** and use their pick.

Otherwise, ask in one short message:

### English version
- Which event(s)? Examples: "Mother's Day", "Q4 (Halloween + BFCM + Christmas)", "next 90 days", "next 6 months"
- Any niche or category to focus on, or all? (default: all)
- Are you a **new seller**, **scaling seller**, or **POD seller**? (optional)

### Vietnamese version
- Sự kiện nào? Ví dụ: "Mother's Day", "Q4 (Halloween + BFCM + Christmas)", "90 ngày tới", "6 tháng tới"
- Niche/category cụ thể hay tất cả? (mặc định: tất cả)
- Bạn là **seller mới**, **đang scale**, hay **POD**? (tùy chọn)

**Default if no seller type is given**: assume **scaling seller** and proceed.

## Step 2: Fetch the calendar

Call `ytrends_trend_calendar` once with the appropriate window:
- `next_30d` — if the user said "this month" or named a single event in the next 30 days
- `next_90d` — if the user said "this quarter", "Q4", or named multiple events
- `full_year` — if the user asked for a 6+ month view

From the result, pick the top 3–5 events by opportunity score (or the specific events the user named).

## Step 3: Pull tied opportunities for each event

For each event picked, call `ytrends_scout_opportunities` with the sweet-spot preset, filtered by the event's top 3 tied keywords, limit 5. Run all of these together (one parallel call across events).

This surfaces low-competition rising niches that fit each event.

## Step 4: Apply the rank-lag math

For each event, compute three dates relative to the peak:

- `latest_safe_launch_date = peak_date − 6 weeks` (the start of the runway)
- `soft_deadline = peak_date − 4 weeks` (tight but doable)
- `hard_deadline = peak_date − 3 weeks` (no new launches)

Then categorize **today's date** for each event:

| If today is ≤ latest_safe_launch_date | 🟢 **GREEN** — full runway, follow normal flow |
| If today is between latest_safe and soft_deadline | 🟡 **YELLOW** — possible but tight; prioritize evergreen listings and add seasonal tags later |
| If today is between soft and hard deadline | 🟠 **ORANGE** — only relist or optimize existing listings, no brand-new launches |
| If today is past hard_deadline | 🔴 **RED** — skip this event, plan for next year |

**For Q4 events specifically** — events peaking **October–December** (Halloween, Black Friday/Cyber Monday, Christmas) — also apply the well-known Etsy seller deadlines on top of the rank-lag math (community consensus dates, not YTrends measurements):
- **September 15** — high-competition Q4 niches must already be live
- **October 1** — absolute last date for any Q4 launch

If today crosses these for a Q4 event, emit a deadline alert even if rank-lag math still says GREEN. These two dates apply **only** to Q4 events — for every other event (Mother's Day, Valentine's, Father's Day, etc.) the rank-lag math computed from the trend-calendar peak dates is the source of truth.

## Step 5: Write the output

Pick exactly one branch below based on the language from Step 0.

### English output

```
## Etsy seasonal plan — generated <YYYY-MM-DD>

**Overall status: <GREEN | YELLOW | ORANGE | RED>**

| Event | Peak date | Launch by | Status | Top tied niches |
|---|---|---|---|---|
| <event> | <YYYY-MM-DD> | <YYYY-MM-DD = peak − 6 weeks> | 🟢/🟡/🟠/🔴 | <3 tied niches, comma-separated> |
| <event> | <YYYY-MM-DD> | <YYYY-MM-DD = peak − 6 weeks> | 🟢/🟡/🟠/🔴 | <3 tied niches> |
| <event> | <YYYY-MM-DD> | <YYYY-MM-DD = peak − 6 weeks> | 🟢/🟡/🟠/🔴 | <3 tied niches> |

**What to do this week:**
1. <action tied to the highest-priority GREEN or YELLOW event>
2. <action tied to the next event>
3. <action tied to the next event>
```

If any event is RED, or a Q4 event (peaking Oct–Dec: Halloween, BFCM, Christmas) is past the Sept 15 / Oct 1 dates:
```
⚠️ **Deadline alert**: <event> is past <reason — e.g. "September 15 high-competition cutoff">. Drop new launches for it; focus on <next event with runway>.
```

If the seller is POD:
```
**Volume suggestion**: launch <N> listings/week across the GREEN events to capture rising demand.
```

### Vietnamese output

```
## Kế hoạch mùa vụ Etsy — tạo ngày <YYYY-MM-DD>

**Tình trạng tổng: <GREEN | YELLOW | ORANGE | RED>**

| Sự kiện | Ngày peak | Launch trước | Tình trạng | Niche tied đáng quan tâm |
|---|---|---|---|---|
| <sự kiện> | <YYYY-MM-DD> | <YYYY-MM-DD = peak − 6 tuần> | 🟢/🟡/🟠/🔴 | <3 niche, ngăn cách bởi dấu phẩy> |
| <sự kiện> | <YYYY-MM-DD> | <YYYY-MM-DD = peak − 6 tuần> | 🟢/🟡/🟠/🔴 | <3 niche> |
| <sự kiện> | <YYYY-MM-DD> | <YYYY-MM-DD = peak − 6 tuần> | 🟢/🟡/🟠/🔴 | <3 niche> |

**Việc cần làm tuần này:**
1. <action cho sự kiện ưu tiên cao nhất GREEN hoặc YELLOW>
2. <action cho sự kiện tiếp>
3. <action cho sự kiện tiếp>
```

If any event is RED, or a Q4 event (peak tháng 10–12: Halloween, BFCM, Christmas) is past Sept 15 / Oct 1:
```
⚠️ **Cảnh báo deadline**: <sự kiện> đã qua <lý do — vd "deadline 15/9 cho niche cạnh tranh cao">. Bỏ kế hoạch launch mới; tập trung vào <sự kiện tiếp còn runway>.
```

If the seller is POD:
```
**Đề xuất volume**: launch <N> listings/tuần cho các sự kiện GREEN để bắt cầu đang lên.
```

## Step 6: Adjust for the seller's experience level

- **New seller / Seller mới** — limit the table to the top 2 events. Drop the volume suggestion line. Add one sentence: "Pick ONE event to focus on this season — don't spread thin." / "Chọn DUY NHẤT 1 sự kiện để tập trung mùa này — đừng dàn trải."
- **Scaling seller** (default if unknown) — full output (3–5 events).
- **POD seller** — full output plus the volume suggestion line.

## Rules

- **Use seller words** — listing, niche, tags, shop, rank, peak, launch, runway, deadline, season.
- **Date everything in ISO** — `YYYY-MM-DD`, US Eastern implied. Even partial dates ("Q4") get expanded to specific calendar dates.
- **Status emoji is required** — 🟢🟡🟠🔴 give instant scannability for sellers who skim.
- **Never recommend a launch date inside the 3-week hard-deadline window** — that math is not negotiable.
- **Q4 hard deadlines win over rank-lag math — for Q4 events only** — Sept 15 / Oct 1 apply to events peaking Oct–Dec (Halloween, BFCM, Christmas); emit the alert even if rank-lag says GREEN. For non-Q4 events, the rank-lag math from the trend-calendar peak dates is the source of truth.
- **Peak dates come from the calendar tool**, not from memory — always cite them exactly.
