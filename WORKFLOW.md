# 🧭 Quy trình nhóm — Etsy Winner Machine (V28)

> **Nguyên tắc 1 câu:** Chọn **người mua có ví tiền + cảm xúc** trước, rồi mới thiết kế cho họ.
> Mọi bước dưới đây tồn tại để **giết ý tưởng yếu TRƯỚC KHI** tốn tiền sản xuất.
>
> 🔒 **KHÔNG BAO GIỜ tự đăng.** Công cụ chỉ chuẩn bị; **người thật bấm đăng thủ công** trên Etsy.
> 📄 Tài liệu viết **tiếng Việt** cho team; listing luôn viết **tiếng Anh**.

## Mục lục

[TOC]

---

## Sơ đồ đường ống mới (fast lane) — 5 bước trên trang chủ

```
 ①  CAPTURE            📥 Thả file CSV/JSON vào ô trên trang chủ (hoặc extension "Send to agent")
        │                 → Tự nhận diện nguồn, đưa về đúng "lane"
        ▼
 ②  FIND WINNERS       🏆 Winner Finder  →  xếp hạng theo "nhu cầu cao × ít cạnh tranh"
        │                 (chấm điểm cục bộ, tức thì, KHÔNG chờ server)
        ▼
 ③  BUILD              🚀 Launch Kit  →  1 keyword ra HẾT: verdict + đối thủ + listing SEO
        │                 + prompt ảnh + kế hoạch ads + checklist, trên MỘT trang
        ▼
 ④  LAUNCH             ✋ Duyệt tay trong Etsy → đăng 3–5 biến thể → Etsy Ads $1–3/ngày
        │
        ▼
 ⑤  LEARN             📉 Ghi nhận đơn bán → vòng học nâng điểm cho niche đã bán được
        └───────────────────────────────── vòng lặp: winner đã bán tự lên hạng lần sau
```

> 🧭 **Điều hướng:** mọi trang có thanh trên cùng (Home · Research · Import · Team · Review · Guide).
> Ô thả file (Capture) nằm ngay ở bước ① trên trang chủ.

---

## ① CAPTURE — thả dữ liệu, tool tự đưa về đúng chỗ

Kéo–thả **1 hoặc NHIỀU** file CSV/JSON vào ô trên trang chủ. Có ô chọn **nguồn** (mặc định **Tự nhận diện**).
Nhiều file sẽ được **gộp + khử trùng lặp** theo keyword.

| Nguồn thả vào | Là loại dữ liệu gì | Tool đưa tới | Ý nghĩa tín hiệu |
|---|---|---|---|
| **Etsy / YTrends keywords** | Bảng **keyword** (có cột Views + Competition) | 🏆 **Winner Finder** | Nhu cầu Etsy thật → xếp hạng winner |
| **Etsy listings / spy** | Bảng **listing** (title + sold + tags, KHÔNG có cột keyword) | 🕵️ **Etsy Spy → keyword leads** | Keyword lặp lại nhiều = có cầu (coi chừng bão hoà) |
| **Supplier (1688/Alibaba/AliExpress)** | Sản phẩm nhà máy (sold, reorder, MOQ) | 🏭 **Supplier Trend Finder** | Nhà máy đẩy mạnh = người bán đang săn (tín hiệu ĐI TRƯỚC) |
| **Pinterest** | Pin (title/mô tả, saves) | 📌 **Pinterest Trend Finder** | Người mua quà lên kế hoạch sớm → saves cao = cầu đang lên |
| **Amazon Xray (Helium 10)** | Keyword Amazon (search volume, competing) | 🏆 Winner Finder (**gắn nhãn tham khảo**) | Chỉ để đối chiếu — cầu Amazon ≠ cầu Etsy |

> **Trung thực (honest-nulls):** thiếu cột nào thì để trống, **không bịa số**. Nguồn ngoài Etsy chỉ là
> **manh mối cầu**, phải đối chiếu lại với Etsy trước khi build.

