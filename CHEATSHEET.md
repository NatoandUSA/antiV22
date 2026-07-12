# Etsy Product Manager — Cheat Sheet (V28.1)

## 🧭 YTuong vs. Dashboard — phân biệt rõ

> **YTuong/HeyEtsy = nơi TÌM dữ liệu thị trường. Dashboard này = nơi biến dữ liệu đó
> thành HÀNH ĐỘNG của team.** Không clone YTuong — chỉ link tới và **import** từ nó.

| Dùng **YTuong / HeyEtsy** để TÌM | Dùng **Dashboard** để THỰC THI |
|---|---|
| listing hot, Etsy's Picks, shop top | giao việc cho nhân viên |
| views / favorites / sold, tag, ảnh | kiểm tra NCC + lợi nhuận |
| lịch mùa vụ | dựng nháp listing (**tiếng Anh**) + brief thiết kế |
| link: [trending](https://trends.ytuong.ai/en/trending) · [hidden gems](https://trends.ytuong.ai/en/hidden-gems) · [spy](https://trends.ytuong.ai/en/spy) · [HeyEtsy hot](https://ytuong.me/hot) | duyệt Publish Gate · theo dõi Ngày 3/7 · học |

**Luồng:** research trên YTuong → 📥 **Import Center** → 🧭 **Research Queue** →
**Build Workspace** (giữ product mode) → task → nháp → **Manager duyệt** →
*đăng bằng tay chỉ khi được duyệt* → Ngày 3/7.

> ⚠️ **PUBLISH_AUTOMATION = false.** Dashboard **không bao giờ** đăng lên Etsy. Listing
> chỉ được đăng **bởi người thật, bằng tay**, khi Workspace báo **Publish-ready = yes**
> + Manager ký duyệt.

---

**Bản ngắn gọn:** công cụ tự chạy. **VPS tự làm mới dữ liệu keyword mỗi ~6 giờ**, team
chỉ **bấm nút trên trình duyệt — không cần terminal, không cần lệnh**. Đóng cửa sổ SSH
**KHÔNG** làm sập web (nó chạy nền). Chỉ mở terminal cho vài việc admin hiếm gặp dưới đây.

## Gõ lệnh ở đâu — dùng Python nào

| Nơi | Mở bằng | Python gõ |
|---|---|---|
| 🌍 **Dashboard** (etsy.theglobalserviceteam.site) | trình duyệt | *không — chỉ bấm nút* |
| 🖥️ **VPS** (server) | SSH, rồi `cd ~/etsy-agent` | **`.venv/bin/python`** |
| 💻 **Laptop** | PowerShell (Win) / Terminal (Mac) | `py` (Win) · `python3` (Mac) |

> ⚠️ **Trên VPS luôn dùng `.venv/bin/python`, không dùng `python3` trần** (sẽ báo
> `No module named 'dotenv'`). Mẹo: chạy `source .venv/bin/activate` 1 lần/phiên.

## 🆘 Mở lại VPS (sau khi đóng cửa sổ / server khởi động lại)

```bash
ssh -p 55317 etsy@51.79.200.65      # mật khẩu gõ sẽ không hiện — bình thường
cd ~/etsy-agent
systemctl status etsy-web --no-pager      # tìm dòng "active (running)"
systemctl status etsy-tunnel --no-pager
sudo systemctl restart etsy-web etsy-tunnel   # nếu 1 trong 2 KHÔNG chạy
#  Web: https://etsy.theglobalserviceteam.site
```

`q` thoát màn hình `status`; `exit` đóng SSH (web vẫn chạy).

## 🖥️ Lệnh admin trên VPS (hiếm khi cần) — nhớ tiền tố `.venv/bin/`

| Lệnh | Làm gì |
|---|---|
| `git pull` | Lấy code mới nhất tôi đã push. |
| `sudo systemctl restart etsy-web` | Nạp code mới vào web (~5s). Chỉ cần **sau khi `git pull` đổi code**. |
| `.venv/bin/python main.py warm --fresh` | Làm mới Trending/Opportunities **ngay bây giờ**. (Tự chạy mỗi 6h.) |
| `.venv/bin/python main.py healthcheck --with-tests` | **Kiểm tra thật:** deps + pytest + cờ readiness. Chỉ báo **SYSTEM_READY_FOR_TEAM_USE: true** khi mọi thứ pass **trên VPS**. |
| `.venv/bin/python main.py cron status` | Auto-refresh đã cài chưa? chạy lần cuối? |
| `.venv/bin/python main.py clean` | **Dọn ổ đĩa** (cắt archive cũ, prune cache). An toàn, chạy hàng tháng. |
| `.venv/bin/python main.py daily-run` | Job đêm: keyword + feeds + warm + summary. **Không đăng bài.** |

**Cập nhật web sau khi tôi push code:**
```bash
cd ~/etsy-agent && git pull && sudo systemctl restart etsy-web
```

## 📦 Đóng gói bản giao (chỉ khi cần gửi/deploy bản sạch)

```bash
py main.py package release      # (Mac: python3)  -> dist/etsy-product-manager-v28.1.zip
```
Gói này **chỉ** chứa code + dữ liệu tham chiếu NCC. **Tự loại bỏ** `.env`, `.git`,
log, cache, và **DB thật** (`app.db`/`agent.db` + toàn bộ dữ liệu team). Nếu có gì rò
rỉ, lệnh **tự xóa gói và báo lỗi**. Trên máy mới: giải nén → `py main.py auth
create-admin ...` để tạo admin đầu tiên (DB tự khởi tạo).

## 💻 Trên laptop — tùy chọn (không cần hằng ngày)

| Lệnh | Làm gì |
|---|---|
| `py main.py selftest` | Kiểm tra nhanh sau mỗi thay đổi. Phải báo **ALL CHECKS PASSED**. Offline. |
| `py main.py web` | Xem thử toàn bộ dashboard tại máy. `Ctrl+C` để dừng. |
| `py main.py workspace build --keyword "usa raccoon shirt" --mode pod` | Dựng 1 workspace từ terminal. |

> Mac dùng `python3`. Vài lệnh research sâu (`expand`, `discover`, `ideas`, `grow`)
> dùng nguồn cookie cũ — chạy trên laptop. Dữ liệu keyword hằng ngày dùng YTrends MCP
> công khai (chạy được cả trên VPS — nên auto-refresh 6h chạy ở server).

## Quy tắc vàng
1. **Team dùng dashboard; bạn hiếm khi động vào terminal.** VPS tự làm mới mỗi ~6h.
2. **Trên VPS luôn `.venv/bin/python …`** (không dùng `python3` trần).
3. Sau khi tôi push code: trên VPS `git pull` (+ `sudo systemctl restart etsy-web` nếu đổi code).
4. **Không tự đăng.** Listing đăng **thủ công**, chỉ khi **PUBLISH_READY = true**.
5. Chạy `py main.py selftest` sau mỗi thay đổi — phải **ALL CHECKS PASSED**.
6. **Không bao giờ chia sẻ `.env`** — nó chứa mật khẩu và token của bạn.
