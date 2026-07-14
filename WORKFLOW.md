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
| 1 | Researcher | Tìm cụm sản phẩm / từ khóa đang lên | 📈 Trending · 💎 Opportunities · 📅 Seasonal | Ý tưởng |
| 2 | Researcher | **Import** phát hiện YTuong (dán URL hoặc gõ keyword) | 📥 Import Center | Candidate (giữ **product mode**) |
| 3 | Researcher/Manager | Phân loại product-fit + **giao việc** (hạn mặc định 24h) | 🧭 Research Queue | Task nghiên cứu (có người phụ trách) |
| 4 | Seller | **Build Workspace** (mode **giữ nguyên**) → đọc Verdict | 🛠️ Workspace | Quyết định GO / CHECK / NO |
| 5 | Seller | Kiểm tra NCC (URL, giá gốc, ship, chất liệu, thời gian) | Workspace → Supplier | Trạng thái NCC + margin |
| 6 | Researcher | Soi + audit đối thủ; xem bảng **Can we win** | 🕵️ Spy / Workspace | Khe hở để thắng |
| 7 | Designer | Ảnh đầu (first image) + design prompt | Workspace → Design | Task thiết kế |
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
