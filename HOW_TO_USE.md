# 📖 Hướng dẫn sử dụng công cụ (How to Use) — V28.1

> Tài liệu **nội bộ** cho team (tiếng Việt). Giải thích **mọi khu vực**, **mọi điểm số**,
> **mọi bước**, và **vì sao** công cụ quyết định như vậy. Đọc 1 lần để hiểu — sau đó chỉ
> cần bấm nút.
>
> ⚠️ **Nguyên tắc bất di bất dịch:** công cụ **KHÔNG BAO GIỜ tự đăng bài lên Etsy**.
> Mọi listing chỉ là **bản nháp (draft)** cho tới khi người thật bấm đăng thủ công.
> 🏷️ **Title / tag / mô tả listing luôn viết TIẾNG ANH** (khách Etsy là người Anh–Mỹ).
> Riêng **tài liệu team này** viết tiếng Việt cho dễ hiểu.

---

## Mục lục

[TOC]

---

## 0. Sơ đồ tổng quan — đọc cái này trước

**YTuong/HeyEtsy = engine NGHIÊN CỨU. Dashboard này = engine THỰC THI.** Ta không clone
YTuong; ta **import** phát hiện rồi biến nó thành kế hoạch làm việc có kiểm soát:

```
   YTuong / HeyEtsy  (nghiên cứu thị trường)
            │  copy link / keyword
            ▼
   📥 IMPORT CENTER ──────────────► tạo "candidate" (giữ nguyên Product mode)
            │                         + tự chấm product-fit + trademark
            ▼
   🧭 RESEARCH QUEUE ─────────────► giao việc cho nhân viên · theo dõi trạng thái
            │  bấm "Build workspace"
            ▼
   🛠️ CONFIRM & ASSIGN / WORKSPACE ─► Verdict + 8 điểm + Can-we-win + listing + design
            │                          (bản nháp — KHÔNG tự đăng)
            ▼
   🔍 REVIEW QUEUE ──────────────► Manager đọc báo cáo → Duyệt / Cần sửa / Từ chối
            │  chỉ khi PUBLISH_READY = true + Manager ký
            ▼
   ✋ ĐĂNG THỦ CÔNG trên Etsy  (người thật bấm đăng)
            │
            ▼
   📉 FEEDBACK Ngày 3 / Ngày 7 ───► GIỮ / SỬA / BỎ / SCALE (công cụ tự học)
```

**Dữ liệu từ đâu?** Mọi số liệu (view, số listing, giá, conversion…) lấy **trực tiếp từ
chỉ số YTrends của Etsy**, tự làm mới **mỗi ~6 giờ** trên server. Không bịa số, không dùng
log tìm kiếm của nhân viên. Nguồn nào không có → hiện `SOURCE_NOT_AVAILABLE` (không giả).

---

## 1. Công cụ này để làm gì?

| Câu hỏi của bạn | Công cụ trả lời bằng |
|---|---|
| Nên bán sản phẩm/từ khóa này không? | Điểm **Verdict** (GO / CÓ ĐIỀU KIỆN / KHÔNG) + 8 điểm số |
| Thị trường đang hot cái gì? | 📈 **Trending** · 💎 **Opportunities** |
| Đối thủ đang làm gì, làm sao thắng? | 🕵️ **Spy + Reverse Engine** + bảng **Can we win** |
| Viết title + tag + mô tả thế nào? | **Listing builder** trong Workspace (13 tag chuẩn SEO) |
| Sản phẩm này có lời không? | 💰 **Profit Center** (đã trừ phí Etsy) |
| Ai làm việc gì, tiến độ ra sao? | 📋 **Team Tasks** (bảng "Ai đang làm gì") · 📅 **Calendar** |

---

## 2. Thanh điều hướng trên cùng (MỚI)

Trước đây mỗi trang chỉ có nút **← Home**, nên đổi trang phải quay về trang chủ. **Giờ mọi
trang đều có 1 thanh điều hướng chung ở trên cùng** — nhảy thẳng giữa các khu vực từ bất
kỳ đâu (kể cả trong trang Build Workspace):

```
🏠 Home   🧭 Research   📥 Import   📋 Team   🔍 Review   📖 Guide
```

