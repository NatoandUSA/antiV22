# 📖 Hướng dẫn sử dụng công cụ (How to Use) — V37

> Tài liệu **nội bộ** cho team (tiếng Việt). Giải thích **mọi khu vực**, **mọi điểm số**,
> **mọi bước**, và **vì sao** công cụ quyết định như vậy. Đọc 1 lần để hiểu — sau đó chỉ cần
> nhìn trang chủ là làm được.
>
> 🔒 Công cụ **KHÔNG BAO GIỜ tự đăng**. Nó chỉ chuẩn bị dữ liệu, điểm số, nội dung. **Người thật**
> bấm đăng thủ công trên Etsy. Listing viết **tiếng Anh**; tài liệu này **tiếng Việt**.

## Mục lục

[TOC]

---

## 0. Sơ đồ tổng quan — đọc cái này trước

Trang chủ giờ là một **bảng 9 bước**. Đi từ trái sang phải:

```
🎯 BUILD QUEUE (mở mỗi ngày)
① FEED → ② RANK → ③ PATTERN MINER → ④ KEYWORD LAB → ⑤ RE-RANK
                                                        │
⑨ LEARN ← ⑧ ADS ← ⑦ PHOTO ← 🎨 DESIGN SKILL BRIDGE ← ⑥ BUILD ←┘
```

Ý tưởng lõi: **Inbox xếp hạng NHIỀU LỚP** — Cổng rủi ro (L0) → Bằng chứng bán thật trên
Etsy (L1) → Điểm thị trường (L2) → **Hành động cuối** (Build/Confirm/Review/Watch/Skip/
Blocked). Niche **đang bán thật** đứng trên niche chỉ đẹp trên giấy; keyword rủi ro/quá
rộng **không bao giờ** hiện "Build".

---

## 1. Công cụ này để làm gì?

Biến dữ liệu nghiên cứu (thả file) thành: **winner được xếp hạng → gói listing đầy đủ → kế hoạch ads →
vòng học từ đơn bán thật**. Nó **không** đụng vào tài khoản Etsy — bạn là cầu nối duy nhất để đăng.

---

## 2. Thanh điều hướng trên cùng

Mọi trang có: **Home · 🎯 Build · Research · Design · Launch Kit · Review/Team · Guide**. Nhảy giữa các bước không cần về trang chủ. **🎯 Build** là nút mở đầu mỗi ngày (xem mục dưới).

---

## ⭐ 2.5 🎯 BUILD QUEUE — mở đầu tiên mỗi ngày (`/build-queue`)

Kho keyword có hơn **1.000 dòng** nhưng chỉ khoảng **5% là "vàng"**. Build Queue làm sẵn việc lọc: bạn **không** phải cuộn cả kho — nó đưa lên đúng vài chục dòng đáng làm.

**Nó hiện gì:**

- Chỉ keyword **PROVEN** (đã chứng minh: có listing + views + doanh thu + conversion thật). Dòng rỗng (empty) bị giấu — làm trên dòng rỗng là **đoán mò**.
- Xếp hạng bằng **Build Score (0–100)** = trộn cầu (views) + conversion + giá + momentum + ít cạnh tranh. Cao = thắng nhanh & an toàn hơn.
- Cờ **⚠ verify TM** ở keyword nghi nhãn hiệu; keyword rủi ro cao (HIGH) đã bị loại sẵn.

**Cách dùng (mỗi sáng):**

1. Mở **🎯 Build Queue**. Đọc dòng tóm tắt: bao nhiêu proven / empty / cần làm / đã xong.
2. Đọc bảng từ **Build Score cao → thấp**. Chọn 3–5 dòng cho hôm nay.
3. Thấy **⚠** → tra nhãn hiệu (tmsearch.uspto.gov) trước.
4. Bấm **🎨 Design** (mổ xẻ + thiết kế gốc) hoặc **🚀 Kit** (gói listing đầy đủ) — keyword điền sẵn.
5. Làm xong / đã giao → bấm **✓** để chuyển xuống "Done" (không ai làm trùng).
6. Định kỳ mở **🧹 Base maintenance → Archive empty keywords** để dọn dòng rỗng ra khỏi kho (khôi phục được).

