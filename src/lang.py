"""Bilingual reports: every VI report also gets an _EN sibling + PDFs."""
from pathlib import Path

VI2EN = [
    # ideas report
    ("# Báo cáo Ý tưởng Etsy Tốt nhất", "# Best Etsy Idea Report"),
    ("## Việc cần làm hôm nay", "## What to do today"),
    ("**THIẾT KẾ NGAY (DESIGN_PREP_READY) -> ", "**DESIGN_PREP_READY -> "),
    ("**: designer chuẩn bị concept. Seller CHỈ được tạo bản nháp (draft) - chưa được đăng.",
     "**: designer prepares concepts. Seller may prepare a DRAFT only - no publishing."),
    ("**KIỂM CHỨNG TRƯỚC (VALIDATE FIRST) -> ", "**VALIDATE FIRST -> "),
    ("**: chỉ đăng 2 listing thử nghiệm. Chưa làm loạt thiết kế lớn.",
     "**: publish 2 test listings only. No big design batch yet."),
    ("**BỎ QUA (SKIP)**: ", "**SKIP for now**: "),
    ("Sản phẩm này có người tìm mua mỗi ngày và mức cạnh tranh có thể thắng được. Ước tính: ",
     "People search for this product every day and competition is beatable. Estimated: "),
    ("lãi khoảng $", "about $"),
    (" mỗi đơn ở mức giá hiện tại", " profit per sale at current prices"),
    ("chưa rõ lợi nhuận - hãy điền giá supplier vào costs.csv",
     "profit unknown - fill supplier prices into costs.csv"),
    (" Supplier rẻ nhất: ", " Cheapest supplier: "),
    ("**Làm 5 thiết kế này trước:**", "**Make these 5 first:**"),
    ("**Cách đăng listing:**", "**How to list it:**"),
    ("- Tiêu đề: ", "- Title: "),
    ("- Tags (copy đủ 13): ", "- Tags (copy all 13): "),
    ("- Giá bán: $", "- Price: $"),
    (" -> bạn giữ lại khoảng $", " -> you keep about $"),
    (" sau phí Etsy + giá gốc", " after Etsy fees + product cost"),
    ("- Trước khi thiết kế: mở 3 listing đối thủ lớn nhất. Ghi lại ảnh đầu, số review, tùy chọn cá nhân hóa, tốc độ ship. Làm tốt hơn đối thủ yếu nhất.",
     "- Before designing: open the 3 biggest competitor listings. Note first photo, review count, personalization options, shipping speed. Beat the weakest one."),
    ("**Các từ khóa trong nhóm này:**", "**Keywords in this cluster:**"),
    ("| Từ khóa | Kết quả Etsy | Views/ngày | Giá TB | An toàn? |",
     "| Keyword | Etsy results | Views/day | Avg price | Safe? |"),
    ("| an toàn |", "| yes |"),
    ("**Kiểm chứng 7 ngày:** Ngày 1-2 đăng 3 listing (từ khóa top). Ngày 3-4 đăng thêm 2. Ngày 5-7: 0 view = đổi tags; có favorite/giỏ hàng = làm thêm 3 biến thể của thiết kế đó.",
     "**7-day test:** Days 1-2 publish 3 listings (top keywords). Days 3-4 publish 2 more. Days 5-7: 0 views = change tags; any favorite or cart = make 3 more variations of that design."),
    ("## Nhu cầu tốt nhưng cần giá bán cao hơn",
     "## Good demand but needs a higher price"),
    ("_Bán chạy nhưng giá phổ biến quá thấp để có lãi. CHỈ dùng với phiên bản cá nhân hóa/cao cấp ở mức 'giá tối thiểu', hoặc tìm supplier rẻ hơn._",
     "_These sell well but the usual price is too low to profit. Use ONLY with personalized/premium versions at the 'charge at least' price, or find a cheaper supplier._"),
    ("| Từ khóa | Giá phổ biến | Giá tối thiểu | Để lãi $6 |",
     "| Keyword | Usual price | Charge at least | For $6 profit |"),
    ("## Chờ kiểm tra thương hiệu - trademark (2 phút/từ)",
     "## Waiting for trademark check (2 min each)"),
    ("_Tra từng cụm tại tmsearch.uspto.gov (lọc: Live). Không có nhãn hiệu sống trong ngành hàng -> ghi CLEAR vào tm_verified.csv kèm link. Có -> ghi BLOCKED._",
     "_Search each phrase at tmsearch.uspto.gov (filter: Live). No live mark in your product class -> add CLEAR to tm_verified.csv with the link. Found one -> add BLOCKED._"),
    ("## Phụ lục số liệu (dành cho leader)", "## Numbers appendix (for the leader)"),
    ("Tất cả từ khóa bị loại - bảng đầy đủ (bấm để mở)",
     "All rejected keywords - full table (click to open)"),
    ("| Từ khóa | Views/ngày | Kết quả Etsy | Giá TB | Lý do loại |",
     "| Keyword | Views/day | Etsy results | Avg price | Why rejected |"),
    # discover report
    ("# Báo cáo khám phá từ khóa", "# Keyword discovery report"),
    ("## FOCUS - ưu tiên thiết kế trước", "## FOCUS - design these first"),
    ("_Cạnh tranh thấp + nhu cầu thật + tỷ lệ mua tốt + không dính thương hiệu._",
     "_Low competition + real demand + converts + no known trademark._"),
    ("## Listing bán chạy nhất theo từ khóa FOCUS (tham khảo thị trường - KHÔNG copy)",
     "## Top performers per FOCUS keyword (market intel - do NOT copy)"),
    ("   Tags chung của các listing thắng: ", "   Tags shared by winners: "),
    ("## Ngách của bạn (theo dõi)", "## Your niches (watchlist)"),
    ("## Các từ khóa khác (ý tưởng mở rộng)", "## Other keywords (expansion ideas)"),
    ("| Focus | Từ khóa | Listing Etsy | Seller | Views 24h | Giá TB | Doanh thu TB | Conv. | Momentum | Rủi ro TM |",
     "| Focus | Keyword | Etsy listings | Sellers | Views 24h | Avg price | Avg revenue | Conv. | Momentum | TM risk |"),
    ("### Cách dùng báo cáo này", "### How to use this report"),
    # listing pack (ASCII Vietnamese)
    ("# Goi listing hoan chinh", "# Complete listing pack"),
    ("**CANH BAO:** Cum tu nay giong slogan. Tra tmsearch.uspto.gov (loc Live) va ghi vao tm_verified.csv TRUOC khi dang.",
     "**WARNING:** This phrase looks like a slogan. Check tmsearch.uspto.gov (filter Live) and log in tm_verified.csv BEFORE publishing."),
    ("## 1. Noi dung dan vao Etsy (giu tieng Anh)",
     "## 1. Content to paste into Etsy"),
    ("**TITLE (dan vao o Title):**", "**TITLE (paste into the Title field):**"),
    ("**TAGS (dan tung tag, du 13):**", "**TAGS (paste each tag, all 13):**"),
    ("**DESCRIPTION (dan vao o Description):**",
     "**DESCRIPTION (paste into the Description field):**"),
    ("**GIA BAN: $", "**PRICE: $"),
    (" (ban giu lai ~$", " (you keep ~$"),
    (" | Supplier re nhat: ", " | Cheapest supplier: "),
    (" | Gia trung binh doi thu: $", " | Competitor average: $"),
    ("## 2. Doi thu manh nhat (tham khao, KHONG copy)",
     "## 2. Strongest competitors (reference only - do NOT copy)"),
    (" da ban", " sold"),
    ("## 3. Checklist anh/mockup (10 o anh cua Etsy)",
     "## 3. Photo/mockup checklist (10 Etsy photo slots)"),
    ("1. Anh chinh: san pham ro net, nen sang, thay chu/thiet ke ngay",
     "1. Main photo: product sharp, bright background, design visible instantly"),
    ("2. Goc gan (chi tiet thiet ke/theu)", "2. Close-up (design/embroidery detail)"),
    ("3. Nguoi that dang dung / lifestyle", "3. Real person using it / lifestyle"),
    ("4. Bang size hoac kich thuoc", "4. Size chart or dimensions"),
    ("5. Cac mau/bien the co san", "5. Available colors/variations"),
    ("6. Anh mockup dip tang qua (goi qua, thiep)",
     "6. Gift-occasion mockup (wrapping, card)"),
    ("7. Anh personalization: vi du ten khac nhau",
     "7. Personalization examples: different names"),
    ("7. Anh goc canh khac", "7. Alternate angle"),
    ("8. Anh so sanh kich thuoc thuc te", "8. Real-scale size comparison"),
    ("9. Review/feedback mockup (khi co)", "9. Review/feedback mockup (when available)"),
    ("10. Anh thuong hieu shop", "10. Shop branding photo"),
    ("Video 5-15 giay neu co the - Etsy uu tien listing co video.",
     "5-15 second video if possible - Etsy boosts listings with video."),
    ("## 4. Cac buoc dang tren Etsy (Shop Manager)",
     "## 4. Publish steps on Etsy (Shop Manager)"),
    ("2. Tai 6-10 anh + video theo checklist tren",
     "2. Upload 6-10 photos + video per the checklist above"),
    ("3. Dan TITLE (muc 1)", "3. Paste the TITLE (section 1)"),
    ("5. Chon Category dung nhat theo goi y cua Etsy",
     "5. Pick the most accurate Category Etsy suggests"),
    ("6. Dien DESCRIPTION (muc 1) - nho dien cho [Fill]",
     "6. Paste the DESCRIPTION (section 1) - remember to complete [Fill]"),
    ("7. Keo xuong Tags: dan du 13 tag (muc 1)",
     "7. Scroll to Tags: paste all 13 tags (section 1)"),
    ("8. Variations: them size/mau theo supplier",
     "8. Variations: add sizes/colors per your supplier"),
    ("9. Personalization: BAT, ghi ro huong dan cho khach",
     "9. Personalization: turn ON, write clear buyer instructions"),
    ("9. Personalization: tat (san pham nay khong ca nhan hoa)",
     "9. Personalization: off (this product is not personalized)"),
    ("10. Price: dat theo GIA BAN o tren; Quantity: 20-50",
     "10. Price: use the PRICE above; Quantity: 20-50"),
    ("11. Shipping: chon shipping profile khop processing time supplier",
     "11. Shipping: pick the profile matching your supplier's processing time"),
    ("12. Production partner: chon dung supplier (bat buoc voi POD)",
     "12. Production partner: select the correct supplier (required for POD)"),
    ("13. Bam Publish ($0.20 phi listing)", "13. Click Publish ($0.20 listing fee)"),
    ("14. Sau khi dang: mo listing o che do khach, kiem tra anh + personalization hoat dong",
     "14. After publishing: open the listing as a buyer, verify photos + personalization work"),
    ("## 5. Sau khi dang", "## 5. After publishing"),
    ("- Ghi URL listing + ngay dang vao file theo doi cua team",
     "- Log the listing URL + publish date in the team tracker"),
    ("- Ngay 3 va ngay 7: xem views/favorites trong Shop Manager Stats",
     "- Day 3 and day 7: check views/favorites in Shop Manager Stats"),
    ("- 0 view sau 7 ngay -> doi tag yeu nhat bang tu khoa moi tu 'py main.py expand'",
     "- 0 views after 7 days -> replace weakest tags with new keywords from 'py main.py expand'"),
    ("- Co favorite/cart -> lam them 3 bien the thiet ke ngay",
     "- Any favorite/cart -> make 3 more design variations immediately"),
    # gtrends report stays English already
]


