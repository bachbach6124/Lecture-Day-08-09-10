from quality.expectations import run_expectations
from transform.cleaning_rules import clean_rows


def row(
    doc_id="policy_refund_v4",
    chunk_text="Khách hàng được hoàn tiền trong 14 ngày làm việc.",
    effective_date="2026-02-01",
    exported_at="2026-04-11T00:00:00",
):
    return {
        "doc_id": doc_id,
        "chunk_text": chunk_text,
        "effective_date": effective_date,
        "exported_at": exported_at,
    }


def test_clean_rows_fixes_refund_window_and_normalizes_dates():
    cleaned, quarantine = clean_rows(
        [
            row(effective_date="01/02/2026", exported_at="2026/04/11T00:00:00"),
        ]
    )

    assert quarantine == []
    assert cleaned[0]["effective_date"] == "2026-02-01"
    assert cleaned[0]["exported_at"] == "2026-04-11T00:00:00"
    assert "7 ngày làm việc" in cleaned[0]["chunk_text"]
    assert "14 ngày làm việc" not in cleaned[0]["chunk_text"]


def test_clean_rows_quarantines_stale_hr_and_unknown_doc_id():
    cleaned, quarantine = clean_rows(
        [
            row(
                doc_id="hr_leave_policy",
                chunk_text="Nhân viên dưới 3 năm có 10 ngày phép năm.",
                effective_date="2026-01-01",
            ),
            row(doc_id="unknown_policy", chunk_text="Unknown source."),
        ]
    )

    assert cleaned == []
    assert {r["reason"] for r in quarantine} == {
        "stale_hr_policy_10d_annual_leave",
        "unknown_doc_id",
    }


def test_expectations_halt_on_unfixed_refund_window():
    cleaned, quarantine = clean_rows(
        [row()],
        apply_refund_window_fix=False,
    )

    assert quarantine == []
    results, halt = run_expectations(cleaned)
    by_name = {r.name: r for r in results}

    assert halt is True
    assert by_name["refund_no_stale_14d_window"].passed is False
    assert by_name["refund_no_stale_14d_window"].severity == "halt"
