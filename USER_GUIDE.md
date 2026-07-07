# Etsy Product Manager V20.2-FINAL - Team User Guide / Huong dan su dung

## 1. What this tool does / Cong cu nay lam gi

It is a research + preparation assistant for our Etsy POD & embroidery
team: it finds product opportunities, checks safety (trademark, policy,
supplier, data quality), generates designer prompts and seller packs,
and tells every team member what to do each day.
Day la tro ly nghien cuu + chuan bi cho team Etsy POD & theu: tim co hoi
san pham, kiem tra an toan (trademark, chinh sach, supplier, chat luong
du lieu), tao prompt cho designer va goi listing cho seller, va cho moi
thanh vien biet viec can lam moi ngay.

**It NEVER publishes to Etsy. / KHONG BAO GIO tu dang len Etsy.**
Seller may publish manually ONLY when Final QA status is PUBLISH_READY.
Seller chi duoc dang TAY khi Final QA la PUBLISH_READY.

## 2. Install (one time) / Cai dat (mot lan)

1. Install Python 3.11+ from python.org (tick "Add to PATH").
   Cai Python 3.11+ tu python.org (nho tick "Add to PATH").
2. Unzip the tool folder anywhere, open a terminal in that folder.
   Giai nen thu muc tool, mo terminal (cmd) trong thu muc do.
3. Run / Chay:  `py -m pip install -r requirements.txt`
4. Copy `.env.example` to `.env` and fill / Copy `.env.example` thanh
   `.env` va dien:
   - YTRENDS_COOKIE: log in trends.ytuong.ai -> F12 -> Network -> click
     any "keywords" request -> Request Headers -> copy the whole
     `cookie:` value. (Het han thi lap lai buoc nay. / Repeat when the
     cookie expires.)
   - PRINTIFY_API_TOKEN (optional): Printify -> My Profile ->
     Connections -> Generate token.
   **NEVER share .env or commit it. / TUYET DOI khong chia se .env.**
5. Verify / Kiem tra:  `py main.py selftest`  -> must say
   "ALL CHECKS PASSED".

## 3. Daily workflow / Quy trinh hang ngay

**Morning (Manager) / Buoi sang (Manager):**
```
py main.py listreports
```
(or just open the folder / hoac chi can mo thu muc: reports/latest/)
Only 5 files / Chi 5 file:
0. `00_START_HERE.md` - navigation + today status / dieu huong + trang thai
1. `01_MANAGER_ACTION_REPORT.md` - READ FIRST / DOC TRUOC: quyet dinh,
   diem chan, quyen dang bai (gom ca blockers, tasks, status, final QA)
2. `02_MARKET_KEYWORD_OPPORTUNITY_REPORT.md` - xep hang tu khoa 1-2-3,
   y tuong, co hoi, discover, performance - TAT CA trong 1 file
3. `03_SELLER_EXECUTION_REPORT.md` - Seller: ban nhap, title/tags, QA
4. `04_DESIGNER_BRIEF_REPORT.md` - Designer: brief + prompt
Chi tiet debug nam trong reports/runs/<run>/archive_debug_reports/.

**During the day / Trong ngay:** each owner clears their blockers.
Designer works from the design prompts file; Seller drafts from the
seller pack (DRAFTS ONLY / CHI BAN NHAP).

**End of day (Claude Operator) / Cuoi ngay:**
```
py main.py daily
py main.py listreports
```
Send the manager this path / Gui manager duong dan:
`reports/latest/00_START_HERE.md`

## 4. All commands / Tat ca lenh

### Daily operations / Van hanh hang ngay
| Command | What it does / Tac dung |
|---|---|
| `py main.py daily [pod\|embroidery]` | THE team command: 5 clean reports into reports/latest/ + a timestamped run folder. Works even with no data. / Lenh chinh cua team: 5 bao cao sach. |
| `py main.py listreports` | Show every latest report path (md+csv). / Xem duong dan moi bao cao moi nhat. |
| `py main.py openreports` | Open the latest report folder. / Mo thu muc bao cao moi nhat. |
| `py main.py manager [pod\|embroidery]` | Full manager analysis only. Never hangs. / Chi chay phan tich manager. |
| `py main.py tasks` | Daily tasks report (9 roles). / Bao cao viec theo 9 vai tro. |
| `py main.py blockers` | Blockers grouped by severity. / Bao cao diem chan theo muc do. |
| `py main.py statusboard` | Product status board (csv+md). / Bang trang thai san pham. |
| `py main.py finalqa` | Final QA summary. / Tom tat QA cuoi. |
| `py main.py performance` | Decisions from shop_performance.csv (SCALE/REVISE/KILL/WATCH). / Quyet dinh tu so lieu shop. |
| `py main.py selftest` | Verify install, 90+ checks, no internet needed. / Kiem tra cai dat. |

