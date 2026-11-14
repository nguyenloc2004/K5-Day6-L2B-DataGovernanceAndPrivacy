# Kế hoạch demo T08 · Bảng điều khiển xử lý yêu cầu xóa dữ liệu

Bổ sung cho [PLAN_T08.md](PLAN_T08.md). Mục tiêu: demo trông và vận hành như một công cụ thật mà đội privacy/DPO của công ty dùng hằng ngày, nhưng vẫn chạy **offline 100%** bằng đúng lệnh của lab.

## 1. Ý tưởng

Trong thực tế, các công ty xử lý yêu cầu xóa dữ liệu (DSR, *Data Subject Request*) bằng một "console": danh sách yêu cầu kèm hạn chót, mở từng yêu cầu ra thấy dữ liệu của người đó nằm ở đâu, máy đề xuất xóa/giữ/chuyển duyệt, người phụ trách duyệt, hệ thống thực thi và lưu bằng chứng.

Nhóm làm phiên bản thu nhỏ của console đó:

- **Không cần server, không cần mạng.** Pipeline sinh ra một file `out/poc/dashboard.html` duy nhất, dữ liệu nhúng sẵn bên trong, mở bằng trình duyệt là xem được.
- **Không thêm logic mới.** Dashboard chỉ hiển thị những gì pipeline đã tạo (`actions.csv`, `review_queue.csv`, `audit_log.jsonl`, `decision.json`, `run_info.json`, và graph đầu vào).
- **Không ảnh hưởng điểm.** Chạy sau khi `actions.csv` đã ghi xong; dashboard lỗi thì pipeline vẫn exit 0 (bắt lỗi, ghi cảnh báo).

## 2. Luồng nghiệp vụ mô phỏng

Dashboard thể hiện mỗi yêu cầu đi qua các trạng thái như ngoài đời:

```
TIẾP NHẬN → XÁC MINH DANH TÍNH → TRUY TÌM DỮ LIỆU → KẾ HOẠCH (dry-run)
          → CHỜ DUYỆT (nếu có escalate) → ĐÃ DUYỆT → ĐÃ THỰC THI (tombstones)
```

| Trạng thái | Lấy từ đâu |
|---|---|
| Tiếp nhận, hạn chót | `requests.json` (`received_at`, `deadline`, `channel`) |
| Xác minh danh tính | `identity_verified` |
| Truy tìm dữ liệu | Các dòng của yêu cầu trong `actions.csv`, `lineage_path` |
| Kế hoạch | `dry_run: true` → mọi action là đề xuất |
| Chờ duyệt / đã duyệt | Dòng `escalate` có hay chưa có quyết định trong `review_queue_reviewed.csv` |
| Đã thực thi | `dry_run: false` và có `tombstones.json` (việc của M1 trong PLAN_T08) |

## 3. Các màn hình

Một file HTML, 5 tab. Thứ tự ưu tiên: P0 bắt buộc có trước phút 145, P1 nên có, P2 làm trong 24 giờ sau.

### Tab 1 · Hộp yêu cầu (P0)

Bảng 10 yêu cầu, giống inbox của hệ thống ticket:

| Cột | Ví dụ |
|---|---|
| Mã yêu cầu, chủ thể | DR-002 · subj_03 |
| Nhận lúc, hạn chót, **còn bao nhiêu ngày** | 02/11 → 02/12 · còn 18 ngày (đỏ khi < 7 ngày) |
| Trạng thái | Badge: `Chờ duyệt (3)` / `Đã duyệt` / `Đã thực thi` |
| Đếm action | 🟢 12 xóa · 🟡 1 giữ · 🟠 2 chờ duyệt |

Phía trên bảng: 4 ô số tổng (tổng artefact trong phạm vi, sẽ xóa, giữ theo luật, chờ duyệt) và kết luận `GO/HOLD` từ `decision.json` kèm `reason_code` và `owner`.

Bấm một dòng thì mở Tab 2 của yêu cầu đó.

### Tab 2 · Chi tiết yêu cầu và cây dữ liệu (P0, màn hình "wow")

Vẽ **cây lineage** của dữ liệu thuộc người yêu cầu, mỗi node một ô:

```
[a0043 raw_video 🔒 LH-2026-03]  ← vàng: giữ theo legal hold
 ├ [a0044 backup]                ← xanh: xóa (viền nét đứt: phái sinh của bản bị hold)
 ├ [a0045 frame] ── [a0046 face_crop] ── [a0047 embedding]
 │                         └ [a0211 training_export · 10 người]  ← cam: chờ duyệt
 └ ...
```

