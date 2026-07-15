# 🧭 Quy trình nhóm — từ ý tưởng đến listing (V28.1)

> **YTuong / HeyEtsy = engine NGHIÊN CỨU. Dashboard này = engine THỰC THI.**
> Ta không clone YTuong — ta **import** phát hiện từ YTuong rồi biến thành: task cho team,
> kiểm tra nhà cung cấp (NCC), bản nháp listing, brief thiết kế, duyệt cổng đăng, và học
> Ngày 3 / Ngày 7.
>
> 🔒 **KHÔNG BAO GIỜ tự đăng.** Listing chỉ lên sàn khi **PUBLISH_READY = true**, quản lý
> ký duyệt, và người thật bấm đăng **thủ công** trên Etsy.
> 📄 Tài liệu này viết **tiếng Việt** cho team; listing luôn viết **tiếng Anh**.

## Mục lục

[TOC]

---

## Sơ đồ đường ống (pipeline)

```
 [1] Tìm ý tưởng            📈 Trending · 💎 Opportunities · 📅 Seasonal
        │
 [2] Import                 📥 Import Center        → tạo candidate (giữ mode)
        │
 [3] Giao việc              🧭 Research Queue        → task + người phụ trách
        │
 [4] Build workspace        🛠️ Confirm & Assign      → Verdict + 8 điểm + Can-we-win
        │
 [5] NCC + [6] Đối thủ      Supplier · 🕵️ Spy        → cost/margin + khe hở thắng
        │
 [7] Design + [8] Listing   Design brief · 13 tag    → nháp (tiếng Anh)
        │
 [9] Duyệt                  🔍 Review Queue          → Manager: Duyệt/Sửa/Từ chối
        │   PUBLISH_READY = true + Manager ký
        ▼
[10] ✋ ĐĂNG THỦ CÔNG (Etsy) → [11] 📉 Feedback Ngày 3/7 → GIỮ/SỬA/BỎ/SCALE
```

> 🧭 **Điều hướng:** mọi trang có thanh trên cùng (Home · Research · Import · Team ·
> Review · Guide) — nhảy giữa các bước không cần về trang chủ.

---

## Các bước (theo đúng thứ tự)

| Bước | Vai trò | Hành động | Mục trên dashboard | Kết quả |
|---|---|---|---|---|
| 1 | Researcher | **Mở 📊 Daily brief trước** (danh sách đã chấm điểm + xếp hạng cho hôm nay), rồi đào thêm ở Trending / Opportunities / Hidden gems / Newest winners | 📊 Daily brief · 📈 Trending · 💎 Opportunities · 💠 Hidden gems · 📅 Seasonal | Ý tưởng (kèm **Opp score** + verdict) |
| **1b** | Researcher | **🔍 Page-1 scan + quy tắc 70% — LÀM TAY** (xem mục riêng bên dưới). **Chỉ import khi ≥70%** | Etsy page 1 + YTuong overlay | STRONG_ENTRY / POSSIBLE_ANGLE / ENTRENCHED |
| 2 | Researcher | **Import** phát hiện YTuong (dán URL hoặc gõ keyword) — chỉ sau khi 1b đạt | 📥 Import Center | Candidate (giữ **product mode**) |
| 3 | Researcher/Manager | Phân loại product-fit + **giao việc** (hạn mặc định 24h) | 🧭 Research Queue | Task nghiên cứu (có người phụ trách) |
| 4 | Seller | **Build Workspace** (mode **giữ nguyên**) → đọc Verdict | 🛠️ Workspace | Quyết định GO / CHECK / NO |
| 5 | Seller | Kiểm tra NCC — bấm **🏭 Open Supplier panel** → **Match** (gõ sản phẩm), xác nhận URL + giá gốc/ship. **Không cần terminal** | Workspace → Supplier panel | Trạng thái NCC + margin (đã trừ phí + đổi tiền) |
| 6 | Researcher | Soi đối thủ; đọc **🎯 Biggest gaps to exploit** + **Trend phase**; **xác nhận cửa hàng LÀM TAY**: mở order chart 3–5 shop top → ≥3 shop steady/growing = CONFIRMED | 🕵️ Spy / Workspace + YTuong | Khe hở lớn nhất + xác nhận tiền thật |
| 7 | Designer | Kiểm **Producibility** (thêu được không) → ảnh đầu + design prompt | Workspace → Design | Task thiết kế (mẫu thêu-sạch) |
| 8 | Seller | Dựng nháp listing: title + 13 tag + mô tả (**tiếng Anh**) | Workspace → Listing | Nháp listing |
| 9 | Manager | Duyệt **Publish Gate** (đọc báo cáo nhân viên) | 🔍 Review Queue | Duyệt / Cần sửa / Từ chối |
| 10 | Seller | Đăng **THỦ CÔNG** trên Etsy (chỉ khi được duyệt) | Etsy (ngoài công cụ) | Listing lên sàn |
| 11 | Seller / Manager | Nhập số Ngày 3 + Ngày 7 | 📉 Sales Feedback | Giữ / Sửa / Bỏ / Scale |

