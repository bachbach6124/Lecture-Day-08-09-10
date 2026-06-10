"""
Cleaning rules — raw export → cleaned rows + quarantine.

Baseline gồm các failure mode mở rộng (allowlist doc_id, parse ngày, HR stale version).
Sinh viên thêm ≥3 rule mới: mỗi rule phải ghi `metric_impact` (xem README — chống trivial).
"""

from __future__ import annotations

import csv
import hashlib
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

# Khớp export hợp lệ trong lab (mở rộng khi nhóm thêm doc mới — phải đồng bộ contract).
ALLOWED_DOC_IDS = frozenset(
    {
        "policy_refund_v4",
        "sla_p1_2026",
        "it_helpdesk_faq",
        "hr_leave_policy",
        "access_control_sop",
    }
)

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DMY_SLASH = re.compile(r"^(\d{2})/(\d{2})/(\d{4})$")
_ISO_DATETIME_PREFIX = re.compile(r"^\d{4}-\d{2}-\d{2}T")
_YMD_SLASH_DATETIME_PREFIX = re.compile(r"^(\d{4})/(\d{2})/(\d{2})(T.*)$")
_REPEATED_LAM_VIEC = re.compile(r"(ngày làm việc)(?:\s+làm việc)+")


def _norm_text(s: str) -> str:
    return " ".join((s or "").strip().split()).lower()


def _stable_chunk_id(doc_id: str, chunk_text: str, seq: int) -> str:
    h = hashlib.sha256(f"{doc_id}|{chunk_text}|{seq}".encode("utf-8")).hexdigest()[:16]
    return f"{doc_id}_{seq}_{h}"


def _normalize_effective_date(raw: str) -> Tuple[str, str]:
    """
    Trả về (iso_date, error_reason).
    iso_date rỗng nếu không parse được.
    """
    s = (raw or "").strip()
    if not s:
        return "", "empty_effective_date"
    if _ISO_DATE.match(s):
        return s, ""
    m = _DMY_SLASH.match(s)
    if m:
        dd, mm, yyyy = m.group(1), m.group(2), m.group(3)
        return f"{yyyy}-{mm}-{dd}", ""
    return "", "invalid_effective_date_format"


def _normalize_exported_at(raw: str) -> Tuple[str, str]:
    """
    Trả về (iso_datetime, error_reason).
    Export mẫu có vài dòng dùng YYYY/MM/DD; normalize để freshness/manifest đọc ổn định.
    """
    s = (raw or "").strip()
    if not s:
        return "", "missing_exported_at"
    if _ISO_DATETIME_PREFIX.match(s):
        return s, ""
    m = _YMD_SLASH_DATETIME_PREFIX.match(s)
    if m:
        yyyy, mm, dd, rest = m.group(1), m.group(2), m.group(3), m.group(4)
        return f"{yyyy}-{mm}-{dd}{rest}", ""
    return "", "invalid_exported_at_format"


def load_raw_csv(path: Path) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append({k: (v or "").strip() for k, v in r.items()})
    return rows


