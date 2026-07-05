# Etsy Product Manager V20.2-FINAL

## Run it on a new computer (Mac M1 / Windows / Linux)

The tool is pure Python and cross-platform. To set it up on another machine
(e.g. a MacBook Pro M1):

    # 1. Get the code
    git clone https://github.com/NatoandUSA/etsy-agent.git
    cd etsy-agent

    # 2. Create an isolated environment (recommended)
    python3 -m venv .venv
    source .venv/bin/activate         # Windows: .venv\Scripts\activate

    # 3. Install dependencies
    pip install -r requirements.txt

    # 4. Add your secrets (NEVER commit this file)
    cp .env.example .env              # Windows: copy .env.example .env
    #   then edit .env and fill in your real API tokens

    # 5. Verify + run
    python3 main.py selftest          # health check, no network needed
    python3 main.py daily             # the daily command

On macOS/Linux use `python3`; on Windows use `py` or `python`. Everything
in this README that shows `py main.py` works the same as `python3 main.py`.

Your `.env` (API tokens/cookies) is git-ignored and stays on each machine —
copy it over manually or re-fill it from `.env.example`. To pull the latest
changes on any machine later: `git pull`.

## Simple daily workflow (this is all most people need)

    python main.py selftest      <- after install/update only: health check
    python main.py daily         <- the daily command: makes the 5 reports
    python main.py listreports   <- shows where the reports are
    python main.py openreports   <- opens the report folder

## What to read (in this order)

    reports/latest/
      00_START_HERE.pdf                        <- navigation + today's status
      01_MANAGER_ACTION_REPORT.pdf             <- Manager: decisions, blockers,
                                                  publish permission
      02_MARKET_KEYWORD_OPPORTUNITY_REPORT.pdf <- Researcher: keyword ranking,
                                                  ideas, discover, performance
      03_SELLER_EXECUTION_REPORT.pdf           <- Seller: drafts, title/tags,
                                                  QA (drafts only!)
      04_DESIGNER_BRIEF_REPORT.pdf             <- Designer: briefs + prompts

Every run is also archived with exact time in reports/runs/, including
raw_data/ and archive_debug_reports/ (the detailed reports live there).

## Which command first, and why

- selftest: only after install or update - proves the tool is healthy.
- daily: the normal team command, run at end of day (or morning).
- listreports: find the newest reports any time.
- openreports: open the folder; start from 00_START_HERE.
- rawreports / manager / market / seller / designer / tasks / blockers /
  statusboard / finalqa / performance / grow / discover / supplier /
  printify / expand / listing: advanced or debug - normal team members
  do not need these.
- pdfcheck: only if PDFs are missing.

## Publishing safety rule

Seller may publish manually only when 01_MANAGER_ACTION_REPORT says
Publish Allowed = YES and Final QA status is PUBLISH_READY.

## If reports say DATA_UNAVAILABLE

The run still produces all 5 reports; they name the fix: refresh
YTRENDS_COOKIE in .env or provide fresh keyword_data.csv. No product
moves forward, no publishing, until data is restored.

## SAFETY - read first
- This tool NEVER publishes to Etsy. All publishing is manual.
- It never scrapes Etsy or automates the Etsy website.
- PUBLISH_READY appears only when every evidence gate passes
  (see src/publish_gate.py - the single source of truth).
- Flagged/suspicious data can never drive product decisions.
- Supplier truth lives in supplier_products.csv (supplier_costs.csv
  is cluster-level estimates only).

## Manual Etsy review checklist (before ANY publish)
[ ] Supplier verified: URL + material + size + cost + processing,
    last_verified date filled in supplier_products.csv
[ ] Production partner disclosed in Etsy listing settings
[ ] Original design confirmed (seller_original_design_confirmed=yes)
[ ] Trademark: USPTO checked + link saved, or manager approval logged
[ ] Etsy policy reviewed (prohibited/mature/reselling)
[ ] Title approved (validator passing, buyer-readable)
[ ] 13 tags approved (validator passing)
[ ] Photos/mockups honest - show the real product
[ ] Price/margin approved (real costs, >= $6 net)
[ ] Shipping/processing accurate in the listing
[ ] manual_review=yes recorded in supplier_products.csv

## What this tool does NOT do
No auto-publishing, no Etsy scraping, no legal advice, no sales
guarantees. It prepares and gates; your team decides.

# Etsy Agent - Niche Research (Phase 1)

Finds rising, low-competition niches for your POD/embroidery shop using
Google Trends (free), with a ready slot for the YTrends API.

## Setup (one time)

