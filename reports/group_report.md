# Group Report — Day 06 Data Lab (Field-to-Release PoC)

## 00 · Header

| Mục | Giá trị |
|---|---|
| Group ID | G08 |
| Challenge | **T08 · Retention & Delete Request Simulator** |
| Thành viên (5) + vai trò | 1. Nguyễn Hữu Lộc (`nguyenhuuloc.122004@gmail.com`) — Lead / Integrator (M1)<br>2. Bùi Sỹ Tùng (`buisytungk25cntt@gmail.com`) — Data & Lineage (M2)<br>3. Trịnh Đức Hưng (`hungductrinh2004@gmail.com`) — Policy / Precedence Engine (M3)<br>4. Dương Dũng (`duongdung04bg@gmail.com`) — QA / Metrics / Tests (M4)<br>5. Nguyễn Hải Nam (`Khongcomatkhau@2005`) — Human Review / Audit / Report (M5) |
| Git URL | https://github.com/nguyenloc2004/K5-Day6-L2B-DataGovernanceAndPrivacy.git |
| Tag `demo-180m` (commit) | `demo-180m` |
| Tag `final-24h` (commit) | `final-24h` |
| Deadline (giờ VN) | 2026-11-15 17:00 |

---

## 01 · Problem statement

- **Ai bị ảnh hưởng / chịu hậu quả khi hệ thống sai:**
  - *Chủ thể dữ liệu (người dùng cá nhân):* Bị xâm phạm quyền riêng tư nghiêm trọng nếu dữ liệu cá nhân (đặc biệt là vector khuôn mặt/embedding) không được xóa triệt để hoặc bị xóa nhầm dữ liệu của người khác (ảnh chụp chung).
  * *Doanh nghiệp:* Chịu mức phạt hành chính khổng lồ (lên tới 4% doanh thu toàn cầu theo GDPR Điều 83 hoặc đình chỉ xử lý dữ liệu theo Nghị định 356/2025/NĐ-CP); đối mặt với trách nhiệm hình sự nếu tiêu hủy chứng cứ đang chịu lệnh giữ của cơ quan tư pháp (**Legal Hold**).
- **Điểm nghẽn cụ thể:**
  - Dữ liệu trong hệ thống AI/ML không đứng độc lập mà có phả hệ phức tạp: từ `raw_video` $\rightarrow$ `frame` $\rightarrow$ `face_crop` $\rightarrow$ `embedding` $\rightarrow$ `training_export`, cùng các bản sao lưu `backup`.
  - Nếu chỉ xóa theo tên tệp thô (cách làm ngây thơ), toàn bộ bản phái sinh và vector nhận diện vẫn tồn tại. Ngược lại, nếu duyệt BFS ngây thơ sẽ xóa nhầm con cháu của chủ thể khác (Bẫy B6) hoặc tiêu hủy dữ liệu đang bị phong tỏa pháp lý (Bẫy B1).
- **Đầu vào $\rightarrow$ Đầu ra:**
  - *Đầu vào:* 10 yêu cầu xóa dữ liệu cá nhân (`requests.json`) và đồ thị 212 tạo tác giả lập (`data_graph.json`) trong `fixtures/t08_deletion/`.
  - *Đầu ra:* Bảng quyết định hành động `out/poc/actions.csv` gồm 158 dòng `(request_id, artefact_id, action)` và nhật ký kiểm toán không thể sửa đổi `out/poc/audit_log.jsonl`.
- **Tiêu chí GO / HOLD / REWORK:**
  - `GO`: 100% các dòng nghi vấn (`escalate`) đã được chuyên viên pháp chế/DPO xem xét trong review queue và không có lỗi toàn vẹn dữ liệu.
  - `HOLD`: Còn tồn đọng dòng `escalate` chưa duyệt, hoặc phát hiện cảnh báo dữ liệu (vòng lặp chu trình, con trỏ cha trỏ tới artefact không tồn tại `DATA_WARNINGS`).
  - `REWORK`: Tỷ lệ Deletion Completeness < 95% hoặc False-delete count > 0 trên tập kiểm thử nội bộ.
- **Giả định của nhóm:**
  - **Q1 (Chính sách giữ):** Quyết định chọn `hold_scope: direct` — lệnh giữ chỉ áp dụng trực tiếp cho artefact mang cờ `legal_hold != null`. Các tệp con cháu phái sinh vẫn thực hiện xóa kèm lý do `DERIVED_FROM_HELD` theo nguyên tắc tối thiểu hóa dữ liệu (Data Minimization - GDPR Điều 5(1)(c)). Giả định này đã được chuẩn bị phương án đối chứng (Ablation) `hold_scope: descendants` để pháp chế/DPO thẩm định.

