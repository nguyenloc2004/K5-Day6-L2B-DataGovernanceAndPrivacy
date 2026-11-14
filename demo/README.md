# Demo T08 · DSR Console

Kế hoạch đầy đủ: [docs/PLAN_DEMO_T08.md](../docs/PLAN_DEMO_T08.md).

## Chuẩn bị (trước khi lên trình bày)

```powershell
# Xóa output cũ (audit log chỉ ghi nối thêm)
Remove-Item -Recurse -Force out -ErrorAction SilentlyContinue

# 1. Baseline (để Tab 5 có cột so sánh)
python -m src.main --track t08 --pipeline src.t08.baseline --output out/baseline --run-name baseline --offline --seed 42

# 2. PoC: sinh actions.csv, review_queue.csv, contact_sheet.html, dashboard.html
python -m src.main --config configs/lab.yaml --track t08 --output out/poc --run-name poc --offline --seed 42

# 3. Mở bảng điều khiển
start out\poc\dashboard.html
```

Dashboard là một file HTML tự chứa, mở offline được. Mỗi lần chạy lại lệnh PoC thì file được sinh lại; bấm F5 trên trình duyệt để cập nhật.

## Kịch bản 5 phút

| Phút | Người nói | Màn hình | Nội dung |
|---|---|---|---|
| 0:00 | M1 | Terminal | "Công ty nhận 10 yêu cầu xóa dữ liệu." Chạy lệnh PoC, exit 0, dưới 1 giây |
| 0:40 | M1 | Tab 1 | 10 yêu cầu, hạn chót; 158 artefact trong phạm vi: 128 xóa, 2 giữ, 28 chuyển duyệt; kết luận `HOLD` |
| 1:10 | M2 | Tab 2, DR-001 | Frame `a0011` có 2 người nên chuyển duyệt. Ảnh mặt `a0012` và embedding `a0013` bên dưới là của subj_00 (xám), **không xóa** dù nằm dưới node của người yêu cầu |
| 1:50 | M3 | Tab 2, DR-002 rồi DR-008 | Video `a0043` giữ vì legal hold, bản phái sinh viền nét đứt (xóa nhưng cần lưu ý, quyết định Q1). DR-008: backup do `vendor-x` quản lý nên chuyển duyệt |
| 2:40 | M5 | Tab 3 → trang duyệt | Bấm "Mở trang duyệt", nhập tên, approve 2–3 dòng, Export CSV |
| 3:10 | M5 | Terminal | Chép file tải về thành `out\poc\review_queue_reviewed.csv`, chạy lại lệnh PoC |
| 3:30 | M5 | Tab 3, Tab 4 | Số chờ duyệt giảm; nhật ký có tên người duyệt |
| 4:00 | M4 | Tab 5 | Baseline (10 dòng, chỉ xóa video gốc, xóa cả video đang bị giữ) và PoC; các test |
| 4:30 | M1 | Slide cuối | Giả định cần pháp chế xác nhận, giới hạn |

Lệnh chép file sau khi Export CSV (file tải về nằm trong thư mục Downloads):

```powershell
Copy-Item "$env:USERPROFILE\Downloads\review_queue_reviewed.csv" out\poc\review_queue_reviewed.csv
```

## Ảnh chụp dự phòng

| File | Nội dung |
|---|---|
| `01_hop_yeu_cau.png` | Tab 1 · Hộp yêu cầu |
| `02_cay_du_lieu_DR-001.png` | Tab 2 · Cây dữ liệu DR-001 (bẫy B6) |
| `03_hang_cho_duyet.png` | Tab 3 · Hàng chờ duyệt |

Máy demo trục trặc thì mở các ảnh này thay vì dựng lại tại chỗ.