Dưới ô thả có dòng **"Last import: N rows · X phút trước · nguồn"** để biết đang dùng dữ liệu nào.

---

## ② FIND WINNERS — Winner Finder (trái tim của tool)

`🏆 Winner Finder` lấy import mới nhất và **xếp hạng đúng góc "cầu cao × ít cạnh tranh"**.

- **Winner** = trung bình nhân của **Nhu cầu (Demand)** và **Sức khoẻ cạnh tranh (ít bão hoà)**.
  Phải **mạnh CẢ HAI** mới lên hạng — cầu cao mà bão hoà, hoặc thoáng mà không có cầu, đều bị kéo xuống.
- Cột **Demand** (dài = tốt) và **Saturation** (ngắn = tốt) hiển thị bằng thanh trực quan.
- **✔N** cạnh keyword = **shop mình đã bán N đơn** niche này → vòng học đã tự nâng điểm (xem bước ⑤).
- Bấm **+ Google Trends** để đối chiếu cầu ngoài Etsy cho top 12.
- **Sharpest pick** ở cuối → bấm thẳng **Build the full Launch Kit**.

Verdict: **GO ≥ 80 · CONDITIONAL ≥ 65 · WATCH ≥ 50 · SKIP**. Thiếu tín hiệu lõi → tối đa **WATCH** (không GO ẩu).

---

## ③ BUILD — Launch Kit (1 winner ra tất cả)

`🚀 Launch Kit` gom mọi thứ để launch **1 winner** trên **một trang**:

1. **Verdict & winner score** — điểm, verdict, trademark; báo đỏ nếu HIGH-risk hoặc SKIP.
2. **Beat competitors** — khe hở cạnh tranh **đo được** (thiếu cá nhân hoá / title yếu / thiếu tag / video / …), lớn nhất trước.
3. **Listing draft** — title (keyword trong 40 ký tự đầu), 13 tag, mô tả, cá nhân hoá, bài toán lợi nhuận.
4. **Photo prompt set** — 10 slot ảnh + prompt AI. **Slot đánh dấu 📸 REAL PHOTO phải là ảnh thật** (mũi chỉ/sản phẩm thật); AI chỉ dùng cho mockup/đồ hoạ.
5. **Etsy Ads plan** — ngân sách bắt đầu, **breakeven ACOS từ phí Etsy thật**, phủ tag, luật đọc/giết sau 2 tuần.
6. **Seller launch checklist** — 9 bước từ trademark → sew-out → listing → profit gate → ảnh → publish → ads → **ghi nhận đơn bán**.

> Các công cụ lẻ vẫn có nếu cần: `/draft-listing`, `/photo-brief`, `/ads-plan`, `/edge` (Beat competitors).

---

## ④ LAUNCH — vẫn 100% thủ công trong Etsy

1. Thiết kế **stitch-safe** (≤6 màu chỉ, hình bold, chữ đọc được); **làm sew-out/proof thật trước khi scale**.
2. Chạy `📋 Listing Analyzer` (`/grade`) + `💰 Profit Center` (`/profit`) — chốt biên lợi nhuận **≥ 35–40% NET**.
3. **Người thật** dán nội dung, đăng **3–5 biến thể** của 1 concept (khác angle/sản phẩm), KHÔNG đăng 1 cái.
4. Bật **Etsy Ads $1–3/ngày** theo kế hoạch — chỉ để gom dữ liệu click, chưa cần lời ngay.

---

## ⑤ LEARN — vòng học tự nâng điểm

Khi bán được, vào `📉 Sales feedback` (Launch Kit có sẵn **link điền sẵn**) ghi: keyword, tag, mode, giá, đơn.

- Mỗi đơn ghi nhận → cập nhật `winner_patterns` → **Winner Finder tự nâng điểm** niche đó (và tag liên quan) lần sau.
- Công cụ gợi ý **GIỮ / SỬA / GIẾT / SCALE** theo Ngày 3 / Ngày 7.
- Winner đã bán được hiện **✔N** và nổi lên đầu bảng → bạn nhân bản concept thắng ra 10–20 biến thể.