---

## 02 · Data & provenance

| Split | N | Nguồn / link | License | Synthetic? |
|---|---|---|---|---|
| Fixture chính (`fixtures/t08_deletion/`) | 212 artefacts, 10 requests (158 cặp) | Sinh bởi `tools/make_fixtures.py` (seed 42) | CC0-1.0 | Có (Synthetic mock) |
| Mini Gold Set (`tests/data/t08_mini/`) | 16 artefacts, 3 requests (18 cặp) | Viết tay bởi M4 phục vụ kiểm định độc lập | CC0-1.0 | Có (Hand-crafted) |

- **Schema & Thuộc tính:**
  - Mỗi artefact chứa: `artefact_id, type, subject_ids, parent_ids, uri, owner, acl, legal_hold, origin_known, created_at, filename`.
  - Loại tạo tác: `raw_video` (15), `backup` (15), `frame` (45), `face_crop` (45), `embedding` (45), `annotation` (45), `training_export` (2).
- **Seed:** Cố định `42`. Toàn bộ quá trình đọc và sắp xếp output đều dùng thuật toán ổn định (`mergesort`) theo cặp khóa `[request_id, artefact_id]`.
- **Kiểm tra Provenance:** Tệp `manifest.csv` đã được xác thực tính toàn vẹn mã băm SHA-256 (`53c2bd96...` cho `data_graph.json` và `aa7c66c4...` cho `requests.json`).

---

## 03 · Research & design

- **Tài liệu tham khảo cốt lõi:**
  1. *GDPR Article 17 (Right to Erasure) & 17(3) (Legal Exceptions):* Căn cứ không xóa dữ liệu khi có nghĩa vụ pháp lý lưu trữ.
  2. *Nghị định 356/2025/NĐ-CP & Luật 91/2025/QH15:* Quy định về nghĩa vụ xóa dữ liệu và bảo vệ quyền dữ liệu cá nhân tại Việt Nam.
  3. *California DELETE Act (SB 362 - DROP Platform):* Cơ chế xử lý yêu cầu xóa tập trung và kiểm toán minh bạch.
- **Sơ đồ Data Flow:**
  ```mermaid
  flowchart LR
      In[requests.json + data_graph.json] --> L[01 Load & Provenance]
      L --> P[02 Process: BFS Lineage + 7-Level Policy]
      P --> R[03 Rank: Top B=60 Queue]
      R --> Rev[04 Human Review & Overrides]
      Rev --> D[05 Decide: GO/HOLD Gate]
      D --> Out[actions.csv + audit_log.jsonl]
  ```
- **Thứ tự ưu tiên chính sách (Policy Precedence - 7 cấp độ):**
  1. Có lệnh giữ pháp lý (`legal_hold != null`) $\rightarrow$ `retain_legal_hold` (`LEGAL_HOLD_ACTIVE`).
  2. Danh tính chưa xác minh (`identity_verified == false`) $\rightarrow$ `escalate` (`IDENTITY_UNVERIFIED`).
  3. Hệ thống thiếu quyền hạn (`acl` không có `data-platform`) $\rightarrow$ `escalate` (`NO_DELETE_PERMISSION`).
  4. Nguồn gốc không rõ ràng (`origin_known == false`) $\rightarrow$ `escalate` (`UNKNOWN_ORIGIN`).
  5. Chứa nhiều chủ thể (`len(subject_ids) > 1`) $\rightarrow$ `escalate` (`MULTI_SUBJECT`).
  6. Bản phái sinh có tổ tiên bị hold (chế độ descendants) $\rightarrow$ `retain_legal_hold` (`DERIVED_FROM_HELD`).
  7. Dữ liệu hợp lệ của duy nhất người yêu cầu $\rightarrow$ `delete` (`SUBJECT_ONLY`).

---

## 04 · Baseline vs PoC

- **Baseline (`src.t08.baseline`):** Mô phỏng cách làm truyền thống ngây thơ: chỉ quét tệp `raw_video` có tên chứa mã `subject_id`, gán nhãn `delete`. Bỏ qua toàn bộ phả hệ và các ngoại lệ pháp lý.
- **PoC hoàn chỉnh (`src.pipeline`):** Truy vết phả hệ theo phạm vi `subject_ids`, kiểm tra 6 bẫy dữ liệu, áp dụng ma trận chính sách 7 cấp và hỗ trợ Human-in-the-loop review.
- Cùng seed 42, cùng offline mode, cùng dữ liệu đầu vào.

