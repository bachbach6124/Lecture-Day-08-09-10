# Báo Cáo Cá Nhân — Lab Day 10: Data Pipeline & Observability

**Họ và tên:** Đào Xuân Bách - 2A202600640 
**Vai trò:** Full pipeline owner — Ingestion, Cleaning, Quality, Embed, Monitoring  
**Ngày nộp:** 2026-06-10

---

## 1. Tôi phụ trách phần nào?

Tôi phụ trách toàn bộ pipeline Day 10 từ phân tích raw data đến clean, validate, embed, eval và tài liệu vận hành. Tôi bắt đầu với `data/raw/policy_export_dirty.csv`, đếm được `raw_records=247`, sau đó đối chiếu với `data/grading_questions.json` để xác định các source grading cần: `policy_refund_v4`, `sla_p1_2026`, `it_helpdesk_faq`, `hr_leave_policy`, và `access_control_sop`. Tôi sửa `transform/cleaning_rules.py`, `quality/expectations.py`, `contracts/data_contract.yaml`, `docs/data_contract.md`, `docs/pipeline_architecture.md`, `docs/runbook.md`, và tạo `docs/quality_report.md`. Tôi cũng chạy `.venv/bin/python etl_pipeline.py run --run-id sprint4-final`, tạo manifest, eval và grading artifact.

**File / module:**

- `transform/cleaning_rules.py`
- `quality/expectations.py`
- `contracts/data_contract.yaml`
- `docs/*.md`
- `artifacts/eval/grading_run.jsonl`

**Bằng chứng:** Final run `sprint4-final` ghi `raw_records=247`, `cleaned_records=35`, `quarantine_records=212`, `embed_upsert count=35`, và `PIPELINE_OK`.

---

## 2. Một quyết định kỹ thuật

Quyết định kỹ thuật quan trọng nhất của tôi là dùng expectation `halt` cho các lỗi có thể làm agent trả sai chính sách, thay vì chỉ cảnh báo. Các lỗi như refund stale `14 ngày`, HR stale `10 ngày phép năm`, thiếu source grading, chunk ambiguous/noisy và `exported_at` không ISO đều phải chặn publish. Lý do là vector store có thể giữ context sai rất lâu nếu đã embed nhầm. Tôi vẫn dùng `--skip-validate` trong Sprint 3, nhưng chỉ để mô phỏng incident có chủ đích. Sau đó tôi chạy lại pipeline sạch để prune vector stale và publish snapshot đúng. Cách này chứng minh expectation không chỉ là checklist mà thật sự bảo vệ chất lượng retrieval.

---

## 3. Một lỗi hoặc anomaly đã xử lý

Anomaly lớn nhất là pipeline baseline bỏ sót source hợp lệ `access_control_sop`. Raw CSV có 8 dòng source này và grading câu `gq_d10_10` yêu cầu `expect_top1_doc_id=access_control_sop`, nhưng allowlist ban đầu không có nên bị quarantine nhầm. Tôi thêm source này vào `ALLOWED_DOC_IDS` và data contract. Một anomaly khác là HR stale: nhiều chunk ghi `10 ngày phép năm (bản HR 2025)` nhưng lại có `effective_date` sau 2026, nên chỉ kiểm ngày là chưa đủ. Tôi thêm rule quarantine theo nội dung stale, tạo reason `stale_hr_policy_10d_annual_leave`. Sau fix, grading `gq_d10_09` và `gq_d10_10` đều pass.

---

## 4. Bằng chứng trước / sau

Baseline Sprint 1:

```text
run_id=sprint1-baseline
cleaned_records=40
quarantine_records=207
expectation[hr_leave_no_stale_10d_annual] FAIL (halt) :: violations=2
```

Sprint 3 inject:

```text
expectation[refund_no_stale_14d_window] FAIL (halt) :: violations=1
q_refund_window: bad_hits_forbidden=yes
```

Final Sprint 4:

```text
run_id=sprint4-final
cleaned_records=35
quarantine_records=212
PIPELINE_OK
```

`instructor_quick_check.py --grading artifacts/eval/grading_run.jsonl` pass đủ `gq_d10_01` đến `gq_d10_10`; `sprint4_final_eval.csv` có `bad_count=0`. Freshness vẫn `FAIL` vì snapshot mẫu có `latest_exported_at=2026-04-11T00:00:00`, cũ hơn SLA 24h, và tôi đã giải thích trong runbook.

---

## 5. Cải tiến tiếp theo

Nếu có thêm 2 giờ, tôi sẽ chuyển các rule versioning như HR cutoff và forbidden phrase sang đọc động từ `contracts/data_contract.yaml`, đồng thời thêm test tự động assert số vector trong Chroma bằng số dòng cleaned sau mỗi rerun.