**Flywheel:** capture → winner → launch kit → publish → ghi đơn → vòng học sắc hơn → lần capture sau tốt hơn.

---

## Vòng team (khi cần giao việc, không làm 1 mình)

Fast lane ở trên là để **1 người chạy nhanh**. Khi cần chia việc cho team, dùng vòng cũ (vẫn hoạt động):

```
✅ Confirm & Assign  →  🧭 Research Queue  →  (supplier · design · draft)  →  🔍 Review Queue (Manager duyệt)  →  ✋ Đăng thủ công
```

- **Manager desk** trên trang chủ: Imported today · In flight · To review · Ready to publish · Blocked · Day 3/7 due.
- `👥 Team` / `📅 Team Calendar`: giao việc, xem "ai đang làm gì", hạn chót.

---

## Bảng điểm Cơ hội (0–100) — cách chấm

`Overall = Market(0.32) + Competition(0.28) + Opportunity(0.15) + Private(0.15) + Feasibility(0.10)`

- **Market** = cầu (views/momentum/conversion). **Competition** = 100 − độ bão hoà.
- **Private** = dữ liệu bán thật của shop (vòng học). **Feasibility** = sản xuất được + rủi ro trademark.
- Thiếu tín hiệu lõi (Market/Competition/Opportunity) → **cap ở WATCH**. Trademark HIGH → **SKIP**.

---

## Cổng đăng bán (Publish Gate) & Quy tắc vàng (BẮT BUỘC)

- 🔒 **Không tự đăng.** Listing chỉ lên khi mọi cổng cứng đạt **VÀ** Manager ký **VÀ** người thật bấm đăng.
- 🎯 **Real photo:** ảnh hero + macro mũi chỉ + số đo **phải là ảnh thật**. AI render sản phẩm thật = quảng cáo sai.
- 🧵 **Sew-out trước khi scale** với thêu. Đo lợi nhuận **thật**, không đo doanh thu.
- ⚖️ **Trademark:** kiểm mọi cụm từ/thiết kế (USPTO + Google). Không brand/đội/trường/nhân vật/lyrics.
- 🤖 **KHÔNG** nối tự động hoá vào tài khoản Etsy/Seller Central. Mọi thao tác chạm tài khoản = người thật, thủ công.
- ✅ **Data-driven, trung thực:** thiếu dữ liệu thì nói thiếu, không bịa "GO".

---

## Nhịp làm việc tuần (giữ đơn giản)

- **T2 — Nghiên cứu:** thả 1–3 file (Etsy/YTrends + supplier/pinterest) → Winner Finder → chọn 3 GO.
- **T3 — Thiết kế:** design + đặt sew-out cho cái qua cổng.
- **T4 — Listing:** Launch Kit → dán vào Etsy (đăng tay), chạy profit gate.
- **T5 — Tối ưu:** đọc Stats, áp bảng "triệu chứng → sửa" cho listing đang chạy.
- **T6 — Marketing:** 3–5 pin Pinterest + 1 video ngắn cho top listing.

---

## Cập nhật code lên dashboard (chỉ chủ shop)

Từ máy có repo `D:\Claude\22etsy-agent`:

```
git add -A ; git commit -m "update" ; git push
ssh -p 55317 etsy@51.79.200.65 "cd ~/etsy-agent && git fetch origin && git reset --hard origin/main && find . -type d -name __pycache__ -prune -exec rm -rf {} + && .venv/bin/python -m compileall -q src && sudo systemctl restart etsy-web && sleep 2 && systemctl is-active etsy-web"
```

In ra **`active`** = đã lên. Mở https://etsy.theglobalserviceteam.site (Ctrl+F5).
`push-to-vps.ps1` là **đồng bộ DỮ LIỆU** (report/keyword), **không** deploy code.