### Research (needs live YTrends) / Nghien cuu (can API song)
| Command | What it does / Tac dung |
|---|---|
| `py main.py grow` | Auto-add viral/best-selling keywords + niches. / Tu them tu khoa hot. |
| `py main.py grow "embroidered sweatshirt"` | Deep-research one niche. / Dao sau 1 ngach. |
| `py main.py grow pod` / `grow embroidery` | Auto-grow one product line. / Theo dong san pham. |
| `py main.py discover [pod\|embroidery]` | FOCUS keywords + winner listing AGES (FRESH WINNER = new shop can rank). / Tu khoa FOCUS + tuoi listing thang. |
| `py main.py expand "keyword"` | 20 related keywords + TM flags. / 20 tu khoa lien quan. |
| `py main.py listing "keyword"` | Full listing pack for one keyword. / Goi listing cho 1 tu khoa. |
| `py main.py ideas [pod\|embroidery]` | Light cluster report. / Bao cao cum rut gon. |
| `py main.py categories` | Etsy categories by revenue/seller. / Nganh hang theo doanh thu. |
| `py main.py supplier pod\|embroidery "product"` | Supplier records -> supplier_products.csv. / Ho so supplier. |
| `py main.py printify "pouch"` / `printify cost <id>` | Printify catalog / real shipping. |
| `py main.py` | Google Trends check of keywords.csv. |

## 5. Files the team maintains / File team tu cap nhat

| File | Owner | Purpose / Muc dich |
|---|---|---|
| `.env` | Claude Operator | API cookie/token. Refresh cookie when 401. / Lam moi cookie khi loi 401. |
| `supplier_products.csv` | Supplier Checker | Supplier truth: URL, material, size, cost, processing, disclosure, last_verified, manual_review. Publish gates read THIS file. |
| `tm_verified.csv` | IP Reviewer | USPTO evidence + decision=MANAGER_APPROVED. |
| `competitor_audit.csv` | Researcher | Manual competitor fields (photos, video, reviews...). |
| `social_signals.csv` | Researcher | Pinterest/X manual checks (RISING/STABLE/DECLINING). |
| `shop_performance.csv` | Performance Analyst | Etsy Stats per listing -> performance decisions. |
| `keywords.csv`, `niches.txt` | Researcher | Seeds; `grow` also updates them. |
| `team_workflow/` | Everyone | Daily role forms + weekly calendar + Claude operator prompt. |

## 6. Statuses in one line each / Y nghia trang thai

- DESIGN_PREP_READY: designer may prepare CONCEPTS. Not publishable.
  / Designer duoc chuan bi concept. CHUA duoc dang.
- NEED_SUPPLIER_DETAILS / SUPPLIER_CHECK: fill supplier_products.csv.
- TM_IP_CHECK: USPTO check or manager approval needed.
- DATA_CHECK_REQUIRED: researcher must verify the keyword data.
- LISTING_DRAFT_READY: seller may create an Etsy DRAFT only.
- FINAL_QA: waiting for the 21-gate form + manager manual_review=yes.
- PUBLISH_READY: every gate passed - seller may publish MANUALLY.
- BLOCKED: do not use. / Khong dung.

## 7. Troubleshooting / Xu ly loi

| Problem | Fix |
|---|---|
| 401 / "unreachable" on research commands | Cookie expired. Redo step 2.4 (F12 -> copy cookie -> .env). / Cookie het han, lay lai. |
| Reports say DATA_UNAVAILABLE | Same as above, or restore fresh keyword_data.csv. No product moves forward that day; no publishing. |
| `pytrends` error on bare `py main.py` | `py -m pip install pytrends` (only affects Google Trends check). |
| "Unknown command" | Check spelling; run `py main.py` help text. The tool never guesses. |
| Where are my reports? | `py main.py listreports` - or bookmark `reports/latest/`. Selftest reports live in `reports/selftest/` and are never "latest". |

## 8. Safety rules (memorize) / Quy tac an toan (thuoc long)

1. The tool never publishes. Humans publish. / Tool khong dang; nguoi dang.
2. Drafts only until PUBLISH_READY. / Chi ban nhap den khi PUBLISH_READY.
3. No brand/celebrity/franchise terms, ever. / Khong dung ten thuong hieu.
4. When unsure about trademark: CAUTION, never CLEAR. / Khong chac -> CAUTION.
5. Never guess supplier facts; missing = blocked. / Khong bia thong tin supplier.
6. Competitors are for positioning, not copying. / Doi thu de dinh vi, khong copy.
7. Flagged data never drives decisions. / Du lieu nghi van khong dung ra quyet dinh.