- Khu vực **đang mở** được **tô đậm màu cam** để biết mình đang ở đâu.
- Thanh này **theo vai trò**: quản lý thấy **Team** + **Review**; nhân viên thấy **My Tasks**.
- Thanh **dính (sticky)** ở trên cùng — cuộn xuống vẫn thấy, đổi trang không cần cuộn lên.

---

## 3. Quy trình chuẩn — làm theo thứ tự

> ⚡ **Đường tắt hằng ngày (nhanh nhất):** dùng **✅ Confirm & Assign** ngay trang chủ —
> dán 1 niche từ YTuong → xem verdict (product-fit + trademark, tuỳ chọn cross-check
> Google/Pinterest/X) → **giao cho nhân viên** bằng 1 nút. Đủ cho phần lớn việc hằng ngày.
>
> 🧵 **Mode mặc định là Embroidery** (POD / Both vẫn 1 cú bấm).

| Bước | Việc làm | Ở đâu | Ai làm |
|---|---|---|---|
| 1️⃣ Tìm ý tưởng | Xem từ khóa đang lên / ngách ít cạnh tranh | Trending · Opportunities · Seasonal | Researcher |
| 🔍 **Page-1 scan (LÀM TAY)** | Quét page 1 Etsy + **quy tắc 70%** (≥70% mới import) + xác nhận order chart 3–5 shop. **Máy không làm được — xem WORKFLOW để biết vì sao** | Etsy + YTuong | Researcher |
| 2️⃣ Import | Dán URL/keyword → tạo candidate (giữ mode) — **chỉ khi page-1 scan đạt** | 📥 Import Center | Researcher |
| 3️⃣ Giao việc | Phân loại product-fit + giao cho nhân viên | 🧭 Research Queue | Researcher/Manager |
| 4️⃣ Quyết định | **Build workspace** → đọc Verdict + điểm | 🛠️ Workspace | Seller |
| 5️⃣ NCC + đối thủ | Kiểm tra nhà cung cấp + soi đối thủ | Workspace → Supplier/Spy | Seller/Researcher |
| 6️⃣ Listing + Design | Title + 13 tag + mô tả (nháp) + brief thiết kế | Workspace → Listing/Design | Seller/Designer |
| 7️⃣ Duyệt | Nộp bài + **báo cáo đã làm gì** → Manager duyệt | My Tasks → Review Queue | Staff → Manager |
| 8️⃣ Đăng (thủ công) | Chỉ khi **Publish-ready = yes** + Manager ký | Ngoài Etsy, bằng tay | Manager/Seller |
| 9️⃣ Học sau bán | Nhập số thực Ngày 3–7 → GIỮ/SỬA/BỎ/SCALE | 📉 Sales Feedback | Seller |

### 🔎 Ví dụ cụ thể: import 1 listing → làm bản Embroidery (mode GIỮ NGUYÊN)

Bạn thấy trên YTuong listing **"monogram tote bag"** bán chạy, muốn làm bản **thêu**:

1. **Trên YTuong:** copy link listing (hoặc chỉ cần nhớ keyword `monogram tote bag`).
2. **Vào 📥 Import Center** và điền: *Kind* = Product idea · *Source* = YTuong ·
   *Mode* = **Embroidery** (chọn tay để **ÉP** chế độ thêu) · *Value* = dán link **hoặc**
   gõ `monogram tote bag` · *Note* = "bán 500+, personalization yếu — mình thắng bằng
   monogram đẹp hơn" → bấm **Import → create candidate**.
3. **Kết quả:** candidate `monogram tote bag`, **product_mode = embroidery**, fit =
   **EMBROIDERY_FIT**, trạng thái `NEW_IDEA` → tự vào 🧭 **Research Queue**.
4. **Research Queue:** thẻ hiện keyword + nhãn **Embroidery** + link + nút **Build workspace**.
5. Bấm **Build workspace** → Workspace mở **đúng chế độ Embroidery** (logic NCC thêu, design
   prompt thêu, Publish Gate theo ràng buộc thêu). **KHÔNG** dùng giả định POD.

> ⚠️ Dán URL mà công cụ **không đọc ra keyword** → nó **không tạo candidate rác**, mà báo
> *"Could not extract a keyword… nhập keyword bằng tay"*. Cứ gõ keyword rồi import lại.

---

## 4. Mọi khu vực trên Dashboard