---

## Ai làm gì — theo vai trò

- **Researcher:** bước 1–3 và 6 — tìm ý tưởng, import, giao việc, soi đối thủ.
- **Seller:** bước 4–5, 8, 10–11 — dựng workspace, chốt NCC, dựng listing, đăng, nhập feedback.
- **Designer:** bước 7 — ảnh đầu + thiết kế theo brief.
- **Manager:** bước 9 (+ giám sát toàn bộ) — duyệt cổng đăng, ký PUBLISH_READY.

> 👥 **"Who's on what" (Team Tasks):** quản lý xem mỗi người đang gánh gì (To-do / Đang làm
> / Trễ hạn / Chờ duyệt) trong 1 liếc. Ô **"In flight"** ở Manager Desk đếm việc đang chạy.

---

## 🔍 Page-1 Freshness — quy tắc 70% (LÀM TAY, trước khi Import)

> Nguồn: founder ytuong.me (07-2026). **Page 1 của Etsy = sự thật của thị trường** —
> thuật toán đã xếp sẵn cái gì đang bán được. Không cần soi 100 trang; vài trang đầu là đủ.

**Bước 1 — Quét Page 1 (~15 phút/niche)**
- Search từ khóa trên Etsy → nhìn **page 1** (60–80 listing)
- Rê từng listing qua YTuong/HeyEtsy → ghi: **ngày tạo** + **có bán gần đây không**

**Bước 2 — Quy tắc 70% (cổng chặn)**

`freshness_ratio = (số listing tạo ≤ 6 tháng VÀ đang bán) / (tổng listing page-1 đã soi)`

| Tỉ lệ | Kết luận | Làm gì |
|---|---|---|
| **≥ 70%** | STRONG_ENTRY | Sang bước 3 → rồi Import |
| **40–69%** | POSSIBLE_ANGLE | Chỉ vào khi có **góc hẹp hơn** |
| **< 40%** | ENTRENCHED | **Bỏ** — shop cũ đang giữ chặt |

**Bước 3 — Xác nhận cửa hàng (3–5 shop top)**
- Mở **order chart** từng shop → ghi steady / growing / declining
- **≥ 3 shop steady-or-growing → CONFIRMED**, được vào niche. Ghi 1 dòng/shop vào competitor audit

**Tư duy (quan trọng):**
- Ngách to + nhiều shop đang thắng = **BẰNG CHỨNG CÓ TIỀN**, không phải "trễ rồi"
- 1 shop không ôm hết nhu cầu mỗi ngày — luôn còn chỗ cho **sản phẩm tốt hơn, ảnh tốt hơn, offer tốt hơn**
- **Đừng thấy "saturation = high" rồi bỏ.** Hỏi đúng câu: *người mới có lên được không?* (freshness)

