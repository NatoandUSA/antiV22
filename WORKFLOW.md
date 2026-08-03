# 🧭 Quy trình Etsy — 5 giai đoạn (12 bước)

_File này được sinh ra từ `src/workflow_spine.py` — **cùng một nguồn** với trang chủ.
Nếu hai bên khác nhau thì module đúng, hãy sinh lại file này thay vì sửa tay._

> **Quy trình 9 bước cũ (V30) đã BỎ.** Nó không mô tả đúng cách làm thật: Pinterest và
> nhà cung cấp bị coi là badge phụ ở cuối thay vì cổng lọc ở đầu, và nó ghi Alura/EverBee
> trong khi shop đang chạy bằng export HeyEtsy.

## Vì sao gộp thành 5 giai đoạn

12 bước là **checklist đúng** nhưng **điều hướng sai**. Nhiều bước thực ra là *một lần ngồi
làm* trên *một trang*: bước 6/7/8 đều là “học người thắng” (`/imports` → `/pattern-miner`),
còn bước 9/10 đã gộp thành **một nút bấm** từ khi khoá được vòng lặp winner → Inbox (V37.7).
Tách ra thành 12 ô trên trang chủ làm việc trông giống bản kế hoạch dự án hơn là việc trong ngày.
Vì vậy: **màn hình hiện 5 giai đoạn, 12 bước nằm bên trong.** Không mất gì.

## Quy tắc

- **Mỗi bước chỉ có MỘT đường dẫn chính.** Dashboard có 104 route nhưng chỉ 12 là bước quy
  trình; phần còn lại là route hỗ trợ (xem cuối file).
- **Trạng thái đọc từ dữ liệu thật.** Chỉ ✅ khi output có thật trên đĩa. Không đoán.
- **Hướng dẫn cho team viết tiếng Việt. Nội dung listing (tiêu đề · 13 tag · mô tả) viết
  tiếng Anh** vì người mua ở Mỹ.
- **Không tự đăng bán.** `PUBLISH_AUTOMATION = False`; người thật đăng tay trên Etsy.

## 5 giai đoạn

| # | Giai đoạn | Làm gì | Bước | Route chính | Người phụ trách |
|---|---|---|---|---|---|
| 1 | 🔎 **Tìm & lọc** (Find & filter) | Gom từ khoá, xem tín hiệu Pinterest, kiểm nhà cung cấp làm được hay không | 1·2·3 | `/trending` | Researcher |
| 2 | 🏆 **Xếp hạng** (Rank) | Để máy chấm điểm và nói rõ nên làm cái nào trước | 4 | `/inbox` | Researcher |
| 3 | 🔬 **Học người thắng** (Learn from winners) | Nhập bằng chứng HeyEtsy, mở listing top, đọc ra công thức thắng | 5·6·7·8 | `/pattern-miner` | Researcher |
| 4 | 💡 **Từ khoá mới** (New keywords) | Tool tự sinh từ khoá từ winner — bấm một nút đẩy lại vào Inbox | 9·10 | `/keyword-lab` | Researcher |
| 5 | 🚀 **Làm & giao** (Build & ship) | Lên listing + ảnh, giao việc cho team, đo kết quả Ngày 3 / Ngày 7 | 11·12 | `/launch-kit` | Seller |

### 🔎 Giai đoạn 1 — Tìm & lọc

- **Làm gì:** Gom từ khoá, xem tín hiệu Pinterest, kiểm nhà cung cấp làm được hay không
- **Tạo ra:** Danh sách từ khoá thô đã qua cổng lọc
- **Route chính:** `/trending` · **Phụ trách:** Researcher

| Bước | Tên | Route | Cần có | Tạo ra |
|---|---|---|---|---|
| 1 | MCP / YTrends keyword feed | `/trending` | Live YTrends index (harvest runs on the PC — the VPS IP is blocked) | keyword_data.csv — the master every later step ranks |
| 2 | Pinterest trend signal | `/pinterest-trends` | Pinterest export or capture for the niche | Demand corroboration badge on matching keywords |
| 3 | Supplier feasibility | `/suppliers` | Supplier library (CSV import or saved suppliers) | Can we actually make and ship it, at what cost |

### 🏆 Giai đoạn 2 — Xếp hạng

- **Làm gì:** Để máy chấm điểm và nói rõ nên làm cái nào trước
- **Tạo ra:** Hành động cuối cho từng từ khoá: Làm ngay / Kiểm tra / Theo dõi / Bỏ
- **Route chính:** `/inbox` · **Phụ trách:** Researcher

| Bước | Tên | Route | Cần có | Tạo ra |
|---|---|---|---|---|
| 4 | Find good keyword / Rank | `/inbox` | keyword_data.csv from step 1 | Final action per keyword: Build now / Confirm first / Watch / Skip |

### 🔬 Giai đoạn 3 — Học người thắng

- **Làm gì:** Nhập bằng chứng HeyEtsy, mở listing top, đọc ra công thức thắng
- **Tạo ra:** Tiêu đề · tag · ảnh · giá · cá nhân hoá · góc nhìn người mua
- **Route chính:** `/pattern-miner` · **Phụ trách:** Researcher

