# Runbook — Lab Day 10 (incident tối giản)

---

## Symptom

User hoặc agent thấy một trong các triệu chứng sau:

- Câu trả lời refund nói hoặc trích context có `14 ngày` trong khi chính sách hiện hành là `7 ngày`.
- Câu HR trả về `10 ngày phép năm` cho nhân viên dưới 3 năm kinh nghiệm thay vì `12 ngày`.
- Câu access control không tìm được Level 4 Admin Access hoặc không trả về IT Manager/CISO.
- Freshness monitor báo `FAIL` dù pipeline vừa chạy xong.

---

## Detection

- Log pipeline: `expectation[refund_no_stale_14d_window] FAIL`, `expectation[hr_leave_no_stale_10d_annual] FAIL`, hoặc thiếu `required_grading_doc_ids_present`.
- Eval/grading: `hits_forbidden=true`, `contains_expected=false`, hoặc `top1_doc_matches=false`.
- Freshness: `python etl_pipeline.py freshness --manifest artifacts/manifests/manifest_<run_id>.json`.
- Manifest/log sanity: `raw_records`, `cleaned_records`, `quarantine_records`, `run_id`.

Ý nghĩa freshness theo 2 boundary:

- `source_export`: đo `latest_exported_at`, mặc định SLA 24 giờ. Boundary này trả lời câu hỏi "dữ liệu nguồn trong index có mới không?"
- `pipeline_publish`: đo `run_timestamp`, mặc định SLA 2 giờ. Boundary này trả lời câu hỏi "pipeline/index có vừa publish không?"
- Overall `PASS`: cả source snapshot và pipeline publish đều trong SLA.
- Overall `WARN`: thiếu/không parse được timestamp, hoặc chỉ pipeline publish quá SLA.
- Overall `FAIL`: `source_export` quá SLA. Với snapshot lab hiện tại, `FAIL` là kỳ vọng vì export mới nhất là `2026-04-11T00:00:00`, cũ hơn SLA 24h tại ngày chạy 2026-06-10.

Ví dụ diễn giải đúng: nếu `source_export=FAIL` nhưng `pipeline_publish=PASS`, pipeline vừa chạy thành công nhưng chỉ publish lại snapshot nguồn đã cũ. Việc cần làm là yêu cầu source owner xuất snapshot mới, không phải sửa prompt/model.

---

## Diagnosis

| Bước | Việc làm | Kết quả mong đợi |
|------|----------|------------------|
| 1 | Kiểm tra `artifacts/manifests/*.json` | Xác định `run_id`, `cleaned_csv`, `latest_exported_at`, `run_timestamp`, collection Chroma |
| 2 | Mở `artifacts/logs/run_<run_id>.log` | Thấy expectation nào fail/warn và số `raw/cleaned/quarantine` |
| 3 | Mở `artifacts/quarantine/quarantine_<run_id>.csv` | Xác định reason tăng bất thường: `unknown_doc_id`, `stale_*`, `ambiguous_*` |
| 4 | Chạy `.venv/bin/python eval_retrieval.py --out artifacts/eval/debug_eval.csv` | Xác định câu nào `hits_forbidden` hoặc top-1 sai |
| 5 | Chạy `.venv/bin/python grading_run.py --out artifacts/eval/grading_run.jsonl` | Kiểm đủ 10 câu grading trước khi nộp |
| 6 | Chạy `.venv/bin/python -m pytest -q` | Unit tests cho cleaning/expectation/freshness pass |

---

## Mitigation

1. Nếu expectation halt fail: không dùng `--skip-validate` trong run nộp bài. Sửa rule/source rồi chạy lại:

```bash
.venv/bin/python etl_pipeline.py run --run-id sprint4-final
```

2. Nếu đã inject bad vào Chroma: chạy lại pipeline chuẩn để prune id stale và upsert snapshot sạch.
3. Nếu freshness `FAIL` do `source_export` cũ nhưng `pipeline_publish` mới: ghi rõ trong report/runbook, không đổi dữ liệu giả để che lỗi. Nếu đây là production, tạm banner “data stale” và yêu cầu source owner xuất lại snapshot.
4. Nếu freshness `WARN` do `pipeline_publish` cũ nhưng source còn tươi: chạy lại pipeline/publish index, rồi kiểm manifest mới.
5. Nếu top-k còn context cấm: kiểm tra cleaned CSV và quarantine reason, sau đó chạy lại `grading_run.py`.

---

## Prevention

- Giữ expectation halt cho stale refund, HR version conflict, thiếu source grading và timestamp không ISO.
- Đồng bộ allowlist giữa `contracts/data_contract.yaml` và `transform/cleaning_rules.py`.
- Duy trì artifact bắt buộc cho mỗi run: log, manifest, cleaned, quarantine, eval.
- Với production, giữ monitor 2 boundary: `source_export` để bảo vệ chất lượng câu trả lời, `pipeline_publish` để phát hiện job/index chưa chạy.
- Thêm owner/source map cho từng doc_id để tránh `access_control_sop` bị quarantine nhầm như baseline.