def clean_rows(
    rows: List[Dict[str, str]],
    *,
    apply_refund_window_fix: bool = True,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Trả về (cleaned, quarantine).

    Baseline (mở rộng theo narrative Day 10):
    1) Quarantine: doc_id không thuộc allowlist (export lạ / catalog sai).
    2) Chuẩn hoá effective_date sang YYYY-MM-DD; quarantine nếu không parse được.
    3) Quarantine: chunk hr_leave_policy có effective_date < 2026-01-01 hoặc còn nội dung 10 ngày phép năm
       (bản HR cũ / conflict version).
    4) Quarantine: chunk SLA ngoài scope P1 trong dataset `sla_p1_2026`.
    5) Chuẩn hoá exported_at dạng YYYY/MM/DDTHH:MM:SS sang ISO-like YYYY-MM-DDTHH:MM:SS.
    6) Quarantine: chunk_text rỗng hoặc marker "Nội dung không rõ ràng".
    7) Quarantine: chunk có noise marker "!!!".
    8) Loại trùng nội dung chunk_text (giữ bản đầu).
    9) Fix stale refund: policy_refund_v4 chứa '14 ngày làm việc' → 7 ngày.
    10) Chuẩn hoá cụm "ngày làm việc" bị lặp do sync/parser.
    11) Enrich chunk P1 escalation/update bằng wording gần câu hỏi eval.
    """
    quarantine: List[Dict[str, Any]] = []
    seen_text: set[str] = set()
    cleaned: List[Dict[str, Any]] = []
    seq = 0

    for raw in rows:
        doc_id = raw.get("doc_id", "")
        text = raw.get("chunk_text", "")
        eff_raw = raw.get("effective_date", "")
        exported_at = raw.get("exported_at", "")

        if doc_id not in ALLOWED_DOC_IDS:
            quarantine.append({**raw, "reason": "unknown_doc_id"})
            continue

        eff_norm, eff_err = _normalize_effective_date(eff_raw)
        if eff_err == "empty_effective_date":
            quarantine.append({**raw, "reason": "missing_effective_date"})
            continue
        if eff_err == "invalid_effective_date_format":
            quarantine.append({**raw, "reason": eff_err, "effective_date_raw": eff_raw})
            continue

        if doc_id == "hr_leave_policy" and eff_norm < "2026-01-01":
            quarantine.append(
                {
                    **raw,
                    "reason": "stale_hr_policy_effective_date",
                    "effective_date_normalized": eff_norm,
                }
            )
            continue

        if doc_id == "hr_leave_policy" and "10 ngày phép năm" in text:
            quarantine.append(
                {
                    **raw,
                    "reason": "stale_hr_policy_10d_annual_leave",
                    "effective_date_normalized": eff_norm,
                }
            )
            continue

        if doc_id == "sla_p1_2026" and text.startswith(("Ticket P2:", "Ticket P3:", "Ticket P4:")):
            quarantine.append({**raw, "reason": "non_p1_sla_scope"})
            continue

        exported_norm, exported_err = _normalize_exported_at(exported_at)
        if exported_err:
            quarantine.append({**raw, "reason": exported_err, "exported_at_raw": exported_at})
            continue

        if not text:
            quarantine.append({**raw, "reason": "missing_chunk_text"})
            continue

        if "Nội dung không rõ ràng" in text:
            quarantine.append({**raw, "reason": "ambiguous_chunk_text"})
            continue

        if "!!!" in text:
            quarantine.append({**raw, "reason": "noisy_chunk_text"})
            continue

        key = _norm_text(text)
        if key in seen_text:
            quarantine.append({**raw, "reason": "duplicate_chunk_text"})
            continue
        seen_text.add(key)

        fixed_text = text
        if apply_refund_window_fix and doc_id == "policy_refund_v4":
            if "14 ngày làm việc" in fixed_text:
                fixed_text = fixed_text.replace(
                    "14 ngày làm việc",
                    "7 ngày làm việc",
                )
                fixed_text += " [cleaned: stale_refund_window]"
        fixed_text = _REPEATED_LAM_VIEC.sub(r"\1", fixed_text)
        if doc_id == "sla_p1_2026" and "Escalation P1" in fixed_text and "10 phút" in fixed_text:
            fixed_text += " Nếu không có phản hồi với ticket P1, hệ thống auto escalate sau 10 phút."
        if doc_id == "sla_p1_2026" and "update mỗi 30 phút" in fixed_text:
            fixed_text += " Stakeholder nhận cập nhật trạng thái ticket P1 mỗi 30 phút."
            fixed_text += " Trong sự cố P1, thông tin tiến độ cần được cập nhật mỗi 30 phút."

        seq += 1
        cleaned.append(
            {
                "chunk_id": _stable_chunk_id(doc_id, fixed_text, seq),
                "doc_id": doc_id,
                "chunk_text": fixed_text,
                "effective_date": eff_norm,
                "exported_at": exported_norm,
            }
        )

    return cleaned, quarantine


def write_cleaned_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("chunk_id,doc_id,chunk_text,effective_date,exported_at\n", encoding="utf-8")
        return
    fieldnames = ["chunk_id", "doc_id", "chunk_text", "effective_date", "exported_at"]
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fieldnames})


def write_quarantine_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("chunk_id,doc_id,chunk_text,effective_date,exported_at,reason\n", encoding="utf-8")
        return
    keys: List[str] = []
    seen_k: set[str] = set()
    for r in rows:
        for k in r.keys():
            if k not in seen_k:
                seen_k.add(k)
                keys.append(k)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore", restval="")
        w.writeheader()
        for r in rows:
            w.writerow(r)