> Build Queue là **lối tắt**: có dòng ngon thì làm luôn, không bắt buộc chạy hết ①→⑨. Quy trình 9 bước bên dưới dành cho nghiên cứu sâu và tìm winner mới.

---

## 3. ① CAPTURE — thả file, tool tự đưa về đúng chỗ

Trên trang chủ, bước ① có **ô kéo–thả**. Kéo **1 hoặc nhiều** file CSV/JSON vào (hoặc bấm để chọn).
Có ô chọn **nguồn**; để **Tự nhận diện (Auto-detect)** là được. Nhiều file được **gộp + khử trùng lặp**.

**Thả loại nào → đi đâu:**

| Bạn thả | Cột đặc trưng | Tool đưa tới |
|---|---|---|
| **Etsy / YTrends keyword** | có `Keyword` + `Views` + `Competition` | 🏆 **Winner Finder** |
| **Etsy listings / spy** | có `title`, `sold`, `tags` (KHÔNG có cột keyword) | 🕵️ **Etsy Spy** (rút keyword từ title) |
| **Supplier 1688/Alibaba** | có `reorder`, `MOQ`, `sold`, `supplier` | 🏭 **Supplier Trend Finder** |
| **Pinterest** | có `pin_id` / `title_or_desc` / `saves` | 📌 **Pinterest Trend Finder** |
| **Amazon Xray (Helium 10)** | có `Search Volume` / `Competing Products` | 🏆 Winner Finder (nhãn **tham khảo**) |

Sau khi thả, tool tự chuyển bạn tới đúng trang. Dòng **"Last import: N rows · X phút trước"** dưới ô cho biết
đang dùng dữ liệu gì.

> **Extension 22Etsy Exporter v2.6** — không cần lưu file:
> - **↓ Grab all**: tự cuộn trang để lấy **tối đa** số dòng (Pinterest/Alibaba lấy hàng trăm thay vì ~30).
> - **Multi-page batch** (Etsy/Amazon phân trang): bấm **+ Add page** ở mỗi trang → **Batch CSV** / **Send batch** gộp tất cả thành 1 file, tự khử trùng lặp. Bạn tự bấm sang trang; extension không tự phân trang.
> - **Send to agent** hoạt động trên **mọi site**, tự route theo cột.

**Đọc bảng "Recent import events" (`/kw-history`) cho đúng — cột kết quả:**

| Bạn thấy | Nghĩa là |
|---|---|
| **+N new kw** | N keyword MỚI thêm vào kho |
| **N updated** | Gửi LẠI bảng keyword cũ → làm mới số thị trường (đúng, nên làm — không phải "hỏng") |
| **N leads** | Dòng listing/spy (Etsy/Amazon/Pinterest...) đã lưu vào lane spy — hữu ích, chỉ là **không phải keyword** |
| **—** | Không có gì vào (mới cần kiểm tra) |

> Gửi file **listing** thấy "leads" là **đúng**. Chỉ bảng **keyword** (YTrends) mới cộng "new kw". Gửi lại bảng keyword cũ để cập nhật giá/cầu → hiện "updated".

---

## 4. ② RANK — Opportunity Inbox (`/inbox`) — xếp hạng NHIỀU LỚP

Trang này lấy dữ liệu keyword YTuong thật và đưa **từng keyword qua các lớp**, rồi hiện
**Hành động cuối** (Final Action), không phải một con số trần.

**Đọc bảng (trái → phải):**

- **Etsy proof:** 🏆 PROVEN / 🟢 SELLING nếu có export Alura/EverBee (đơn bán thật) —
  hàng có bằng chứng bán thật xếp lên đầu. Trống = chưa có export.
- **Product-fit:** loại từ khoá (POD/Embroidery/Theme-needs-product/Broad seed/Policy…).
- **Final action:** 🚀 Build now · 🔍 Confirm first · 🚩 Review · 🟡 Watch · ⛔ Skip · 🚫 Blocked.
- **Market signal:** GO ≥ 80 · CONDITIONAL 65–79 · WATCH 50–64 · SKIP < 50 — **mô hình
  giải thích được** (demand · competition · conversion · momentum, dữ liệu thật + trọng số
  ta chọn). Đây là **một lớp**, không phải toàn bộ quyết định.