1. Install Python 3.10+ from https://python.org (check "Add to PATH" on Windows).
2. Open this folder in VS Code (File -> Open Folder).
3. Open the terminal in VS Code (Ctrl+`) and run:

   pip install -r requirements.txt

## Run it

   python main.py

It reads `keywords.csv`, checks 12-month Google Trends momentum for each
keyword, scores every niche, and writes a ranked report into `reports/`.

## Weekly workflow

1. Add new keyword ideas to `keywords.csv` (one per line).
2. Fill the `competition` column: search the keyword on Etsy and copy the
   listing count (or read it from YTrends). This makes scores far more accurate.
3. Run `python main.py`.
4. Designer works only on DESIGN_PREP_READY items. Seller may prepare drafts only; publish manually only after PUBLISH_READY.
5. Never automate the Etsy website itself. All publishing is manual copy-paste.

## Discover mode (live YTrends data)

   py main.py discover

Pulls YTuong's top-revenue keywords + trending + hidden gems, then:
- marks FOCUS picks: sellable POD/embroidery product, <=300 Etsy
  listings (or LOW level), 500+ views/day, conversion >=2%, rising,
  and no known trademark hit
- shows Etsy listing count + seller count + 24h views per keyword
- flags trademark risk: HIGH (known brand - skip) and CAUTION
  (slogan-like - verify at tmsearch.uspto.gov before designing)
- filters out shop-name junk and service keywords automatically
Results cached per day; safe within your 800/day API quota.

## Expand a niche

   py main.py expand "chenille name bag"

Shows 20 related keywords (with listings count, revenue, conversion,
and trademark flag) so you can build out a niche you like.

## Top performers

The discover report now includes the top 3 Etsy listings per FOCUS
keyword: title, price, sold, revenue, listing age, link, and the tags
the winners share. MARKET INTEL ONLY - never copy a design or title.

## Category intelligence

   py main.py categories

Ranks Etsy's categories by revenue-per-seller so you know where the
money concentrates (e.g. Jewelry pays ~$4,800/seller).

## Authentication

Prefer YTRENDS_API_TOKEN in `.env`. A session cookie is supported only as a fallback and must never be shared or committed. If a cookie expires, refresh it manually; do not automate browser access.

## Best Etsy Idea Report (cluster mode)

   py main.py ideas

Groups keywords into product clusters, scores each on demand,
competition, conversion, AOV, momentum, profit margin, IP/policy
safety, and differentiation (weighted), then gives verdicts:
DESIGN NOW / VALIDATE FIRST / SKIP. Auto-rejects services, passed
seasons, thin margins, low demand, and unverified trademark risks.
Includes first-5-designs, title formula, 13 tags, pricing target,
and a 7-day validation plan per winning cluster.

Team inputs the agent depends on:
- costs.csv        -> one row per supplier per cluster; agent auto-picks
                      the cheapest. REPLACE placeholders with real prices
                      from each supplier dashboard (see SUPPLIERS.md)
- tm_verified.csv  -> log every USPTO check (keyword, CLEAR/BLOCKED,
                      link, who, date); CAUTION keywords stay rejected
                      until logged here

## Listing Factory (goi listing hoan chinh)

   py main.py listing "chenille name bag"

Tao goi listing DRAFT: TITLE + 13 TAGS + DESCRIPTION (tieng Anh,
dan thang vao Etsy), gia ban kem loi nhuan uoc tinh, link 3 doi thu manh
nhat, checklist 10 anh/mockup, va 14 buoc dang tren Shop Manager - tat ca
huong dan bang tieng Viet, xuat kem PDF. Tu khoa dinh thuong hieu HIGH se
bi chan; CAUTION se co canh bao kiem tra USPTO truoc.

## Printify integration (real costs)

   py main.py printify "pouch"       -> find matching Printify products
   py main.py printify cost 1090     -> print providers + REAL US shipping

Needs PRINTIFY_API_TOKEN in .env (Printify -> My Profile -> Connections,
catalog.read scope). Shipping comes from the API; blank-product base cost
you read once from the Printify catalog page. Put both in costs.csv, then
rerun `py main.py ideas` for true profit numbers.

## Etsy Product Manager AI (lenh chinh moi)

   py main.py manager

Bao cao quan ly san pham 12 muc: quyet dinh (DESIGN NOW / VALIDATE FIRST /
WATCHLIST / SKIP / BLOCKED / WAIT FOR TM CHECK), cluster tot nhat + diem
/100, 5 brief cho designer, mo hinh loi nhuan day du, audit doi thu (loc
relevance >= 0.75), 2 goi listing da kiem tra (dung 13 tag), bang tu khoa
bi loai + cach cuu, hang doi trademark, ke hoach 7 ngay, va QA validator
15 muc (READY / NEEDS_FIX). Xuat: .md + PDF (song ngu), .json (may doc),
tasks_*.md (viec cho designer/seller/researcher/trademark).

Legacy notes - BAN HANG TOT HON DOI THU (sales execution):
- Muc 1b "Tom tat hanh dong ban hang": tra loi 11 cau hoi (ban gi, vi sao,
  thiet ke gi, supplier nao, lai bao nhieu, listing the nao, kiem tra gi,
  test gi 7 ngay, nhan rong the nao) trong 1 trang.
- Muc 6b "Kiem tra tin hieu da nguon": Google Trends chay TU DONG cho tu
  khoa cua cum tot nhat; Pinterest/X khong co API gia re nen researcher
  kiem tra tay 5 phut roi dien social_signals.csv (he thong tu tao mau,
  KHONG BAO GIO bia tin hieu). Verdict: CONFIRMED / MIXED / ETSY_ONLY /
  DECLINING.
- Muc 9c "Ke hoach loi the canh tranh": 11 chien thuat co bang chung +
  nguoi phu trach (anh dau tien, mockup, ca nhan hoa, goc ngach, bundle,
  gia, SEO, uy tin, ship ro rang, video, mo rong dong san pham). 3 loi the
  hang dau duoc bom thang vao prompt cua designer.
- Du lieu tu khoa TU LAM MOI: keyword_data.csv cu hon hom nay -> tu keo
  lai + grow.

V16 - TU DONG MO RONG TU KHOA & NGACH (grow):
   py main.py grow                          (tu dong: viral + hidden gem +
                                             goi y tu ngach cua ban)
   py main.py grow "embroidered sweatshirt" (dao sau 1 ngach cu the)
   py main.py grow pod / grow embroidery    (theo dong san pham)
Tu dong cap nhat: keywords.csv (kem so listing canh tranh), niches.txt
(danh dau auto-added de ban duyet), keyword_data.csv (manager cham diem
ngay lan chay sau). Loc trung lap, junk, dich vu, trademark HIGH.
Demand duoc suy ra trung thuc: views/ngay = tong ban/ngay : ty le mua.
'py main.py manager' cung tu grow khi keo du lieu moi. Quota: ~15 call.

V15 - MOI:
   py main.py manager pod          (chi tu khoa print-on-demand)
   py main.py manager embroidery   (chi tu khoa theu)
Moi lan chay manager tao them 2 file cho team:
- design_prompts_*.md: prompt san sang COPY-DAN vao Claude/Claude Design
  cho tung thiet ke (kem du lieu best seller Etsy + spec san xuat POD/theu)
- seller_pack_*.md: chi tiet listing theo DUNG thu tu dan vao Etsy
Bao cao manager gio co du 2 ban: tieng Anh (goc) + _VI.md tieng Viet, moi
ban kem PDF.

V14 - LENH SUPPLIER (2 lenh moi):
   py main.py supplier pod "clear concert bag"
   py main.py supplier embroidery "chenille name bag"
Tao ho so supplier vao supplier_products.csv (Printify keo truc tiep qua
API; ShineOn/BurgerPrints/Printway khong co API du lieu -> team dien tu
dashboard). San pham chi PUBLISH_READY khi 1 dong supplier dat
SUPPLIER_CONFIRMED. Bao cao luon in 3 trang thai: QA_REPORT_READY /
DESIGN_PREP_READY / PUBLISH_READY.

QUY TAC XUAT BAN (publish gates): moi listing package co 2 trang thai:
DESIGN_PREP_READY (designer duoc chuan bi mockup) va PUBLISH_READY (seller
duoc dang). PUBLISH_READY chi khi du 7 dieu kien: audit doi thu dat, supplier
xac nhan material/size/processing (dien vao supplier_costs.csv), tu khoa
chinh khong bi DATA_CHECK_REQUIRED, trademark da xac minh/chap nhan duoc,
du 13 tag, khong con placeholder, va lai >= $6. Muc 0 cua bao cao liet ke
moi thu dang chan - KHONG duoc dang khi muc 0 con o trong.

Kiem tra cai dat:  py main.py selftest  (khong can API, khong can mang)

Input files (tu tao mau neu thieu): keyword_data.csv (tu dong keo tu
YTrends neu chua co), supplier_costs.csv, tm_verified.csv,
competitor_audit.csv. Xem SYSTEM_PROMPT.md de hieu toan bo quy tac.

## Modes: POD vs Embroidery

   py main.py discover pod          py main.py ideas pod
   py main.py discover embroidery   py main.py ideas embroidery

Loc ket qua theo dong san pham. Khong ghi mode = tat ca.
Embroidery = tu khoa chua: embroider/chenille/monogram/applique/
stitch/patch/crochet/knit. POD = phan con lai.

## PDF + song ngu (bilingual)

Moi bao cao xuat 4 file: report.md + report.pdf (tieng Viet) va
report_EN.md + report_EN.pdf (tieng Anh) - cung noi dung, cung so lieu.

Moi bao cao (.md) tu dong xuat them ban PDF cung thu muc reports/.
Noi dung huong dan trong bao cao viet bang tieng Viet; tu khoa va so
lieu giu tieng Anh vi Etsy la thi truong tieng Anh.
Yeu cau: pip install reportlab (da co trong requirements.txt).

## Next upgrades (do these in Claude Code)

- Wire in the YTrends API: see instructions inside `src/ytrends_client.py`.
- Phase 2 "Listing Factory": drafts title + 13 tags + description per niche.
- Phase 3: import Etsy Stats CSV exports to learn what converts.

## Safety rules baked in

- Secrets live only in `.env` (git-ignored). Never in code, never in chat.
- No scraping or automation of etsy.com. Data comes from YTrends' API,
  Google Trends, and your own manual CSV exports from Shop Manager.