**Bảng 1 · So sánh chi tiết Baseline vs PoC**

| Metric (Đơn vị) | Baseline | PoC (Nhóm T08) | Độ cải thiện ($\Delta$) & Chú thích |
|---|---|---|---|
| **Primary: Deletion Completeness** | 6.25% (8/128) | **100.0% (128/128)** | **+93.75%** (Xóa sạch toàn diện) |
| **False-delete count** (Mục tiêu = 0) | **2** (Vi phạm nặng) | **0** (Tuyệt đối an toàn) | **-2** (Không vi phạm pháp lý) |
| **Exception handling accuracy** | 0.0% (0/30) | **100.0% (30/30)** | **+100.0%** (Nhận diện trọn vẹn ngoại lệ) |
| **Audit trace completeness** | 6.33% (10/158) | **100.0% (158/158)** | **+93.67%** (100% vết kiểm toán minh bạch) |
| **Số dòng Delete thực thi** | 10 dòng | 128 dòng | Bao phủ cả frame, crop, embedding, backup |
| **Số dòng Retain Legal Hold** | 0 dòng | 2 dòng | `a0043` và `a0099` được bảo vệ |
| **Số dòng Escalate (Chờ duyệt)** | 0 dòng | 28 dòng | Bảo vệ dữ liệu người khác không bị mất |
| **Thời gian thực thi (Runtime)** | 0.038s | 0.281s | Siêu nhanh, đạt chuẩn real-time |

---

## 05 · Evaluation protocol

- **Công thức Primary Metric:**
  $$\text{Deletion Completeness} = \frac{\text{Số artefact thuộc diện phải xóa đã gắn nhãn delete}}{\text{Tổng số artefact thuộc diện phải xóa}} = \frac{128}{128} = 1.0$$
- **Công thức False-delete count:**
  $$\text{False-delete} = \sum (\text{Ngoại lệ bị xóa nhầm}) + \sum (\text{Artefact bị xóa nằm ngoài phạm vi yêu cầu}) = 0$$
- **Đơn vị đánh giá:** Cặp khóa duy nhất `[request_id, artefact_id]`.
- **Review Budget:** $B = 60$ (đóng băng tại phút 30 theo `reports/metric_contract.md`).
- **Lệnh chạy và đánh giá chính xác:**
  ```powershell
  # Chạy PoC:
  python -m src.main --config configs/lab.yaml --track t08 --output out/poc --run-name poc --offline --seed 42
  # Chạy Baseline:
  python -m src.main --track t08 --pipeline src.t08.baseline --output out/baseline --run-name baseline --offline --seed 42
  ```

---

## 06 · Result slices & Failure Mode Analysis

| Slice phân loại | Tổng số (N) | Baseline | PoC | Phân tích hành vi |
|---|---|---|---|---|
| `must-delete` (Đủ điều kiện xóa) | 128 | 8 (6.25%) | 128 (100.0%) | Baseline bỏ quên 120 tệp con cháu và bản sao lưu |
| `retain_legal_hold` (Trát tòa) | 2 | 0 (0.0%) | 2 (100.0%) | Baseline xóa nhầm cả 2 (`a0043`, `a0099`) |
| `escalate` (Đa chủ thể / Thiếu quyền) | 28 | 0 (0.0%) | 28 (100.0%) | PoC đẩy toàn bộ 28 ca vào hàng đợi kiểm duyệt |

### Phân tích 3 Failure Mode bắt buộc:
1. **Failure Mode 1: Tiêu hủy chứng cứ đang bị phong tỏa (Bẫy B1 - Legal Hold)**
   * *Hiện tượng:* Tệp `a0043` (thuộc DR-002) có lệnh giữ `LH-2026-03` và `a0099` (thuộc DR-005) có lệnh giữ `LH-2026-07`.
   * *Baseline:* Xóa thẳng tay vì thấy tên tệp có chứa `subj_03` và `subj_07` $\rightarrow$ Phạm tội tiêu hủy tài liệu điều tra.
   * *PoC giải quyết:* Nhận diện cờ `legal_hold != null` ở mức ưu tiên cao nhất, gán `retain_legal_hold` và ghi hẹn xóa sau khi hết hạn giữ vào audit log.