- Cột **Do**: đúng nút cho hành động — Build → Launch Kit; Confirm/Pattern → Pattern Miner;
  Review → xem lại; Watch → kiểm tra.
- **Cổng chạy TRƯỚC điểm:** trademark → Blocked; tên shop → Skip; theme/seed rộng → chặn
  ở Confirm; policy → Review. Nên keyword rủi ro/rộng **không bao giờ** ra "Build".

> 💡 **Bật Etsy proof:** thả CSV **Product Research của Alura/EverBee** (đơn bán + doanh
> thu + tuổi listing) → chọn nguồn *"Alura/EverBee products"*. Inbox hiện tier PROVEN/SELLING.

**Nếu bảng trống:** file bạn thả không có cột keyword + competition (ví dụ file listings). Dùng đúng lane
(Etsy Spy) hoặc thả file YTrends keyword.

---

## 5. ③ PATTERN MINER — mổ winner để biết VÌ SAO thắng

Từ hàng **Confirm first** ở Inbox (hoặc lane Etsy Spy): mổ 5–10 listing đang thắng của 1 keyword.

- Lấy top listing: ytuong.me "Hot" hoặc Etsy search + overlay HeyEtsy (đủ sold/revenue/tags) → CSV / Send to agent.
- Đọc: từ khoá tiêu đề hay lặp · **từ trong 40 ký tự đầu** · cấu trúc title · khoảng giá · % cá nhân hoá/gift/video · **khe hở**.
- Ghi lại **seed keyword** + ít nhất 1 khe hở khai thác được (vd: ít listing có video, ít ai theo chuyên khoa).

> Học **cấu trúc + khe hở** rồi tự viết mới — KHÔNG copy title/art/mockup của đối thủ.

---

## 6. ④ KEYWORD LAB — sinh keyword mới từ mẫu thắng (`/keyword-lab`)

Từ seed, sinh keyword mới theo người mua lân cận + biến thể — không đoán bừa.

- Nhập seed. Tool sinh keyword theo chuyên khoa / dịp / biến thể sản phẩm.
- Tick các keyword muốn giữ → bấm **MỘT nút** "➕ Add SELECTED to Inbox & re-rank" (cả lô ≤20, lưu vào keyword_data.csv + re-rank 1 lần). KHÔNG bấm từng cái.
- Ưu tiên keyword **HẸP** hơn (chuyên khoa): cạnh tranh thấp, buyer rõ, dễ cá nhân hoá sâu.

---

## 7. ⑤ RE-RANK — keyword mới quay lại Inbox

Keyword mới xuất hiện lại trong Inbox với Hành động cuối riêng.

- So sánh: ưu tiên keyword **HẸP** + (lý tưởng) có Etsy Proof.
- Chốt **1 winner** để đưa vào Launch Kit. Chưa lên BUILD_NOW là bình thường — đưa qua Launch Kit ở dạng nháp và bổ sung bằng chứng.

---

## 8. ⑥ BUILD — Launch Kit (`/launch-kit`)

1 winner → **mọi thứ trên một trang**:

1. **Verdict & winner score** (kèm cảnh báo trademark/SKIP).
2. **Beat competitors** — khe hở **đo được**, lớn nhất trước (thiếu cá nhân hoá, title yếu, thiếu tag, video…).
3. **Listing draft** — title (keyword trong 40 ký tự đầu), 13 tag, mô tả, cá nhân hoá, lợi nhuận. **Đây là nơi tạo listing cuối** (route-aware: hàng thêu → "stitched", hàng in → "printed").
4. **Photo prompt set** — **12 slot ảnh**, mỗi slot có prompt sẵn. Slot **📸 SHOOT THIS** = shot brief để chụp thật (hero, macro mũi chỉ, số đo, sew-out) — ảnh đăng phải là ảnh thật.
5. **Etsy Ads plan** — ngân sách, **breakeven ACOS từ phí Etsy thật**, phủ tag, luật đọc/giết 2 tuần.
6. **Checklist launch** — có link **ghi nhận đơn bán điền sẵn**.