| Khu vực | Dùng để | Nhập gì | Nhận lại gì |
|---|---|---|---|
| ✅ **Confirm & Assign** | **Bắt đầu ở đây** — xác nhận nhanh 1 niche rồi giao việc | Dán/gõ 1 keyword (+ tuỳ chọn cross-check **Google · Pinterest · Reddit · X**) | Verdict **GO / CHECK / NO** + nút giao nhân viên |
| ⚡ **Command Center** | 1 từ khóa → cả bộ hồ sơ | Chọn **Product mode** + gõ từ khóa | Verdict, 8 điểm, listing, design, kế hoạch |
| 📥 **Import Center** | Import phát hiện YTuong/HeyEtsy/Etsy | Dán URL hoặc gõ keyword (+ mode) | Candidate vào Research Queue (**giữ mode**); bảng *Recently imported* có **cột Assigned** (ai đang phụ trách) |
| 🧭 **Research Queue** | Đường ống ý tưởng → duyệt đăng | Bấm **Build workspace** / giao task | NEW_IDEA → NCC → audit → design → nháp → duyệt → đăng; **mode giữ nguyên** |
| 📈 **Trending** | Từ khóa **đang lên** | Bấm (theo mode) | ~50 từ khóa rising + **cụm sản phẩm** |
| 💎 **Opportunities** | Ngách **ít cạnh tranh, cầu thật** | Bấm | ~50 ý tưởng "vùng ngọt" + cụm + cột **Opp score** |
| 📊 **Daily brief** (MỚI) | **Đọc đầu ngày** — danh sách nên làm hôm nay, đã chấm điểm + xếp hạng | Bấm (theo mode) | GO / CONDITIONAL trước, WATCH sau (kèm lý do + cái gì còn thiếu) + lịch mùa vụ 90 ngày |
| 💠 **Hidden gems** (MỚI) | Ngách **conversion cao + ít cạnh tranh** (bảng đầy đủ) | Bấm | Gem score, listings/sellers, L/S, conv, sold 24h, **Trend phase**, Opp score |
| 🆕 **Newest winners** (MỚI) | Listing **mới toanh mà đã bán chạy** — học GÓC ĐỘ, không copy | Bấm | Tuổi listing, perf, sold 24h, **vì sao nó hot**, tag mẫu |
| 🗂️ **Category intel** (MỚI) | Chọn **cả CATEGORY** đang thiếu người bán trước khi săn keyword | Bấm (sort) | Demand/Supply, revenue, conv, verdict ENTER / NICHE DOWN / AVOID. *Cần `YTRENDS_COOKIE` trong `.env` — hết hạn/thiếu thì trang báo thẳng kèm hướng dẫn lấy lại (1 phút), không bịa số* |
| 🕵️ **Spy + Reverse Engine** | Giải mã đối thủ | Từ khóa **hoặc link listing Etsy** | Ai thắng, playbook của họ, khe hở để thắng |
| 📅 **Seasonal calendar** | Lịch mùa vụ | Bấm | Ngày lễ sắp tới + **hạn chót launch** |
| 📝 **Listing Analyzer** | Chấm điểm listing | Dán title+tag+mô tả | Điểm SEO/Trust/Image + cổng duyệt |
| 🏪 **Saved shops / 📌 Saved listings** | Thư viện tình báo | Bấm **Auto-pull** | Shop mới bán chạy · listing trẻ đang thắng |
| 🏭 **Supplier panel** (MỚI) | Tìm + xác nhận NCC — **không cần terminal nữa** | Gõ tên sản phẩm → **Match**; hoặc Upload CSV / Sync catalog | Danh sách NCC khớp (điểm fit, giá gốc, link, trạng thái). Từ Workspace bấm **"🏭 Open Supplier panel"** là tới thẳng |
| 💰 **Profit Center** | Lời lỗ thật | Nhập giá bán, giá vốn, ship | P&L đã trừ phí Etsy, theo NCC |
| 🚀 **Launchpad** | Bảng theo dõi launch | Tự động | Ý tưởng → duyệt → Day-7 → scale/kill |
| 📊 **Market & keyword tracker** | Xu hướng theo thời gian | Thêm từ khóa theo dõi | Đang lên / xuống / ổn định |
| 👥 **Team** | Quản lý người + việc | — | Tasks, Calendar, Review, Feedback, Users |