2. **Failure Mode 2: Xóa ngây thơ bỏ sót định danh sinh trắc học (Xóa raw nhưng giữ embedding)**
   * *Hiện tượng:* Người dùng yêu cầu xóa, hệ thống chỉ xóa video `drive_subj_01_000.mp4`.
   * *Hậu quả:* Tệp `a0018` (vector đặc trưng khuôn mặt 512 chiều) vẫn tồn tại trong cơ sở dữ liệu vector. Hệ thống AI vẫn nhận diện được người dùng $\rightarrow$ Vi phạm quyền được quên (GDPR Art. 17).
   * *PoC giải quyết:* Lần theo đồ thị lineage từ raw $\rightarrow$ frame $\rightarrow$ face_crop $\rightarrow$ embedding và gán nhãn xóa toàn bộ chuỗi.
3. **Failure Mode 3: Duyệt cây ngây thơ xâm phạm dữ liệu người khác (Bẫy B6)**
   * *Hiện tượng:* Tệp frame `a0011` chụp chung cả `subj_00` và `subj_01`. Từ frame này cắt ra ảnh mặt `a0012` và vector `a0013` của riêng `subj_00`. Khi `subj_01` yêu cầu xóa, nếu duyệt BFS ngây thơ lấy hết con cháu của `a0011` thì sẽ xóa mất ảnh và vector của `subj_00`.
   * *PoC giải quyết:* Đặt nguyên tắc phạm vi: Một artefact chỉ được xử lý khi `subject_id` yêu cầu nằm trong trường `subject_ids` của chính nó. Do đó `a0012` và `a0013` bị loại khỏi phạm vi của DR-001, tránh hoàn toàn lỗi False-delete.

---

## 07 · Human & decision

- **Review Queue:** Được tạo tự động tại `out/poc/review_queue.csv` với dung lượng $B = 60$. Sắp xếp ưu tiên: ca `retain_legal_hold` (ưu tiên 3.0) $\rightarrow$ ca phái sinh từ hold (2.5) $\rightarrow$ ca nghi vấn đa chủ thể/thiếu quyền `escalate` (2.0) $\rightarrow$ thời hạn chót (`deadline`) gần nhất xếp trước.
- **Quy trình Human-in-the-loop (`apply_review`):**
  - Chuyên viên DPO (Nguyễn Hải Nam) xem xét các ca nghi vấn trong `review_queue.csv`.
  - Thực hiện ghi đè quyết định (ví dụ: chuyển ca ảnh 2 người sang `delete` sau khi đã hoàn tất làm mờ mặt đối tượng còn lại) và xuất ra `out/poc/review_queue_reviewed.csv`.
  - Hàm `apply_review()` tự động đọc các quyết định ghi đè, cập nhật vào bảng kết quả và ghi lại danh tính người duyệt cùng lý do vào `out/poc/audit_log.jsonl`.
- **Cơ chế Ra quyết định (`decide`):**
  - Trả về `GO` khi tất cả các dòng cần review đã được phê duyệt.
  - Trả về `HOLD` với mã lý do `PENDING_REVIEWS` nếu còn tồn đọng yêu cầu chưa duyệt, hoặc `DATA_WARNINGS` nếu phát hiện dữ liệu đồ thị có bất thường.

---

## 08 · Reproduce & tests

Quy trình tái lập 100% offline không cần kết nối mạng:

```powershell
# 1. Cài đặt môi trường
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt

# 2. Chạy pipeline PoC
python -m src.main --config configs/lab.yaml --track t08 --output out/poc --run-name poc --offline --seed 42

# 3. Chạy kiểm thử tự động
python -m pytest -q
```

- **Kết quả kiểm thử trên bộ Gold Mini (`tests/data/t08_mini/`):**
  - Chạy PoC trên đồ thị mini 16 artefact: Khớp chính xác **18/18 dòng** (100.0%) so với đáp án viết tay `expected_actions.csv` và `expected_actions_descendants.csv`.
  - Kiểm tra tính bất biến (Idempotency): Chạy 2 lần độc lập, mã hash SHA-256 của file `actions.csv` trùng khớp từng byte.
- **Môi trường thực nghiệm:**
  - OS: Windows 11 / Windows Server · Python: 3.12 · CPU: Intel/AMD 64-bit · Git Commit SHA: `m5/audit-review`.

---

## 09 · Limitations & ethics