Công cụ lẻ: `/draft-listing`, `/photo-brief`, `/ads-plan`, `/edge` (Beat competitors), `/should-sell`.

---

## 9. 🎨 DESIGN SKILL BRIDGE — ảnh mẫu → ChatGPT Skill → listing_seeds (`/design-skill-bridge`)

Thay cho Design Analyzer cũ. **Chạy thủ công, không gọi API.** Luồng:

1. 22etsy tạo **Skill Pack** (điền keyword/target product/mode/placement + Etsy URL + HeyEtsy evidence) → **Create Skill Pack**.
2. Mở **ChatGPT Skill (Etsy POD Redesign V8.1)** → upload ảnh/evidence + dán prompt → chạy.
3. Copy **RESULT_JSON** ở cuối câu trả lời → dán vào **Import & validate** ở 22etsy.
4. Validate PASS → **Owner/Manager duyệt** (RED IP = bỏ; YELLOW = confirm trước).
5. Sau khi duyệt → **Send listing_seeds to Launch Kit**.

> Skill chỉ trả **listing_seeds** (target product, buyer, main keyword, vocabulary, ràng buộc sản xuất) — **KHÔNG** phải listing cuối. **Launch Kit** mới tạo title/tag/mô tả. Kết quả là **CANDIDATE** cho tới khi owner duyệt; mọi bản xem trước ghi **DRAFT ONLY — DO NOT PUBLISH**. Ảnh mẫu chỉ để hiểu cấu trúc + hook; KHÔNG giữ chữ/typography/bố cục/màu của đối thủ.

---

## 10. ⑦ PHOTO — bộ ảnh (Photo Studio, 12 slot)

- Slot đồ hoạ (size chart, color chart, how-to-order): dùng prompt AI có sẵn.
- Slot **📸 SHOOT THIS** — hero, macro mũi chỉ, số đo, sew-out — dùng shot brief để **chụp thật**, tự review trước khi đăng.
- Ảnh 1 (hero): 4:3 / 5:4, contrast cao, text đọc được ở thumbnail; thêm 1 video 15–25s.

> AI chỉ cho mockup/đồ hoạ. Hero/macro/số đo/sew-out = ảnh thật — luật vàng, không du di.

---

## 11. ⑧ ADS — kế hoạch tay, đọc theo Day 3/7/14

1. Lấy **breakeven ACOS** Launch Kit tính sẵn từ phí thật.
2. Bật Etsy Ads **$1–3/ngày** (ưu tiên listing đã có tín hiệu organic).
3. Đọc & quyết theo mốc: Day 3 đọc · Day 7 ROAS ≥3 tăng / 1.5–3 tinh chỉnh / <1 tắt · Day 14 có lợi nhuận + đủ năng lực → SCALE.

---

## 12. ⑨ LEARN — vòng học (`/feedback`)

Bán được thì ghi ngay: keyword, tag, mode, giá, số đơn (Launch Kit có link **điền sẵn**).

- Mỗi đơn → nâng điểm winner của niche đó + tag liên quan → **lần sau tự lên hạng** (hiện ✔N).
- Tool gợi ý **GIỮ / SỬA / GIẾT / SCALE** theo Ngày 3 / Ngày 7.
- Winner thắng → nhân bản concept ra 10–20 biến thể. **Không ghi feedback = tool "mù"**, mọi thứ mãi ở WATCH.

---

## 13. Các "lane" khác từ ô Capture (bổ trợ)

- 🏭 **Supplier Trend Finder** (`/supplier-trends`) — nhà máy đẩy mạnh = cầu **đi trước**. Đối chiếu Etsy: 🟢 OPEN / 🟡 MEDIUM / 🔴 CROWDED. Dòng **★** = supplier nóng **và** Etsy còn thoáng = ngon nhất.
- 📌 **Pinterest Trend Finder** (`/pinterest-trends`) — saves cao = cầu đang lên (đi trước Etsy nhiều tuần).
- 🕵️ **Etsy Spy** (`/etsy-spy`) — thả file listing đối thủ → rút keyword hay lặp lại (coi chừng bão hoà).
- 🅰️ **Amazon Xray** — chỉ **tham khảo**; cầu Amazon ≠ cầu Etsy, phải kiểm lại Etsy.