---

## 5. Trang Confirm & Assign / Build Workspace — đọc kỹ (MỚI)

Đây là **trái tim** của công cụ, vừa được **thiết kế lại theo hướng "quyết định trước"**
(decision-first): thứ quan trọng nhất nằm trên cùng, chi tiết gấp lại để bấm mở khi cần.

**Bố cục từ trên xuống:**

```
┌──────────────────────────────────────────────────────────┐
│ VERDICT (kết luận lớn)  +  Next action (làm gì tiếp)       │  ← đọc trước
├──────────────────────────────────────────────────────────┤
│ Dải điểm nhanh: Overall · Can we win · Launch-ready ·      │  ← liếc là hiểu
│ First image · Offer · Publish-ready · TM                   │
├──────────────────────────────────────────────────────────┤
│ Thanh chip: Verdict · ① Decision · 🔬 Deeper · 🚦 Listing  │  ← nhảy nhanh trong trang
│              · 🎨 Design · ✅ Do next                        │
├──────────────────────────────────────────────────────────┤
│ ① THE DECISION (mở sẵn):                                   │
│    📊 Opportunity scores · 🏆 Can we win (1 bảng) ·         │
│    🔑 Market & keyword · 🛰️ Source confidence               │
├──────────────────────────────────────────────────────────┤
│ ▸ 🔬 Deeper analysis      (gấp lại — bấm để mở)             │
│ ▸ 🚦 Listing & supplier   (gấp lại)                         │
│ ▸ 🎨 Design               (gấp lại)                         │
│ ▸ ✅ Do next & export     (gấp lại — có nút Save + PDF)     │
└──────────────────────────────────────────────────────────┘
```

**Cách đọc (3 bước):**

1. **Đọc VERDICT + Next action** trước. Nó nói thẳng: làm ngay / test 2 listing / chờ /
   bỏ, kèm việc tiếp theo.
2. **Liếc dải điểm nhanh.** Điểm nào đỏ là điểm yếu cần xử lý (xem chi tiết ở ① Decision).
3. **Chỉ mở nhóm gấp khi cần** (Listing để lấy tag, Design để lấy prompt, Do next để Save/PDF).

**Vì sao đổi:** trang cũ dài ~20 mục, phải cuộn mãi. Giờ 4 mục ra quyết định mở sẵn, phần
còn lại 1 cú bấm — nhanh, sắc, tập trung vào **có nên làm không**.

**Bảng "Can we win" (đã gộp):** trước có 2 bảng trùng nhau; giờ **gộp 1 bảng**
`Lợi thế | Điểm | Cách mình thắng` + 1 dòng **"Our edge in one line"** tóm tắt.

### 🆕 3 công cụ quyết định mới trong Workspace

| Công cụ | Ở đâu | Nói gì | Dùng sao |
|---|---|---|---|
| 🎯 **Biggest gaps to exploit** (đo thật từ đối thủ) | Mục **🏆 Can we win** | KHÔNG còn điểm chung chung — công cụ **đo từ listing đối thủ thật**: bao nhiêu % đối thủ **không personalization**, **title cụt/rộng**, **giống clip-art**, **giá thấp còn chỗ premium**, niche **chưa bị khóa**… rồi **xếp hạng khe hở lớn nhất** kèm bằng chứng | Đánh vào khe hở #1 (điểm cao nhất) — đó là chỗ dễ thắng nhất của **riêng** ngách này |
| 🧵 **Producibility (thêu được không)** | Mục **🎨 Design** | Chấm 0–100 xem mẫu **có thêu sạch được không** (cờ đỏ: gradient, ảnh thật/photoreal, màu nước, nét mảnh, chữ nhỏ). **STITCH_SAFE / NEEDS_SIMPLIFYING / NOT_STITCH_SAFE** | Nếu **NOT_STITCH_SAFE** → đơn giản hóa mẫu **hoặc chuyển POD** trước khi giao designer. (POD in được gần như mọi thứ) |
| 📈 **Trend phase (đang lên hay đã đỉnh)** | Mục **🔑 Market** | Phân biệt **RISING** (còn tăng — vào sớm) với **PEAKED/PEAKING** (đã đỉnh/đang chững — cửa sổ đang đóng) | RISING → làm ngay; PEAKED → cân nhắc bỏ hoặc chỉ test nhỏ |

