"""Audit log, dry-run, review overrides. OWNER: M5.

Grader rule: an action counts as audited only if the audit entry has item_id == artefact_id.

STUB (M1 scaffold): one plain audit entry per action row; review overrides not applied yet.
TODO M5: richer entries (lineage_path, held_ancestor, deadline, "delete after hold expires"),
dry-run plan file, apply reviewer overrides (approve/reject/edit/escalate) with reviewer name.
"""
from __future__ import annotations

import json
from pathlib import Path
import pandas as pd


def write_audit(ctx, rows: pd.DataFrame) -> None:
    """Ghi nhật ký kiểm toán (audit log) cho từng hành động.
    
    Quy tắc bắt buộc: trường 'item_id' trong audit log phải bằng 'artefact_id'.
    """
    dry_run = bool(ctx.param("dry_run", True))
    
    for row in rows.itertuples(index=False):
        # 1. Xác định tên hành động bằng if-else rõ ràng
        if dry_run == True:
            action_name = "plan:" + str(row.action)
        else:
            action_name = str(row.action)
        
        # 2. Nếu file bị hoãn do lệnh pháp lý thì thêm ghi chú
        if row.action == "retain_legal_hold":
            note = "delete_after_hold_expires"
        else:
            note = ""
        
        # 3. Lấy các thông tin chi tiết
        reason_text = getattr(row, "reason", "")
        request_id = getattr(row, "request_id", "")
        rule_id = getattr(row, "rule_id", "")
        lineage_path = getattr(row, "lineage_path", "")
        held_ancestor = getattr(row, "held_ancestor", None)
        deadline = getattr(row, "deadline", "")
        
        # 4. Ghi một dòng vào audit_log.jsonl
        ctx.audit.log(
            actor="pipeline",
            action=action_name,
            item_id=row.artefact_id,       # Điểm bắt buộc: phải là artefact_id
            after=row.action,
            reason=reason_text,
            request_id=request_id,
            rule_id=rule_id,
            lineage_path=lineage_path,
            held_ancestor=held_ancestor,
            deadline=deadline,
            note=note,
            dry_run=dry_run,
        )

    # 5. Nếu không phải chạy thử (chạy thật), lưu danh sách id đã xóa vào tombstones.json
    if dry_run == False:
        deleted_rows = rows[rows["action"] == "delete"]
        deleted_ids = deleted_rows["artefact_id"].tolist()
        tombstone_file = ctx.out("tombstones.json")
        with open(tombstone_file, "w", encoding="utf-8") as f:
            json.dump(deleted_ids, f, indent=2)


def apply_review(ctx, scored: pd.DataFrame, reviewed: pd.DataFrame | None) -> pd.DataFrame:
    """Áp dụng các quyết định sửa đổi của chuyên viên review."""
    # Nếu chưa có người duyệt hoặc danh sách duyệt trống thì giữ nguyên
    if reviewed is None:
        return scored
    if len(reviewed) == 0:
        return scored

    # Tạo một bản sao mới để chỉnh sửa
    final_df = scored.copy()
    final_df = final_df.set_index("item_id", drop=False)

    for rev in reviewed.itertuples(index=False):
        item_id = str(rev.item_id)
        
        # Nếu item_id không có trong bảng kết quả thì bỏ qua
        if item_id not in final_df.index:
            continue

        reviewer_name = str(getattr(rev, "reviewer", "reviewer"))
        decision = str(getattr(rev, "reviewer_decision", "")).strip().lower()
        new_action = str(getattr(rev, "override_value", "")).strip().lower()
        note = str(getattr(rev, "review_note", ""))

        # Lấy artefact_id từ item_id (Ví dụ: "DR-001|a0043" -> "a0043")
        if "|" in item_id:
            parts = item_id.split("|")
            artefact_id = parts[1]
        else:
            artefact_id = item_id

        old_action = final_df.loc[item_id, "action"]

        # Trường hợp 1: Người duyệt sửa hành động (edit hoặc reject) và có hành động mới
        if decision == "edit" or decision == "reject":
            if new_action != "":
                # Cập nhật hành động mới vào DataFrame
                final_df.loc[item_id, "action"] = new_action
                
                # Ghi nhật ký kiểm toán là ai đã sửa
                ctx.audit.log(
                    actor=reviewer_name,
                    action="override:" + decision,
                    item_id=artefact_id,
                    before=old_action,
                    after=new_action,
                    reason=note,
                )

        # Trường hợp 2: Người duyệt bấm đồng ý (approve)
        if decision == "approve":
            ctx.audit.log(
                actor=reviewer_name,
                action="review:approve",
                item_id=artefact_id,
                after=old_action,
                reason=note,
            )

    return final_df.reset_index(drop=True)