| Bước | Tên | Route | Cần có | Tạo ra |
|---|---|---|---|---|
| 5 | Pattern Miner on real Etsy results | `/pattern-miner` | A keyword from step 4 | Why the current winners rank for this keyword |
| 6 | HeyEtsy evidence | `/imports` | HeyEtsy Detail + Etsy Reviews export (Evidence Exporter extension) | Views · sold · favorites · listing age · shop proof, per listing |
| 7 | Open the best 5 / 10 / 20 listings | `/imports` | Imported evidence from step 6 | The actual Etsy listing pages of the winners |
| 8 | Extract the winning pattern | `/pattern-miner` | Evidence + reviews from step 6 | Title · tags · photos · price · personalization · reviews · buyer angle |

### 💡 Giai đoạn 4 — Từ khoá mới

- **Làm gì:** Tool tự sinh từ khoá từ winner — bấm một nút đẩy lại vào Inbox
- **Tạo ra:** Từ khoá mới có gắn nguồn winner, được xếp hạng lại
- **Route chính:** `/keyword-lab` · **Phụ trách:** Researcher

| Bước | Tên | Route | Cần có | Tạo ra |
|---|---|---|---|---|
| 9 | Generate new keyword candidates | `/imports` | A dissected winner from step 8 | Keywords from the winner's title, real tags and review language |
| 10 | Send candidates to Re-rank / Inbox | `/rerank` | Candidates from step 9 | Candidates in the master tagged winner:<listing_id>, re-ranked |

### 🚀 Giai đoạn 5 — Làm & giao

- **Làm gì:** Lên listing + ảnh, giao việc cho team, đo kết quả Ngày 3 / Ngày 7
- **Tạo ra:** Listing hoàn chỉnh (tiếng Anh) + việc đã có người nhận
- **Route chính:** `/launch-kit` · **Phụ trách:** Seller

| Bước | Tên | Route | Cần có | Tạo ra |
|---|---|---|---|---|
| 11 | Build listing / design / photo plan | `/launch-kit` | A keyword the engine cleared at step 4 or 10 | Title · 13 tags · description · personalization · photo brief |
| 12 | Assign Team Ops + learn Day 3 / Day 7 | `/team/ops` | A built listing from step 11 | Owned tasks, then the Day 3 / Day 7 keep-fix-drop-scale call |

## Vòng lặp đã khoá (giai đoạn 3 → 4 → 2)

Đây chính là vòng lặp trước kia bị hở, và là lý do tool cảm giác chạy tới chạy lui:

```
  Nhập winner (HeyEtsy)  ──►  Đọc ra công thức thắng
                                  │  tiêu đề · tag thật · lời review
                                  ▼
                         Tool TỰ SINH từ khoá ứng viên
                                  │  hiện ở /imports và /pattern-miner
                                  ▼
                        MỘT NÚT: Send to Re-rank / Inbox
                                  │  gắn nhãn winner:<listing_id>
                                  ▼
                         Xếp hạng lại bằng engine L0–L4
```

Trước V37.7 bước này **không tồn tại**: ứng viên được tính rồi bỏ đó, `candidates_for_rerank()`
không ai gọi, và nhân viên **gõ lại từ khoá bằng tay**. Mỗi lần đẩy đều bị chặn trần ở
`CONFIRM_FIRST` và ghi lại trong `data/imports/rerank_pushes/` kèm listing nguồn, lý do và
tóm tắt bằng chứng — nên mọi từ khoá trong Inbox đều truy ngược được.

## Route hỗ trợ (không phải bước quy trình)

- **Research + discovery:** `/opportunities` · `/gems` · `/newest` · `/research` · `/research-queue` · `/longtail` · `/keyword-lab` · `/should-sell` · `/shortlist` · `/winners` · `/etsy-spy` · `/spy` · `/kw-history`
- **Evidence + imports:** `/import-file` · `/score-import` · `/listings` · `/shops` · `/enrich-leads` · `/imports/add`
- **Build + design:** `/draft-listing` · `/photo-brief` · `/design-skill-bridge` · `/design-analyzer` · `/grade` · `/analyze` · `/ads-plan`
- **Team + admin:** `/team` · `/team/calendar` · `/me/tasks` · `/admin/users` · `/admin/tasks` · `/admin/reviews` · `/admin/activity` · `/launchpad` · `/confirm`
- **Monitoring:** `/alerts` · `/trackers` · `/profit` · `/status` · `/daily-brief` · `/build-queue` · `/feedback`
- **Reference:** `/workflow` · `/how-to-use` · `/cheatsheet` · `/training`

## Nguyên tắc an toàn

- `PUBLISH_AUTOMATION = False` — trong code không có đường đăng bán.
- Không tự động kết nối Etsy / Amazon / eBay / OTA để thao tác.
- Toán xếp hạng L0–L4 do chủ shop quyết; `ranking_engine.py` không đổi.
- Honest-nulls: thiếu số đo thì để trống, không tính thành 0.
