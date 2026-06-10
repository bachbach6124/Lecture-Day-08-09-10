# Quality report — Lab Day 10

**run_id bad:** `sprint3-inject-bad`  
**run_id clean:** `sprint3-after-clean`  
**Ngày:** 2026-06-10

---

## 1. Tóm tắt số liệu

| Chỉ số | Trước / inject bad | Sau / clean | Ghi chú |
|--------|---------------------|-------------|---------|
| raw_records | 247 | 247 | Cùng input `data/raw/policy_export_dirty.csv` |
| cleaned_records | 35 | 35 | Cùng số dòng, khác nội dung refund stale do flag `--no-refund-fix` |
| quarantine_records | 212 | 212 | Rules quarantine không đổi giữa hai run |
| Expectation halt? | Có: `refund_no_stale_14d_window` FAIL `violations=1`, nhưng `--skip-validate` cho embed tiếp | Không: toàn bộ halt expectations OK | Evidence: `artifacts/logs/run_sprint3-inject-bad.log`, `artifacts/logs/run_sprint3-after-clean.log` |
| Embed | `embed_upsert count=35` | `embed_prune_removed=1`, `embed_upsert count=35` | Clean run prune vector stale khỏi index |

---

## 2. Before / after retrieval

File so sánh: `artifacts/eval/sprint3_before_after_compare.csv`

| Câu hỏi | Inject bad | Sau clean | Diễn giải |
|---------|------------|-----------|-----------|
| `q_refund_window` | `contains_expected=yes`, `hits_forbidden=yes`, `top1_doc_id=policy_refund_v4` | `contains_expected=yes`, `hits_forbidden=no`, `top1_doc_id=policy_refund_v4` | Inject bad vẫn trả đúng "7 ngày" nhưng context top-k còn lẫn "14 ngày", nên có rủi ro agent trả lời sai hoặc mâu thuẫn |
| `gq_d10_01` | `contains_expected=true`, `hits_forbidden=true` | `contains_expected=true`, `hits_forbidden=false` | Grading chính thức fail khi embed stale refund; pass sau pipeline clean |

Artifacts:

- Bad self-eval: `artifacts/eval/sprint3_after_inject_bad.csv`
- Clean self-eval: `artifacts/eval/sprint3_after_clean.csv`
- Bad grading snapshot: `artifacts/eval/sprint3_grading_inject_bad.jsonl`
- Final grading: `artifacts/eval/grading_run.jsonl`

---

## 3. Freshness & monitor

Cả hai manifest đều `freshness_check=FAIL` vì `latest_exported_at=2026-04-11T00:00:00` đã vượt SLA 24 giờ tại thời điểm chạy lab.

- Bad manifest: `artifacts/manifests/manifest_sprint3-inject-bad.json`
- Clean manifest: `artifacts/manifests/manifest_sprint3-after-clean.json`

Kết quả FAIL này không phải lỗi Sprint 3; đây là snapshot lab cũ có chủ đích. Freshness monitor hiện tách `source_export` và `pipeline_publish`: source có thể `FAIL` trong khi publish vẫn `PASS` nếu pipeline vừa chạy.

---

## 4. Corruption inject

Lệnh inject:

```bash
.venv/bin/python etl_pipeline.py run --run-id sprint3-inject-bad --no-refund-fix --skip-validate
```

Kiểu corruption: tắt rule sửa cửa sổ refund `14 ngày làm việc` thành `7 ngày làm việc`, sau đó bỏ qua halt validation để cố tình publish dữ liệu xấu vào Chroma.

Detection:

- Expectation `refund_no_stale_14d_window` FAIL `violations=1`.
- Self-eval `q_refund_window` có `hits_forbidden=yes`.
- Grading `gq_d10_01` có `hits_forbidden=true`.

Mitigation đã kiểm chứng:

```bash
.venv/bin/python etl_pipeline.py run --run-id sprint3-after-clean
.venv/bin/python eval_retrieval.py --out artifacts/eval/sprint3_after_clean.csv
.venv/bin/python grading_run.py --out artifacts/eval/grading_run.jsonl
```

Sau mitigation, `instructor_quick_check.py` pass đủ `gq_d10_01` đến `gq_d10_10`.

---

## 5. Hạn chế & việc chưa làm

- Chưa làm thêm LLM-judge; Sprint 3 hiện dùng retrieval + keyword/forbidden theo baseline.
- Không xử lý freshness `source_export=FAIL` thành `PASS` vì dữ liệu mẫu cố tình cũ; runbook đã ghi rõ khác biệt giữa source snapshot và pipeline publish.
- Chưa cập nhật group report theo yêu cầu hiện tại.