> 💰 **Số lời giờ chuẩn hơn:** mọi phép tính lợi nhuận đã **trừ thêm ~2.5% phí đổi tiền USD→VND**
> (shop trả về VND) và cổng đăng **bắt buộc biên lời ròng ≥ 30%** (mục tiêu 35–40%). Nên nếu
> "Profit target met" báo đỏ → **nâng giá / đổi NCC rẻ hơn / thêm personalization** để đạt biên.

---

## 6. Bảng điểm Cơ hội (0–100)

Mỗi ý tưởng được chấm 8 điểm; **Overall** là điểm tổng đã đánh trọng số.

| Điểm số | Nghĩa là gì | Tính từ đâu | Vì sao chọn chỉ số này | Bao nhiêu là tốt |
|---|---|---|---|---|
| **Overall Product** | Điểm tổng hợp | Demand 20% · Opportunity 20% · Competition 15% · Conversion 15% · SEO 10% · Trend 10% · Design 5% · Production 5% | Một con số so sánh nhanh nhiều ý tưởng | ≥ 60 đáng làm |
| **Demand** (Cầu) | Bao nhiêu người mua đang tìm | View thị trường/ngày = *view TB mỗi listing × tổng listing*, chia log | Cầu cao = có người mua sẵn, không phải tự tạo nhu cầu | ≥ 60 |
| **Competition** ⚠️ | Mức độ **dễ** chen chân | Chỉ số tập trung người bán (low≈82, medium≈55, high≈30) | **Điểm CAO = ÍT cạnh tranh = DỄ lên top** (ngược với tên gọi!) | ≥ 60 = dễ vào |
| **Opportunity** | Cầu thật + cạnh tranh thấp | Chỉ số opportunity của YTrends | "Vùng ngọt": có người mua mà chưa nhiều người bán | ≥ 60 |
| **SEO** | Từ khóa có hợp tối ưu không | Độ dài cụm (**3 từ = tốt nhất**, 1 quá rộng, 5+ quá hẹp) | Cụm 2–4 từ đúng cách khách gõ tìm | ≥ 75 |
| **Conversion** | % người xem → mua | Tỉ lệ conversion thực của ngách | Cầu cao vô ích nếu không ai chốt đơn | ≥ 70 |
| **Design Potential** | Còn "đất" cho thiết kế đẹp thắng | Cao hơn khi ngách **ít bão hòa** | Ngách ít đối thủ → thiết kế tốt dễ nổi bật | ≥ 70 |
| **Production Feasibility** | Dễ sản xuất theo mode | Theo **Product mode** (POD dễ nhất) | POD in gì cũng được; thêu kén mẫu | ≥ 70 |
| **Trend / Seasonality** | Đang lên hay đang nguội | **Momentum** + biến động thứ hạng tuần | Bắt trend đang lên, tránh trend đã đỉnh | ≥ 55 |

> 💡 **Mẹo:** đọc **Verdict** trước, rồi nhìn **điểm thấp nhất** — đó là chỗ cần sửa
> (dòng "Improve" nói cách sửa).

---

## 7. 4 cổng điểm quyết định

Ngoài 8 điểm cơ hội, Workspace còn 4 "cổng" trả lời câu hỏi cụ thể (hiện trên dải điểm nhanh):

| Cổng | Trả lời | Đạt khi | Nếu không đạt |
|---|---|---|---|
| 🏆 **Can we win** | Cùng data + AI, **vì sao TA vẫn thắng?** | ≥ 70 = khác biệt được | < 70 = "edge mỏng — chưa nên bán ngay" |
| 🚦 **Launch-readiness** | Đủ điều kiện launch chưa? | ≥ 85 = READY | Liệt kê đúng mục còn thiếu (NCC, ảnh, tag…) |
| 🖼️ **First-image** | Ảnh đầu có đủ mạnh để thắng? | ≥ 75 | Cải thiện ảnh hero trước khi đăng |
| 🎁 **Offer** | Gói chào hàng (bundle/personalization) đủ hấp dẫn? | ≥ 70 | Thêm set / gift-box / cá nhân hóa |