> Mọi lead là **manh mối cầu, chưa phải bằng chứng** — luôn xác nhận trên Etsy trước khi build.

---

## 14. Đăng bán — Manual Publish Gate (KHÔNG phải bước pipeline)

1. Design **stitch-safe** (≤6 màu chỉ, hình bold, chữ đọc được) → **sew-out/proof thật trước khi scale**.
2. `📋 Listing Analyzer` (`/grade`) + `💰 Profit Center` (`/profit`): chốt **≥ 35–40% NET**.
3. Người thật dán nội dung, đăng **3–5 biến thể** 1 concept. **Chỉ đăng khi mọi cổng đạt + Manager ký.**
4. Bật **Etsy Ads $1–3/ngày** để gom click.

---

## 15. Bảng điểm Cơ hội (0–100)

`Overall = Market 0.32 + Competition 0.28 + Opportunity 0.15 + Private 0.15 + Feasibility 0.10`

- **Market**: cầu (views/momentum/conversion). **Competition**: 100 − bão hoà.
- **Opportunity**: tín hiệu "vào ngay". **Private**: dữ liệu bán thật của shop (vòng học).
- **Feasibility**: sản xuất sạch được + rủi ro trademark.
- Thiếu **Market/Competition/Opportunity** → cap **WATCH**. Trademark **HIGH** → **SKIP**.

---

## 16. 4 cổng điểm quyết định (Launch Kit / Build Workspace)

**Can-we-win**, **Launch-ready**, **First-image**, **Offer-strength** — mỗi cổng 0–100. Tất cả phải đạt +
Manager ký thì mới **PUBLISH_READY**.

---

## 17. Quản lý công việc (Team) + "Ai đang làm gì"

Dùng khi chia việc: `✅ Confirm & Assign` → `🧭 Research Queue` → làm → `🔍 Review Queue` (Manager duyệt) → đăng tay.
**Manager desk** trên trang chủ tóm tắt: Imported today · In flight · To review · Ready to publish · Blocked ·
Day 3/7 due. `👥 Team` + `📅 Team Calendar` để giao việc & hạn chót.

---

## 18. Cổng đăng bán (Publish Gate)

Listing chỉ lên khi **mọi cổng cứng đạt** + **Manager ký** + **người thật bấm đăng**. Nút hiện "Save Draft"
cho tới khi PUBLISH_READY = true. `PUBLISH_AUTOMATION = false` — luôn.

---

## 19. Quy tắc vàng (BẮT BUỘC)

1. 🔒 Không tự đăng. Người thật đăng thủ công.
2. 🎯 Ảnh hero + macro mũi chỉ + số đo **phải ảnh thật**; AI chỉ mockup/đồ hoạ.
3. 🧵 Sew-out trước khi scale. Đo **lợi nhuận thật**, không đo doanh thu.
4. ⚖️ Kiểm trademark mọi cụm từ/thiết kế (USPTO + Google). Không brand/đội/trường/nhân vật/lyrics.
5. 🤖 Không nối tự động hoá vào tài khoản Etsy.
6. ✅ Thiếu dữ liệu thì nói thiếu — **không bịa "GO"**.

---

## 20. POD hay Embroidery? Chọn Product Mode

Chọn mode ở Command Center. **Embroidery**: hình bold, ít màu, không gradient/chi tiết nhỏ, chữ ngắn.
**POD**: in gần như mọi thứ, nhưng vẫn cần art nét, tương phản cao.

---

## 21. Sự cố thường gặp

- **Winner Finder trống** → file không có cột keyword+competition. Thả file YTrends keyword, hoặc dùng Etsy Spy.
- **Import sai lane** → chọn thủ công nguồn trong ô dropdown thay vì Auto-detect.
- **"Live data unavailable"** → server YTuong đang chậm/chặn; dùng fast lane (thả file) thay vì trang MCP.
- **Trang lỗi có `[file.py:dòng]`** → gửi dòng đó cho người quản trị để sửa nhanh.
