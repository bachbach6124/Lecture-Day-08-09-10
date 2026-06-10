import json
from datetime import datetime, timezone
from pathlib import Path

from monitoring.freshness_check import check_manifest_freshness, parse_iso


def write_manifest(path: Path, **fields) -> Path:
    path.write_text(json.dumps(fields), encoding="utf-8")
    return path


def test_parse_iso_accepts_z_and_naive_timestamp():
    assert parse_iso("2026-04-11T00:00:00Z").tzinfo is not None
    assert parse_iso("2026-04-11T00:00:00").tzinfo is not None
    assert parse_iso("not-a-date") is None


def test_freshness_passes_when_source_and_publish_are_in_sla(tmp_path):
    manifest = write_manifest(
        tmp_path / "manifest.json",
        run_id="fresh",
        latest_exported_at="2026-06-10T02:00:00+00:00",
        run_timestamp="2026-06-10T03:30:00+00:00",
    )

    status, detail = check_manifest_freshness(
        manifest,
        sla_hours=24,
        publish_sla_hours=2,
        now=datetime(2026, 6, 10, 4, 0, tzinfo=timezone.utc),
    )

    assert status == "PASS"
    assert detail["source_export"]["status"] == "PASS"
    assert detail["pipeline_publish"]["status"] == "PASS"


def test_source_stale_fails_even_if_pipeline_just_published(tmp_path):
    manifest = write_manifest(
        tmp_path / "manifest.json",
        run_id="stale-source",
        latest_exported_at="2026-04-11T00:00:00+00:00",
        run_timestamp="2026-06-10T03:45:00+00:00",
    )

    status, detail = check_manifest_freshness(
        manifest,
        sla_hours=24,
        publish_sla_hours=2,
        now=datetime(2026, 6, 10, 4, 0, tzinfo=timezone.utc),
    )

    assert status == "FAIL"
    assert detail["source_export"]["status"] == "FAIL"
    assert detail["pipeline_publish"]["status"] == "PASS"
    assert detail["reason"] == "freshness_sla_exceeded"


def test_missing_source_timestamp_warns(tmp_path):
    manifest = write_manifest(
        tmp_path / "manifest.json",
        run_id="missing-source",
        run_timestamp="2026-06-10T03:45:00+00:00",
    )

    status, detail = check_manifest_freshness(
        manifest,
        now=datetime(2026, 6, 10, 4, 0, tzinfo=timezone.utc),
    )

    assert status == "WARN"
    assert detail["source_export"]["reason"] == "no_latest_exported_at_in_manifest"