- **Rủi ro và Giới hạn:**
  - *Giả định Q1 (Direct Hold):* Nếu cơ quan điều tra ban hành trát yêu cầu "đóng băng toàn diện chuỗi phái sinh" (descendants hold), thì việc xóa 26 tệp phái sinh của nhóm sẽ bị coi là vi phạm. Nhóm đã phòng ngừa rủi ro này bằng cách chuẩn bị sẵn tham số cấu hình `hold_scope: descendants` và đo lường sẵn kết quả đối chứng.
  - *Mô phỏng vs Dữ liệu thực:* Trong lab, các tệp dữ liệu là giả lập (mock data), lệnh xóa là mô phỏng ghi nhận trạng thái. Trong hệ thống sản xuất thực tế, việc xóa vector trong các cơ sở dữ liệu vector (Milvus/Pinecone/Chroma) đòi hỏi quá trình tái đánh chỉ mục (re-indexing) tốn kém tài nguyên tính toán.
- **Tuyên bố đạo đức:**
  - Nhóm không tự ý tuyên bố hệ thống "đạt chuẩn GDPR 100%" chỉ thông qua các quy tắc tự động. Mọi quyết định xử lý ngoại lệ trong sản phẩm thực tế đều cần có sự tham gia và phê chuẩn của Cán bộ Bảo vệ Dữ liệu (DPO) và bộ phận Pháp chế doanh nghiệp.

---

## 10 · Team contribution

**Bảng 2 · Bằng chứng đóng góp cá nhân (Khớp với `git shortlog -sne --all`)**

| Thành viên | Git Author & Email | Module / Vai trò phụ trách | Đóng góp & Commit chứng minh | Trình bày? |
|---|---|---|---|---|
| **Nguyễn Hữu Lộc** (M1 - Lead) | `nguyenloc2004`<br>`nguyenhuuloc.122004@gmail.com` | Lead / Integrator / CLI | Thiết lập khung `src/pipeline.py`, cài đặt `rank()` với khóa ghép `item_id`, `decide()`, merge Pull Requests. | Có |
| **Bùi Sỹ Tùng** (M2) | `Pynda`<br>`buisytungk25cntt@gmail.com` | Data & Lineage | Cài đặt `src/t08/loader.py` kiểm tra schema; `src/t08/lineage.py` duyệt BFS phả hệ, `scope_for`, phát hiện lỗi dữ liệu. | Có |
| **Trịnh Đức Hưng** (M3) | `TrinhDucHung`<br>`hungductrinh2004@gmail.com` | Policy / Core Logic | Cài đặt `src/t08/policy.py`, file cấu hình luật `configs/t08_policy.yaml` có trích dẫn nguồn luật; nghiên cứu ablation. | Có |
| **Dương Dũng** (M4) | `hurtmyneck` / `Dương Dũng`<br>`duongdung04bg@gmail.com` | QA / Metrics / Tests | Cài đặt `src/t08/baseline.py`, tạo bộ Gold Mini 16 artefact viết tay tại `tests/data/t08_mini/`, viết 10+ bài unit test. | Có |
| **Nguyễn Hải Nam** (M5) | `hainam08012004`<br>`Khongcomatkhau@2005` | Human Review / Audit / Report | Cài đặt `src/t08/audit.py` (`write_audit`, `apply_review`), chốt `metric_contract.md`, hoàn thiện `group_report.md`. | Có |

---

## 11 · References

| Tài liệu / Tiêu chuẩn | Ngày tham khảo | Nội dung & Giá trị áp dụng |
|---|---|---|
| [GDPR Regulation (EU) 2016/679](https://eur-lex.europa.eu/eli/reg/2016/679/oj) | 2026-11-14 | Điều 17 về Quyền được xóa dữ liệu và Điều 17(3) về các trường hợp ngoại lệ lưu giữ pháp lý. |
| [Nghị định 356/2025/NĐ-CP & Luật 91/2025/QH15](https://chinhphu.vn) | 2026-11-14 | Quy định pháp luật Việt Nam về quyền của chủ thể dữ liệu và trách nhiệm của bên kiểm soát dữ liệu. |
| [California Senate Bill 362 (DELETE Act)](https://leginfo.legislature.ca.gov) | 2026-11-14 | Mô hình nền tảng DROP tiếp nhận và điều phối yêu cầu xóa dữ liệu trên quy mô lớn. |
| [Google Data Cards Playbook](https://datacardsplaybook.withgoogle.com/) | 2026-11-14 | Phương pháp luận ghi chép nguồn gốc, tính minh bạch và vòng đời dữ liệu trong hệ thống AI. |