**Vì sao cần 4 cổng riêng:** điểm cơ hội nói *thị trường có tốt không*; 4 cổng nói *TA có
làm thắng được không* — hai câu hỏi khác nhau, cần tách bạch để quyết đúng.

---

## 8. Thuật ngữ quan trọng

| Thuật ngữ | Nghĩa | Vì sao quan trọng |
|---|---|---|
| **Momentum** | Tốc độ **TĂNG** gần đây (bán + tốc độ tăng view) | Cao = đang lên nhanh → **bắt sớm**. Là "gia tốc", không phải "độ lớn" |
| **Saturation** (Bão hòa) | Ngách quá nhiều người bán chưa | **Low** = còn chỗ (tốt); **High** = chật (khó thắng) |
| **Conversion rate** | % xem rồi mua | ~3% là bình thường trên Etsy |
| **Demand : Supply** | Tỉ lệ cầu / cung | > 1 = cầu > cung = cơ hội tốt |
| **Trademark (TM)** | Nhãn hiệu đã đăng ký (Disney, Pokemon, tên band…) | **OK** = an toàn · **CAUTION** = tự tra USPTO · **HIGH** = CẤM (bị gỡ shop) |
| **Publish-ready** | Đủ điều kiện đăng chưa | Chỉ **yes** khi mọi kiểm tra pass **và** Manager ký từng mục. Không bao giờ tự động |
| **Cluster** (Cụm) | Gom nhiều từ khóa liên quan thành **1 ý tưởng** | VD "summer/travel/bridesmaid pouch" → cụm **Pouch**. Làm 1 listing mạnh phủ cả cụm |
| **Design theme** (chủ đề, không có danh từ sản phẩm) | VD "funny raccoon" | 4 mức: **THEME_FIT_READY** (làm ngay) · **NEEDS_PRODUCT** (chọn sản phẩm trước) · **AMBIGUOUS** · **LOW_BUYER_INTENT** |
| **Verdict** | Kết luận nên/không | GO = làm ngay · CÓ ĐIỀU KIỆN = test 2 listing · WATCH = chờ 2–4 tuần · SKIP/BLOCKED = bỏ |
| **Producibility** (MỚI) | Điểm 0–100: mẫu **có thêu sạch được không** (chỉ chế độ thêu) | **NOT_STITCH_SAFE** → đơn giản hóa mẫu hoặc chuyển POD trước khi thiết kế |
| **Trend phase** (MỚI) | **RISING** (còn lên) / **PEAKING** (chững) / **PEAKED** (đã đỉnh) | RISING = vào sớm; PEAKED = coi chừng đã muộn, chỉ test nhỏ |
| **DATA DEGRADED** (MỚI) | Banner đỏ trang chủ khi dữ liệu YTrends **cũ >48h / mất** | Kiểm tra lại số trước khi quyết; chờ lần refresh sau (tự chạy ~6h/lần) |
| **Opp score** (MỚI) | Điểm tổng hợp 0–100 + verdict **GO / CONDITIONAL / WATCH / SKIP** trên trang Opportunities · Hidden gems · Daily brief. Gộp: Thị trường + Cạnh tranh + Cơ hội + **Dữ liệu bán của MÌNH** + Khả thi (thêu được + trademark) | GO = làm ngay · CONDITIONAL = test trước · **WATCH = thiếu dữ liệu lõi, KHÔNG phải "kém"** · SKIP (trademark HIGH = luôn SKIP). Thấy chữ mà **không có số** = dữ liệu lõi thiếu → công cụ **không bịa điểm** |

---

## 9. POD hay Embroidery? Chọn Product Mode

> 🧵 **Mặc định là Embroidery** (Command Center + Import Center) vì team làm thêu là chính.
> Muốn POD / Both thì bấm chọn — mode bạn chọn luôn được ưu tiên và **giữ xuyên suốt**.

| | **POD (Print on Demand)** | **Embroidery (Thêu)** |
|---|---|---|
| Hợp với | Áo/cốc/poster in graphic, nhiều màu | Mũ, túi, khăn, tên/monogram, patch |
| Giá bán | Rẻ hơn, bán số lượng | Cao hơn (premium), biên lợi nhuận cao |
| Sản xuất | Nhanh, in gì cũng được | Chậm hơn, kén mẫu (ít màu, hình khối rõ) |
| Trong công cụ | Trending/Opportunities lọc theo POD | Lọc theo Embroidery; **theme dùng chung cả 2** |

