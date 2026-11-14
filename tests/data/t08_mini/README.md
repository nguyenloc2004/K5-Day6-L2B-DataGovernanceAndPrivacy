# Graph mini T08

Bộ gold nhỏ để chứng minh pipeline đúng khi **không có `gt/`** của giảng viên (xem docs/PLAN_T08.md mục 5).
16 artefact, 3 yêu cầu, 18 dòng đáp án. ID (`m01`..) và subject (`mini_*`) cố ý khác fixture thật:
pipeline mà hard-code ID của fixture sẽ trượt bộ này.

Không đặt trong `fixtures/*/gt/` (GT guard sẽ chặn pipeline). Chạy thử bằng:

```powershell
.venv\Scripts\python -m src.main --config configs/lab.yaml --track t08 --input tests/data/t08_mini --output out/mini --run-name mini --offline --seed 42
```

## Cây

```
m01 raw_video [alice] HOLD LH-MINI-1 ─┬─ m02 frame [alice] ── m03 face_crop [alice] ── m04 embedding [alice] (origin_known=false)
                                      ├─ m05 backup [alice] (acl=vendor-x)
                                      └─ m06 frame [alice, bob] ── m07 face_crop [bob] ── m08 embedding [bob]
m09 raw_video [bob] ── m10 frame [bob]
m11 raw_video [cara] ── m12 frame [cara] ── m13 face_crop [cara] HOLD LH-MINI-2
m14 training_export [alice, bob, cara]   cha: m03, m10, m12
m15 embedding [bob]                       cha: "zz_missing" (không tồn tại)
m16 raw_video [dave]                      không ai yêu cầu xóa
```

Yêu cầu: MR-1 = alice, MR-2 = bob, MR-3 = cara (`identity_verified: false`). Dave không có yêu cầu.

## Mỗi artefact kiểm tra điều gì

| Artefact | Bẫy / luật | Đáp án |
|---|---|---|
| m01 | B1 legal hold | MR-1: `retain_legal_hold` |
| m02, m03 | B2 con của artefact bị hold, bản thân `legal_hold = null` | MR-1: `delete` (Q1 = direct), reason `DERIVED_FROM_HELD` để lên đầu hàng duyệt |
| m04 | B3 không rõ nguồn | MR-1: `escalate` UNKNOWN_ORIGIN |
| m05 | B4 `acl` không có `data-platform` | MR-1: `escalate` NO_DELETE_PERMISSION |
| m06 | B5 nhiều chủ thể | MR-1 và MR-2: `escalate` MULTI_SUBJECT |
| m07, m08 | **B6**: con của m06 nhưng chỉ thuộc bob. m06 lại là con của m01 đang bị hold | MR-1: **không có dòng** (ngoài phạm vi). MR-2: `delete`, reason `DERIVED_FROM_HELD` |
| m09, m10 | Trường hợp xóa bình thường | MR-2: `delete` |
| m11, m12 | Danh tính chưa xác minh (R2) | MR-3: `escalate` IDENTITY_UNVERIFIED |
| m13 | R1 đứng trước R2: có hold thì giữ dù danh tính chưa xác minh | MR-3: `retain_legal_hold` |
| m14 | Export nhiều người. MR-3 chứng minh R2 đứng trước R5 | MR-1, MR-2: MULTI_SUBJECT. MR-3: IDENTITY_UNVERIFIED |
| m15 | `parent_ids` trỏ tới artefact không tồn tại: vẫn `delete` theo phạm vi, nhưng phải có cảnh báo dữ liệu (`decide()` trả HOLD / DATA_WARNINGS) | MR-2: `delete` |
| m16 | Không thuộc yêu cầu nào | Không có dòng nào |

## File

| File | Dùng cho |
|---|---|
| `data_graph.json`, `requests.json`, `manifest.csv` | Đầu vào (manifest có sha256 vì `strict_provenance: true`) |
| `expected_actions.csv` | Đáp án với `hold_scope: direct` (cấu hình đã chốt). Cột `expected_reason` là `reason_code` kỳ vọng. Theo PLAN_T08 §3, bản phái sinh của artefact bị hold vẫn `delete` nhưng mang reason `DERIVED_FROM_HELD` |
| `expected_actions_descendants.csv` | Đáp án với `hold_scope: descendants`, dùng cho ablation của M3. Khác bản trên ở đúng 4 dòng: MR-1 m02, m03 và MR-2 m07, m08 đổi action từ `delete` thành `retain_legal_hold` (reason giữ nguyên `DERIVED_FROM_HELD`) |

Cột `request_id, artefact_id, expected_action` cùng định dạng với `gt_actions.csv` của giảng viên nên có thể đưa vào
`src.metrics.tracks.eval_t08`. Đáp án được viết tay từ bảng luật PLAN_T08 §4.3 rồi đối chiếu độc lập bằng một oracle tạm
(không commit), khớp 18/18 dòng ở cả hai chế độ.

**Lưu ý line ending:** `manifest.csv` kiểm sha256 nên file ở đây không được đổi sang CRLF. Cần dòng
`tests/data/t08_mini/** -text` trong `.gitattributes` (file của M1).
