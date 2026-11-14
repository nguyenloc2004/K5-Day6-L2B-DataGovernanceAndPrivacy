# Metric contract (khai báo bắt buộc — chốt ở phút 30, trước khi chạy eval)

> Các metric chuẩn đã được cài trong `src/metrics/tracks.py`. File này là nơi nhóm **cam kết** cách dùng chúng.
> Không đổi testset, threshold hay trọng số sau khi đã thấy kết quả eval.

| Mục | Khai báo của nhóm |
|---|---|
| Track | **T08 · Retention & Delete Request Simulator** |
| Primary metric (tên đúng như evaluator in ra) | `Deletion Completeness` |
| Tăng tốt hay giảm tốt? | **higher** (càng cao càng tốt, mục tiêu 100%) |
| Đơn vị đánh giá (image / region / pair / release / batch / case …) | Cặp `(request_id, artefact_id)` |
| Công thức + numerator / denominator | `must-delete artefacts deleted / must-delete artefacts` (done / len(must)) |
| Cách ghép prediction ↔ GT (IoU? id? tolerance?) | Khóa ghép chính xác theo cặp `[request_id, artefact_id]` |
| Candidate pool cố định | 158 cặp `(request_id, artefact_id)` từ 10 yêu cầu và 212 artefact trong `fixtures/t08_deletion` |
| Review budget B / K | **B = 60** (đủ bao quát toàn bộ các ca ngoại lệ và phái sinh từ hold) |
| Seed | **42** |
| Threshold policy (chọn trên dev như thế nào) | Thứ tự ưu tiên đóng băng (Policy Precedence):<br>1. `LEGAL_HOLD_ACTIVE` $\rightarrow$ `retain_legal_hold`<br>2. `IDENTITY_UNVERIFIED` $\rightarrow$ `escalate`<br>3. `NO_DELETE_PERMISSION` $\rightarrow$ `escalate`<br>4. `UNKNOWN_ORIGIN` $\rightarrow$ `escalate`<br>5. `MULTI_SUBJECT` $\rightarrow$ `escalate`<br>6. `DERIVED_FROM_HELD` (khi descendants) $\rightarrow$ `retain_legal_hold`<br>7. `SUBJECT_ONLY` $\rightarrow$ `delete` |
| Eval split (không dùng để tune) | Toàn bộ fixture `fixtures/t08_deletion` và bộ đối chứng `tests/data/t08_mini` |
| Chỉ số lỗi xấu (miss / false alarm / false reject) | **`False-delete count` (Mục tiêu = 0)**: đếm số lần xóa nhầm dữ liệu đang có ngoại lệ hoặc xóa nhầm ngoài phạm vi yêu cầu |
| Slices sẽ báo cáo (≥2) | 1. Slice theo hành động kỳ vọng: `delete`, `retain_legal_hold`, `escalate`<br>2. Slice theo loại artefact: `raw_video`, `frame`, `face_crop`, `embedding`, `backup`, `annotation`, `training_export` |
| Cách báo độ bất định khi N nhỏ (Wilson CI / bootstrap) | Wilson score interval 95% cho tỷ lệ Deletion Completeness và Exception Handling Accuracy |
| Quyết định chốt Q1 – Q3 | **Q1:** `hold_scope: direct` (Hold trên video gốc không lan xuống con cháu, con cháu `delete` kèm reason `DERIVED_FROM_HELD`).<br>**Q2:** Dữ liệu nhiều chủ thể (Multi-subject) $\rightarrow$ `escalate`.<br>**Q3:** Review budget $B = 60$. |
| Ngày giờ chốt + người chốt | **2026-11-14 16:30 (Giờ VN) · M5 (Nguyễn Hải Nam)** |

---
**Cam kết Baseline:**
* Thuật toán Baseline ngây thơ (`src.t08.baseline`): chỉ xóa `raw_video` theo tên file, không xét lineage và legal hold.
* Kết quả dự kiến Baseline: Deletion Completeness ~ 6.25% (8/128), False-delete = 2 (xóa nhầm 2 video đang bị hold `a0043` và `a0099`).