def translate(text):
    for vi, en in VI2EN:
        text = text.replace(vi, en)
    return text


def finalize_report(path):
    """Write EN sibling and export PDFs for both languages."""
    from src.timestamp import stamp_file, report_type_for
    path = Path(path)
    base_type = report_type_for(path)
    ts = stamp_file(path, base_type + " VI", None)
    en_path = path.with_name(path.stem + "_EN" + path.suffix)
    en_text = translate(path.read_text(encoding="utf-8"))
    en_text = en_text.replace(f"Report type: {base_type} VI",
                              f"Report type: {base_type} EN", 1)
    en_path.write_text(en_text, encoding="utf-8")
    try:
        from src.pdf_export import md_to_pdf
        for p in (path, en_path):
            pdf = md_to_pdf(p)
            if pdf:
                print(f"  PDF: {pdf}")
    except Exception as exc:
        print(f"  (PDF export failed: {exc})")
    return en_path


# --- V15: manager report is authored in ENGLISH; this produces the VI file ---
EN2VI_MANAGER = [
    ("# Etsy Product Manager Report", "# Bao cao Quan ly San pham Etsy"),
    ("## 0. BLOCKED BEFORE PUBLISHING - fix these first",
     "## 0. CHAN TRUOC KHI DANG - xu ly truoc"),
    ("supplier details confirmed", "da xac nhan chi tiet supplier"),
    ("primary keyword data verified", "da kiem chung du lieu tu khoa chinh"),
    ("trademark status verified or approved",
     "trademark da xac minh hoac duoc duyet"),
    ("competitor audit complete", "da hoan tat audit doi thu"),
    ("no placeholders remain", "khong con placeholder"),
    ("profit model complete", "mo hinh loi nhuan hoan chinh"),
    ("exactly 13 tags", "du dung 13 tag"),
    ("product category confirmed", "da xac nhan category"),
    ("production partner confirmed", "da xac nhan production partner"),
    ("mockup/image checklist complete", "hoan tat checklist anh/mockup"),
    ("**NOTHING below may be published until every box above is checked. "
     "Design preparation may proceed only if DESIGN_PREP_READY = true.**",
     "**KHONG DUOC dang bat cu listing nao ben duoi cho den khi moi o tren "
     "duoc tick. Chi duoc chuan bi thiet ke neu DESIGN_PREP_READY = true.**"),
    ("## 1. Report Status", "## 1. Trang thai bao cao"),
    ("- Traffic light: ", "- Den tin hieu: "),
    ("GREEN - ready for manager review", "XANH - san sang cho manager duyet"),
    ("YELLOW - ready for design preparation",
     "VANG - san sang chuan bi thiet ke"),
    ("GREEN - ready for publishing", "XANH - san sang dang"),
    ("RED - NOT ready for publishing", "DO - CHUA duoc dang"),
    ("- Reason: ", "- Ly do: "),
    ("**Rule: do not publish any listing unless PUBLISH_READY = true.**",
     "**Quy tac: KHONG dang listing nao khi PUBLISH_READY chua = true.**"),
    ("## 2. Executive Decision", "## 2. Quyet dinh dieu hanh"),
    ("## 3. Best Product Cluster", "## 3. Cum san pham tot nhat"),
    ("## 4. Supplier Pull Commands Used", "## 4. Lenh keo supplier da dung"),
    ("## 5. Design Briefs to Prepare ", "## 5. Brief thiet ke can chuan bi "),
    ("(DESIGN_PREP_READY - do NOT finalize until section 0 clears)",
     "(DESIGN_PREP_READY - KHONG hoan thien cho den khi muc 0 xong)"),
    ("## 6. Supporting Keywords (by cluster)",
     "## 6. Tu khoa ho tro (theo cum)"),
    ("## 7. Profit Model", "## 7. Mo hinh loi nhuan"),
    ("- Cluster recommended price:", "- Gia de xuat cua cum:"),
    ("- Test listing price:", "- Gia listing thu nghiem:"),
    ("## 8. Supplier Details", "## 8. Chi tiet supplier"),
    ("## 9. Competitor Audit", "## 9. Audit doi thu"),
    ("## 10. Listing Packages", "## 10. Goi listing"),
    ("## 11. Rejected Ideas", "## 11. Y tuong bi loai"),
    ("## 12. Trademark Queue", "## 12. Hang doi trademark"),
    ("## 13. 7-Day Validation Plan (conditional on PUBLISH_READY)",
     "## 13. Ke hoach kiem chung 7 ngay (dieu kien PUBLISH_READY)"),
    ("## 14. Today's Team Tasks", "## 14. Viec cua team hom nay"),
    ("**Designer:**", "**Designer (thiet ke):**"),
    ("**Seller:**", "**Seller (dang bai):**"),
    ("**Researcher:**", "**Researcher (nghien cuu):**"),
    ("**Manager:**", "**Manager (quan ly):**"),
    ("## 15. Manager Summary", "## 15. Tom tat cua Manager"),
    ("## 16. Final QA", "## 16. QA cuoi cung"),
    ("- Failed checks:", "- Kiem tra loi:"),
    ("- Passed checks:", "- Kiem tra dat:"),
    ("- Final instruction: **Do not publish any listing unless "
     "PUBLISH_READY = true.**",
     "- Chi thi cuoi: **KHONG dang bat cu listing nao khi PUBLISH_READY "
     "chua = true.**"),
    ("IF PUBLISH_READY = true:", "NEU PUBLISH_READY = true:"),
    ("| IF false: finish Section 0 blockers first - do NOT publish; "
     "continue design prep, supplier checks, trademark checks, competitor "
     "audit only.",
     "| NEU false: xu ly het muc 0 truoc - KHONG dang; chi tiep tuc chuan "
     "bi thiet ke, kiem tra supplier, trademark, audit doi thu."),
    ("- PUBLISH BLOCKED BY: ", "- BI CHAN DANG BOI: "),
    ("## Operational Status", "## Trang thai van hanh"),
    ("## Required Team Actions", "## Viec team phai lam"),
    ("Manager decision:", "Quyet dinh cua Manager:"),
    ("No product can move to design, listing, final QA, or "
     "publish-ready today.",
     "Hom nay KHONG san pham nao duoc chuyen sang thiet ke, listing, "
     "QA cuoi hay publish-ready."),
    ("No fresh keyword_data.csv and live YTrends API unreachable.",
     "Khong co keyword_data.csv moi va API YTrends khong ket noi duoc."),
    ("| Claude Operator | Fix data input or credentials | Fresh "
     "keyword_data.csv or valid YTrends token |",
     "| Claude Operator | Sua du lieu dau vao hoac thong tin dang nhap | "
     "keyword_data.csv moi hoac token YTrends hop le |"),
    ("| Researcher | Provide verified keyword data | keyword_data.csv |",
     "| Researcher | Cung cap du lieu tu khoa da kiem chung | "
     "keyword_data.csv |"),
    ("| Manager | Do not approve publish | No publish-ready products "
     "today |",
     "| Manager | Khong duyet dang bai | Hom nay khong co san pham "
     "publish-ready |"),
    ("## 1b. Sales Execution Summary", "## 1b. Tom tat hanh dong ban hang"),
    ("- **What to sell:**", "- **Ban gi:**"),
    ("- **Why it will sell:**", "- **Vi sao se ban duoc:**"),
    ("- **What to design:**", "- **Thiet ke gi:**"),
    ("- **Supplier:**", "- **Supplier:**"),
    ("- **Expected profit:**", "- **Loi nhuan du kien:**"),
    ("- **Listing content:**", "- **Noi dung listing:**"),
    ("- **Competitors doing well / weaknesses to beat:**",
     "- **Doi thu dang lam tot / diem yeu de danh bai:**"),
    ("- **Check before publishing:**", "- **Kiem tra truoc khi dang:**"),
    ("- **First 7 days:**", "- **7 ngay dau:**"),
    ("- **Scale if it works:**", "- **Neu hieu qua thi nhan rong:**"),
    ("## 6b. Multi-Source Signal Check (beyond Etsy data)",
     "## 6b. Kiem tra tin hieu da nguon (ngoai du lieu Etsy)"),
    ("## 9c. Competitive Edge Plan - how we beat sellers with the same data",
     "## 9c. Ke hoach loi the canh tranh - cach thang seller dung cung du lieu"),
]