**⚠️ Kỷ luật lợi nhuận (bắt buộc):** quy tắc 70% chỉ xác nhận **CẦU**, không nói gì về **biên
lời của mình**. Niche CONFIRMED vẫn phải qua **cổng lợi nhuận**: net ≥ **30%** sau phí Etsy
(~13%) + **đổi tiền 2.5%** + giá vốn + ship. *Cổng cầu mở cửa; cổng lợi nhuận quyết định có
bước vào hay không.*

### Vì sao bước này PHẢI làm tay (công cụ KHÔNG tự động được)

| Lý do | Chi tiết |
|---|---|
| **Dữ liệu không có ngày tạo** | `top_listings(keyword)` của chỉ số YTrends trả về title / giá / doanh thu / tag / đã bán / sold_24h / conversion / favorites / views — **KHÔNG có ngày tạo listing**. Không có tử số ("≤ 6 tháng") thì không tính được tỉ lệ |
| **Cỡ mẫu quá nhỏ** | Phương pháp cần **60–80 listing** của page 1. Chỉ số chỉ trả **1–8 listing** cho 1 từ khóa → tính "70%" trên 1–8 mẫu là vô nghĩa |
| **"Page 1" là của Etsy, không phải của chỉ số** | Muốn đúng page-1 thật thì phải **cào trang search Etsy** → **vi phạm luật sàn** + quy tắc cứng của mình (không tự động vào Etsy). API chính thức của Etsy cũng không có "page-1 kèm ngày tạo + doanh số gần đây" |
| **Order chart của shop không có API** | Bước 3 phải mở biểu đồ đơn hàng từng shop trên YTuong — không endpoint nào trả về cái đó |
| **Nguyên tắc không bịa số** | Nếu ép tự động mà thiếu ngày tạo, ô đó sẽ **luôn hiện "pending"** → một ô chết vô dụng. Thà **không có** còn hơn **đoán bừa** |

> ✅ **Cái công cụ LÀM ĐƯỢC (và đã có sẵn):** chỉ số freshness **tổng hợp theo niche** —
> `new_entrant_rate` (tỉ lệ người bán mới vào), `avg_listing_age_days` (tuổi TB listing),
> saturation, seller concentration — đều hiện trong Workspace. **Máy lọc thô → người quét
> page-1 để chốt.** Máy sàng nhanh, người xác nhận tinh.

---

## Product mode giữ xuyên suốt

✅ **Product mode (POD / Embroidery) được giữ nguyên** từ Import → Research Queue → Build
Workspace → NCC → Listing → Design → Publish Gate. Không bị nhầm sang POD khi đang làm hàng
thêu. Mode mặc định là **Embroidery**; chọn POD/Both bằng 1 cú bấm.

---

## Cổng đăng bán (Publish Gate) — chỉ **true** khi đủ TẤT CẢ

NCC đã xác nhận · **đúng product mode** · đạt mục tiêu lợi nhuận · audit đối thủ xong · có
kế hoạch ảnh đầu · **đúng 13 tag sạch** · không dính trademark · không còn `[placeholder]` ·
Manager ký duyệt · điểm **Can-We-Win** + **Launch-Readiness** đạt.

→ Thiếu bất kỳ mục nào: **DRAFT ONLY — KHÔNG ĐĂNG.** Công cụ hiển thị đúng danh sách mục
còn thiếu (`FAILED_PUBLISH_CHECKS`), không bao giờ báo "sẵn sàng" khi chưa đạt.

---

## Quy tắc vàng

🔒 Không tự đăng — luôn thủ công, cần Manager ký · ✅ Mọi thứ là nút bấm (team không cần
terminal) · 🕕 Dữ liệu tự làm mới mỗi ~6 giờ trên server · 🏷️ Listing luôn viết **tiếng
Anh** (khách Etsy là Anh–Mỹ) · 👀 Chỉ học **cấu trúc** đối thủ — tuyệt đối không sao chép
ảnh / title / tag.