- Màu theo action: xanh = `delete`, vàng = `retain_legal_hold`, cam = `escalate`, **xám = ngoài phạm vi** (node của người khác, hiện mờ để thấy vì sao không xóa, đây chính là bẫy B6).
- Biểu tượng nhỏ trên node: 🔒 legal hold, 👥 nhiều chủ thể, ❓ không rõ nguồn gốc, 🏢 thuộc vendor.
- Rê chuột hoặc bấm vào node: hiện `reason_code`, luật đã khớp (R1–R7), `uri`, `acl`, `owner`, đường đi lineage.
- Bên phải cây: bảng các dòng của yêu cầu, lọc được theo action.

Kỹ thuật: vẽ bằng SVG hoặc HTML/CSS tự sinh trong Python. **Không dùng thư viện tải từ CDN** (Mermaid, D3…) vì demo phải offline. Cây T08 nông (tối đa 4 tầng), nên xếp theo tầng là đủ.

Ba yêu cầu nên chuẩn bị sẵn để demo:

| Yêu cầu | Cho thấy |
|---|---|
| DR-001 | Bẫy B6: frame chung 2 người được escalate, con cháu của người khác hiện xám, không bị xóa |
| DR-002 | Legal hold: video giữ lại, bản phái sinh xóa nhưng được đánh dấu cần xem |
| DR-008 | Backup do vendor giữ: escalate vì không có quyền |

### Tab 3 · Hàng chờ duyệt (P0)

Dùng lại công cụ có sẵn của BTC `src/common/contact_sheet.py::render_contact_sheet` (bản HTML offline có dropdown quyết định và nút **Export CSV**), sinh ra `out/poc/contact_sheet.html`. Dashboard có nút mở file này.

Vòng thao tác khi demo:

1. Người duyệt nhập tên, chọn `approve/reject/edit/escalate` cho vài dòng, ghi chú lý do.
2. Bấm **Export CSV**, chép file thành `out/poc/review_queue_reviewed.csv`.
3. Chạy lại lệnh PoC. Dashboard cập nhật: số "chờ duyệt" giảm, trạng thái yêu cầu đổi, audit có tên người duyệt.

### Tab 4 · Nhật ký kiểm toán (P1)

Dòng thời gian đọc từ `audit_log.jsonl`: giờ, người thực hiện (`pipeline` hoặc tên người duyệt), hành động, artefact, lý do. Lọc theo yêu cầu hoặc theo người thực hiện. Cho thấy nhật ký chỉ ghi thêm, không sửa.

### Tab 5 · Kết quả và so sánh (P1)

- Bảng baseline và PoC lấy từ `reports/table1_baseline_vs_poc.md` nếu có (cần `gt/` của giảng viên). Nếu không có thì hiện số tự kiểm của nhóm (graph mini, nhãn tay) và ghi rõ nguồn.
- Thông tin tái lập lấy từ `run_info.json`: seed, git sha, thời gian chạy, chế độ offline.

### Tab phụ · Biên bản xử lý cho từng yêu cầu (P2)

Trang in được (Ctrl+P) gửi lại người yêu cầu: đã xóa bao nhiêu mục, giữ mục nào và vì sao, mục nào đang chờ duyệt, hạn xử lý tiếp. Chỉ hiển thị dữ liệu đã có.

## 4. Thiết kế kỹ thuật

### File và người sở hữu

| File | Người sở hữu | Nội dung |
|---|---|---|
**Cập nhật:** M1 đã làm toàn bộ phần code demo (nhánh `m1/demo-dashboard`). Cây được dựng ngay trong `dashboard.py` nên không phải sửa `lineage.py` của M2.

| File | Người sở hữu | Nội dung |
|---|---|---|
| `src/t08/dashboard.py` (mới) | **M1** ✅ | Gom dữ liệu, dựng và xếp cây cho từng yêu cầu (`build_tree`), chèn JSON vào template, ghi `dashboard.html` |
| `src/t08/templates/dashboard.html` (mới) | **M1** ✅ | HTML, CSS, JS thuần nhúng trong file. Đọc JSON nhúng sẵn và vẽ 5 tab |
| `src/pipeline.py` | **M1** ✅ | Ở bước `rank`: gọi `render_contact_sheet`. Cuối `run()`: gọi `dashboard.render_dashboard`, bọc `try/except`, lỗi thì ghi audit `dashboard_failed`. Sửa cách đếm mục chờ duyệt |
| `tests/test_t08_dashboard.py` (mới) | **M1** ✅ | 4 test: offline, đủ yêu cầu; cây đánh dấu đúng dữ liệu người khác; vòng duyệt làm giảm số chờ duyệt; dashboard lỗi không làm hỏng lần chạy |
| `demo/` | M1 (ảnh), M5 (slides) | Ảnh chụp 3 tab đầu và `demo/README.md` (kịch bản, lệnh). M5 làm slides |