def finalize_manager(path):
    """Manager report: EN original + _VI sibling + PDFs for both."""
    from src.timestamp import stamp_file, report_type_for
    path = Path(path)
    base_type = report_type_for(path)
    stamp_file(path, base_type + " EN", None)
    text = path.read_text(encoding="utf-8")
    vi = text
    for en, v in EN2VI_MANAGER:
        vi = vi.replace(en, v)
    vi = vi.replace(f"Report type: {base_type} EN",
                    f"Report type: {base_type} VI", 1)
    vi_path = path.with_name(path.stem + "_VI" + path.suffix)
    vi_path.write_text(vi, encoding="utf-8")
    try:
        from src.pdf_export import md_to_pdf
        for p in (path, vi_path):
            pdf = md_to_pdf(p)
            if pdf:
                print(f"  PDF: {pdf}")
    except Exception as exc:
        print(f"  (PDF export failed: {exc})")
    return vi_path


# --- V15.1: team packs also get full VI siblings ---
EN2VI_PACKS = EN2VI_MANAGER + [
    ("# Claude Design Prompts", "# Prompt Thiet ke cho Claude"),
    ("How to use: copy ONE full prompt block below into Claude / Claude "
     "Design and send. The market data is for understanding buyers, "
     "never for copying competitor designs.",
     "Cach dung: copy TRON VEN mot khoi prompt ben duoi vao Claude / "
     "Claude Design roi gui. Du lieu thi truong chi de hieu khach mua, "
     "TUYET DOI khong copy thiet ke doi thu."),
    ("## PROMPT #", "## PROMPT (giu tieng Anh khi dan vao Claude) #"),
    ("# Seller Pack", "# Goi viec cho Seller"),
    ("## CANH BAO / WARNING", "## CANH BAO"),
    ("You may PREPARE listings as drafts. Do NOT click Publish "
     "until Section 0 of the manager report is fully checked.",
     "Chi duoc CHUAN BI listing dang nhap (draft). KHONG bam Publish cho "
     "den khi muc 0 cua bao cao manager duoc tick het."),
    ("Paste in this order in Etsy Shop Manager -> Add a listing:",
     "Dan theo dung thu tu nay trong Etsy Shop Manager -> Add a listing "
     "(ten muc giu tieng Anh de khop man hinh Etsy):"),
    ("Publish blocked by: ", "Dang bi chan boi: "),
    ("(required for POD - do not skip)",
     "(bat buoc voi POD - khong duoc bo qua)"),
    ("After publish: open as buyer, test personalization box, log "
     "URL + date in the team tracker.",
     "Sau khi dang: mo listing nhu khach mua, thu o personalization, ghi "
     "URL + ngay vao file theo doi cua team."),
]


def finalize_pack(path):
    """Team pack: EN original + _VI sibling + PDFs for both."""
    from src.timestamp import stamp_file, report_type_for
    path = Path(path)
    base_type = report_type_for(path)
    stamp_file(path, base_type + " EN", None)
    text = path.read_text(encoding="utf-8")
    vi = text
    for en, v in EN2VI_PACKS:
        vi = vi.replace(en, v)
    vi = vi.replace(f"Report type: {base_type} EN",
                    f"Report type: {base_type} VI", 1)
    vi_path = path.with_name(path.stem + "_VI" + path.suffix)
    vi_path.write_text(vi, encoding="utf-8")
    try:
        from src.pdf_export import md_to_pdf
        for p in (path, vi_path):
            md_to_pdf(p)
    except Exception:
        pass
    return vi_path
