# 📖 Hướng dẫn sử dụng công cụ (How to Use) — V28

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

Trang chủ giờ là một **đường ống 5 bước**. Đi từ trái sang phải:

```
①CAPTURE → ②FIND WINNERS → ③BUILD → ④LAUNCH → ⑤LEARN
 (thả CSV)   (Winner Finder)  (Launch Kit)  (đăng tay)  (ghi đơn → học)
```

Ý tưởng lõi: **tìm keyword có "cầu cao × ít cạnh tranh", rồi launch trước khi Etsy bão hoà.**
"Cầu cao × ít cạnh tranh" cũng là chỗ **Etsy Ads rẻ nhất** và **lên top dễ nhất**.

---

## 1. Công cụ này để làm gì?

Biến dữ liệu nghiên cứu (thả file) thành: **winner được xếp hạng → gói listing đầy đủ → kế hoạch ads →
vòng học từ đơn bán thật**. Nó **không** đụng vào tài khoản Etsy — bạn là cầu nối duy nhất để đăng.

---

## 2. Thanh điều hướng trên cùng

Mọi trang có: **Home · Research · Import · Team · Review · Guide**. Nhảy giữa các bước không cần về trang chủ.

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

> **Extension "Send to agent"** (trên YTrends/Etsy/Pinterest) làm y hệt — không cần lưu file.

---

## 4. ② FIND WINNERS — Winner Finder (`/winners`)

Trang này lấy **import mới nhất** và xếp hạng theo góc **cầu cao × ít cạnh tranh**.

**Đọc bảng:**

- Cột **Winner** = điểm sweet-spot (trung bình nhân Demand × Competition-health). Cao = tốt CẢ HAI mặt.
- **Demand** (thanh dài = cầu cao) · **Saturation** (thanh ngắn = ít cạnh tranh, tốt).
- **✔N** sau keyword = **shop đã bán N đơn** niche này (vòng học nâng điểm — xem mục 8).
- **Verdict:** GO ≥ 80 · CONDITIONAL ≥ 65 · WATCH ≥ 50 · SKIP. Thiếu tín hiệu lõi → chỉ tối đa **WATCH**.
- Cuối trang: **Sharpest pick** → bấm **Build the full Launch Kit**.
- Bấm **+ Cross-check Google Trends** để xác nhận cầu ngoài Etsy cho top 12.

**Nếu bảng trống:** file bạn thả không có cột keyword + competition (ví dụ file listings). Dùng đúng lane
(Etsy Spy) hoặc thả file YTrends keyword.

---

## 5. ③ BUILD — Launch Kit (`/launch-kit`)

1 winner → **mọi thứ trên một trang**:

1. **Verdict & winner score** (kèm cảnh báo trademark/SKIP).
2. **Beat competitors** — khe hở **đo được**, lớn nhất trước (thiếu cá nhân hoá, title yếu, thiếu tag, video…).
3. **Listing draft** — title (keyword trong 40 ký tự đầu), 13 tag, mô tả, cá nhân hoá, lợi nhuận.
4. **Photo prompt set** — 10 slot ảnh + prompt AI. **📸 REAL PHOTO = phải ảnh thật** (hero, macro mũi chỉ, số đo).
5. **Etsy Ads plan** — ngân sách, **breakeven ACOS từ phí Etsy thật**, phủ tag, luật đọc/giết 2 tuần.
6. **Checklist launch 9 bước** — có link **ghi nhận đơn bán điền sẵn**.

Công cụ lẻ (nếu chỉ cần 1 phần): `/draft-listing`, `/photo-brief`, `/ads-plan`, `/edge` (Beat competitors),
`/should-sell`.

---

## 6. Các "lane" khác từ ô Capture

- 🏭 **Supplier Trend Finder** (`/supplier-trends`) — nhà máy đẩy mạnh = có cầu **đi trước**. Rút keyword từ
  title sản phẩm, chấm điểm theo **sold + reorder + số nhà cung cấp**, **đối chiếu Etsy**: 🟢 OPEN / 🟡 MEDIUM /
  🔴 CROWDED. Dòng **★** = supplier nóng **và** Etsy còn thoáng = ngon nhất.
- 📌 **Pinterest Trend Finder** (`/pinterest-trends`) — saves cao = cầu đang lên (đi trước Etsy nhiều tuần).
- 🕵️ **Etsy Spy** (`/etsy-spy`) — thả file listing đối thủ → rút keyword hay lặp lại (coi chừng bão hoà).
- 🅰️ **Amazon Xray** — chỉ **tham khảo** (Winner Finder gắn nhãn); cầu Amazon ≠ cầu Etsy, phải kiểm lại Etsy.

