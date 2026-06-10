"""
Kiểm tra freshness từ manifest pipeline.

Monitor tách 2 boundary:
- source_export: dữ liệu nguồn mới nhất trong snapshot có còn trong SLA không.
- pipeline_publish: pipeline vừa publish manifest/index gần đây không.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Tuple


BoundaryResult = Dict[str, Any]


def parse_iso(ts: str) -> datetime | None:
    if not ts:
        return None
    try:
        # Cho phép "2026-04-10T08:00:00" không có timezone
        if ts.endswith("Z"):
            return datetime.fromisoformat(ts.replace("Z", "+00:00"))
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def check_manifest_freshness(
    manifest_path: Path,
    *,
    sla_hours: float = 24.0,
    publish_sla_hours: float = 2.0,
    now: datetime | None = None,
) -> Tuple[str, Dict[str, Any]]:
    """
    Trả về ("PASS" | "WARN" | "FAIL", detail dict).

    Overall status ưu tiên source freshness vì agent trả lời theo dữ liệu nguồn.
    `pipeline_publish` giúp phân biệt "pipeline chưa chạy" với "source snapshot cũ".
    """
    now = now or datetime.now(timezone.utc)
    if not manifest_path.is_file():
        return "FAIL", {"reason": "manifest_missing", "path": str(manifest_path)}

    data: Dict[str, Any] = json.loads(manifest_path.read_text(encoding="utf-8"))

    source = _boundary_status(
        data.get("latest_exported_at"),
        now=now,
        sla_hours=sla_hours,
        timestamp_field="latest_exported_at",
        boundary="source_export",
        missing_reason="no_latest_exported_at_in_manifest",
    )
    publish = _boundary_status(
        data.get("run_timestamp"),
        now=now,
        sla_hours=publish_sla_hours,
        timestamp_field="run_timestamp",
        boundary="pipeline_publish",
        missing_reason="no_run_timestamp_in_manifest",
    )

    detail: Dict[str, Any] = {
        "run_id": data.get("run_id"),
        "source_export": source,
        "pipeline_publish": publish,
        # Backward-compatible summary fields used by older reports/log readers.
        "latest_exported_at": source.get("timestamp"),
        "age_hours": source.get("age_hours"),
        "sla_hours": sla_hours,
    }

    source_status = source["status"]
    publish_status = publish["status"]
    if source_status == "FAIL":
        return "FAIL", {**detail, "reason": source.get("reason", "source_freshness_sla_exceeded")}
    if source_status == "WARN":
        return "WARN", {**detail, "reason": source.get("reason", "source_timestamp_unavailable")}
    if publish_status in {"WARN", "FAIL"}:
        return "WARN", {**detail, "reason": publish.get("reason", "pipeline_publish_freshness_warning")}
    return "PASS", detail


def _boundary_status(
    ts_raw: Any,
    *,
    now: datetime,
    sla_hours: float,
    timestamp_field: str,
    boundary: str,
    missing_reason: str,
) -> BoundaryResult:
    if not ts_raw:
        return {
            "boundary": boundary,
            "timestamp_field": timestamp_field,
            "timestamp": "",
            "status": "WARN",
            "reason": missing_reason,
            "sla_hours": sla_hours,
        }

    dt = parse_iso(str(ts_raw))
    if dt is None:
        return {
            "boundary": boundary,
            "timestamp_field": timestamp_field,
            "timestamp": str(ts_raw),
            "status": "WARN",
            "reason": "timestamp_parse_failed",
            "sla_hours": sla_hours,
        }

    age_hours = (now - dt).total_seconds() / 3600.0
    status = "PASS" if age_hours <= sla_hours else "FAIL"
    detail: BoundaryResult = {
        "boundary": boundary,
        "timestamp_field": timestamp_field,
        "timestamp": str(ts_raw),
        "age_hours": round(age_hours, 3),
        "sla_hours": sla_hours,
        "status": status,
    }
    if status == "FAIL":
        detail["reason"] = "freshness_sla_exceeded"
    return detail