> Từ khóa **theme** (vd "teacher appreciation") xuất hiện ở **cả hai** mode vì in hoặc thêu
> đều được. Từ khóa **sản phẩm cụ thể** (áo → POD; túi thêu tên → Embroidery) thì khác nhau.

---

## 10. Quản lý công việc (Team) + "Ai đang làm gì"

| Trang | Ai dùng | Làm gì |
|---|---|---|
| ✅ **My Tasks** | Mọi nhân viên | Xem việc được giao; đổi trạng thái **và VIẾT BÁO CÁO đã làm gì** (📝) |
| 📋 **Team Tasks** | Quản lý | Giao việc (chọn **ngày + giờ**), sửa/giao lại; **bảng "👥 Who's on what"** (MỚI) |
| 📅 **Team Calendar** | Cả team | Việc theo hạn: hôm nay / tuần này / trễ hạn / sắp tới |
| 🔍 **Review Queue** | Quản lý | Đọc **báo cáo nhân viên** → Duyệt / Cần sửa / Từ chối |
| 💬 **Tool Feedback** | Mọi người | Góp ý/báo lỗi công cụ; chủ shop tick "đã xử lý" |
| 📈 **Activity Log** | Quản lý | Ai đã làm gì trên dashboard |

**MỚI — "👥 Who's on what" (Team Tasks):** một bảng gọn cho quản lý thấy **mỗi nhân viên
đang gánh gì** trong 1 liếc, không cần quét cả 4 cột To-do / In-progress / Done:

| Nhân viên | To do | Đang làm | **Trễ hạn** | Chờ duyệt |
|---|---|---|---|---|
| (mỗi người 1 dòng) | … | … | (đỏ nếu >0) | … |

**MỚI — ô "In flight" (Manager Desk trang chủ):** đếm số task **đang được làm** toàn team,
để bàn quản lý không hiện toàn số 0 trong khi nhân viên vẫn đang chạy việc.

**MỚI — hạn mặc định 24 giờ:** khi giao việc mà **không nhập hạn**, công cụ tự đặt hạn =
**thời điểm giao + 24 giờ** (sửa lại được bất kỳ lúc nào).

---

## 11. Cổng đăng bán (Publish Gate)

Listing chỉ **PUBLISH_READY = true** khi đủ **TẤT CẢ**:

> NCC đã xác nhận · **đúng product mode** · đạt mục tiêu lợi nhuận · audit đối thủ xong ·
> có kế hoạch ảnh đầu · **đúng 13 tag sạch** · không dính trademark · không còn `[placeholder]`
> · Manager ký duyệt · điểm **Can-We-Win** + **Launch-Readiness** đạt ngưỡng.

→ Thiếu bất kỳ mục nào: **DRAFT ONLY — KHÔNG ĐĂNG.** Công cụ hiển thị đúng danh sách còn
thiếu (`FAILED_PUBLISH_CHECKS`), **không bao giờ** báo "sẵn sàng" khi chưa đạt.

---

## 12. Quy tắc vàng (BẮT BUỘC)

| # | Quy tắc | Vì sao |
|---|---|---|
| 1 | **Không bao giờ tự đăng** — chỉ đăng tay khi Publish-ready = yes + Manager duyệt | Tránh đăng nhầm hàng vi phạm/kém |
| 2 | **Luôn kiểm tra Trademark** (CAUTION → tra USPTO; HIGH → bỏ) | Vi phạm nhãn hiệu → **gỡ listing/khóa shop** |
| 3 | **Listing (title/tag/mô tả) luôn viết TIẾNG ANH** | Khách Etsy là Anh–Mỹ |
| 4 | **Học, không sao chép** đối thủ — học cấu trúc, tự làm bản gốc | Sao chép ảnh/title/mô tả = vi phạm bản quyền |
| 5 | Điểm thấp → đọc dòng **"Improve"** để biết cách sửa, đừng bỏ ngay | Nhiều ý tưởng chỉ cần chỉnh 1 điểm yếu là dùng được |

---

*Có gì khó hiểu hoặc thấy lỗi? Vào 💬 **Tool Feedback** trên trang Team để báo trực tiếp.*