### Dữ liệu nhúng vào HTML

```json
{
  "run": {"git_sha": "...", "seed": 42, "dry_run": true, "generated_at": "..."},
  "decision": {"status": "HOLD", "reason_code": "...", "owner": "..."},
  "requests": [{"request_id": "DR-001", "subject_id": "subj_01", "deadline": "...", "counts": {...}, "status": "..."}],
  "rows": [{"request_id": "...", "artefact_id": "...", "action": "...", "reason": "...", "rule_id": "...", "lineage_path": "..."}],
  "trees": {"DR-001": {"nodes": [...], "edges": [...]}},
  "audit": [{"ts": "...", "actor": "...", "action": "...", "item_id": "..."}],
  "metrics": {"baseline": {...}, "poc": {...}}
}
```

### Ràng buộc

- Không tải gì từ Internet: không CDN, không font Google. Kiểm bằng test.
- Mọi thứ sinh từ output của lần chạy. Không có số gõ tay trong HTML.
- "Còn bao nhiêu ngày" tính theo ngày chạy, ghi ngày đó trên màn hình để người xem hiểu.
- Không hiển thị gì ngoài dữ liệu fixture (vốn là giả lập, không có PII thật).
- File tự chứa, dưới 2 MB, mở được bằng Chrome/Edge không cần quyền gì.

## 5. Kịch bản demo (5 phút)

| Phút | Người nói | Màn hình | Nội dung |
|---|---|---|---|
| 0:00 | M1 | Terminal | "Công ty nhận 10 yêu cầu xóa dữ liệu." Chạy 1 lệnh PoC, exit 0, thời gian chạy dưới 1 giây |
| 0:40 | M1 | Tab 1 | 10 yêu cầu, hạn chót, kết luận `HOLD` vì còn 28 mục chờ duyệt |
| 1:10 | M2 | Tab 2, DR-001 | Cây dữ liệu. Chỉ vào node xám: "duyệt cây ngây thơ sẽ xóa ảnh mặt của người khác" |
| 1:50 | M3 | Tab 2, DR-002 và DR-008 | Legal hold được giữ, giải thích quyết định Q1; backup của vendor phải chuyển duyệt |
| 2:40 | M5 | Tab 3 | Duyệt trực tiếp 2–3 dòng, Export CSV, chạy lại lệnh |
| 3:30 | M5 | Tab 1 và Tab 4 | Số chờ duyệt giảm, audit có tên người duyệt |
| 4:00 | M4 | Tab 5 | Baseline và PoC, các test, chạy 2 lần ra cùng kết quả |
| 4:30 | M1 | Slide cuối | Giới hạn và giả định cần pháp chế xác nhận |

Phương án dự phòng: ảnh chụp từng bước trong `demo/` và một bản `dashboard.html` đã sinh sẵn. Máy demo trục trặc thì mở ảnh, không dựng lại tại chỗ.

## 6. Lịch làm (lồng vào lịch 240 phút của PLAN_T08)

Code demo đã xong (5 tab, contact sheet, test). Việc còn lại:

| Phút | M1 | M2, M3, M4 | M5 |
|---|---|---|---|
| Còn lại đến 145 | Merge nhánh `m1/demo-dashboard`; nếu M2/M3 đổi logic thì chạy lại, chụp lại ảnh | Đọc `demo/README.md`, mở dashboard, chuẩn bị phần nói của mình | Slides 3–5 trang, dùng ảnh trong `demo/` |
| 145–170 | Tập demo 2 lần cùng nhóm, thử vòng duyệt thật | Tập phần nói | Tập phần nói |
| 170–180 | Tag `demo-180m` | | |

## 7. Định nghĩa "xong"

- [x] Chạy lệnh PoC sinh `dashboard.html` và `contact_sheet.html`, pipeline vẫn exit 0.
- [x] Dashboard không tải gì từ Internet; cả 5 tab render được (kiểm bằng Chrome headless).
- [x] Tab 2 vẽ cây cho từng yêu cầu, có node xám ngoài phạm vi (DR-001: `a0012`, `a0013`).
- [x] Vòng duyệt làm số chờ duyệt giảm và audit có tên người duyệt (có test tự động).
- [x] `test_t08_dashboard.py` xanh.
- [x] Ảnh chụp 3 tab đầu trong `demo/`.
- [ ] Slides trong `demo/` (M5).
- [ ] Đã tập kịch bản 5 phút ít nhất 2 lần.