> Mọi lead là **manh mối cầu, chưa phải bằng chứng** — luôn xác nhận trên Etsy trước khi build.

---

## 7. ④ LAUNCH — đăng thủ công

1. Design **stitch-safe** (≤6 màu chỉ, hình bold, chữ đọc được) → **sew-out/proof thật trước khi scale**.
2. `📋 Listing Analyzer` (`/grade`) + `💰 Profit Center` (`/profit`): chốt **≥ 35–40% NET**.
3. Người thật dán nội dung, đăng **3–5 biến thể** 1 concept.
4. Bật **Etsy Ads $1–3/ngày** để gom click.

---

## 8. ⑤ LEARN — vòng học (`/feedback`)

Bán được thì ghi ngay: keyword, tag, mode, giá, số đơn (Launch Kit có link **điền sẵn**).

- Mỗi đơn → nâng điểm winner của niche đó + tag liên quan → **lần sau tự lên hạng** (hiện ✔N).
- Tool gợi ý **GIỮ / SỬA / GIẾT / SCALE** theo Ngày 3 / Ngày 7.
- Winner thắng → nhân bản concept ra 10–20 biến thể.

---

## 9. Bảng điểm Cơ hội (0–100)

`Overall = Market 0.32 + Competition 0.28 + Opportunity 0.15 + Private 0.15 + Feasibility 0.10`

- **Market**: cầu (views/momentum/conversion). **Competition**: 100 − bão hoà.
- **Opportunity**: tín hiệu "vào ngay". **Private**: dữ liệu bán thật của shop (vòng học).
- **Feasibility**: sản xuất sạch được + rủi ro trademark.
- Thiếu **Market/Competition/Opportunity** → cap **WATCH**. Trademark **HIGH** → **SKIP**.

---

## 10. 4 cổng điểm quyết định (Launch Kit / Build Workspace)

**Can-we-win**, **Launch-ready**, **First-image**, **Offer-strength** — mỗi cổng 0–100. Tất cả phải đạt +
Manager ký thì mới **PUBLISH_READY**.

---

## 11. Quản lý công việc (Team) + "Ai đang làm gì"

Dùng khi chia việc: `✅ Confirm & Assign` → `🧭 Research Queue` → làm → `🔍 Review Queue` (Manager duyệt) → đăng tay.
**Manager desk** trên trang chủ tóm tắt: Imported today · In flight · To review · Ready to publish · Blocked ·
Day 3/7 due. `👥 Team` + `📅 Team Calendar` để giao việc & hạn chót.

---

## 12. Cổng đăng bán (Publish Gate)

Listing chỉ lên khi **mọi cổng cứng đạt** + **Manager ký** + **người thật bấm đăng**. Nút hiện "Save Draft"
cho tới khi PUBLISH_READY = true. `PUBLISH_AUTOMATION = false` — luôn.

---

## 13. Quy tắc vàng (BẮT BUỘC)

1. 🔒 Không tự đăng. Người thật đăng thủ công.
2. 🎯 Ảnh hero + macro mũi chỉ + số đo **phải ảnh thật**; AI chỉ mockup/đồ hoạ.
3. 🧵 Sew-out trước khi scale. Đo **lợi nhuận thật**, không đo doanh thu.
4. ⚖️ Kiểm trademark mọi cụm từ/thiết kế (USPTO + Google). Không brand/đội/trường/nhân vật/lyrics.
5. 🤖 Không nối tự động hoá vào tài khoản Etsy.
6. ✅ Thiếu dữ liệu thì nói thiếu — **không bịa "GO"**.

---

## 14. POD hay Embroidery? Chọn Product Mode

Chọn mode ở Command Center. **Embroidery**: hình bold, ít màu, không gradient/chi tiết nhỏ, chữ ngắn.
**POD**: in gần như mọi thứ, nhưng vẫn cần art nét, tương phản cao.

---

## 15. Sự cố thường gặp

- **Winner Finder trống** → file không có cột keyword+competition. Thả file YTrends keyword, hoặc dùng Etsy Spy.
- **Import sai lane** → chọn thủ công nguồn trong ô dropdown thay vì Auto-detect.
- **"Live data unavailable"** → server YTuong đang chậm/chặn; dùng fast lane (thả file) thay vì trang MCP.
- **Trang lỗi có `[file.py:dòng]`** → gửi dòng đó cho người quản trị để sửa nhanh.
