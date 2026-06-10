# Data contract — Lab Day 10

> Bắt đầu từ `contracts/data_contract.yaml` — mở rộng và đồng bộ file này.

---

## 1. Nguồn dữ liệu (source map)

| Nguồn | Phương thức ingest | Failure mode chính | Metric / alert |
|-------|-------------------|-------------------|----------------|
| `policy_refund_v4` | Snapshot CSV từ export policy + canonical `data/docs/policy_refund_v4.txt` | Chunk stale còn cửa sổ hoàn tiền 14 ngày, duplicate nội dung, thiếu `effective_date` | `refund_no_stale_14d_window`, `quarantine_records` theo reason, eval `hits_forbidden=false` |
| `hr_leave_policy` | Snapshot CSV từ HR policy + canonical `data/docs/hr_leave_policy.txt` | Version conflict HR 2025/2026: nội dung 10 ngày phép năm hoặc ngày hiệu lực trước 2026 | `hr_leave_no_stale_10d_annual`, quarantine reason `stale_hr_policy_*`, grading `gq_d10_09` |
| `access_control_sop` | Snapshot CSV từ IT Security SOP + canonical `data/docs/access_control_sop.txt` | Source hợp lệ bị thiếu khỏi allowlist, duplicate chunk Level 4, chunk text rỗng | `expect_top1_doc_id=access_control_sop`, duplicate/quarantine count, grading `gq_d10_10` |
| `sla_p1_2026` | Snapshot CSV từ SLA document + canonical `data/docs/sla_p1_2026.txt` | Missing date, duplicate SLA chunk, format ngày không đồng nhất | `effective_date_iso_yyyy_mm_dd`, retrieval câu SLA P1 |
| `it_helpdesk_faq` | Snapshot CSV từ FAQ + canonical `data/docs/it_helpdesk_faq.txt` | Missing text, duplicate FAQ, ngày `DD/MM/YYYY` cần normalize | `chunk_min_length_8`, retrieval câu lockout/VPN |

---

## 2. Schema cleaned

| Cột | Kiểu | Bắt buộc | Ghi chú |
|-----|------|----------|---------|
| chunk_id | string | Có | ID ổn định sau clean: `doc_id + seq + hash` |
| doc_id | string | Có | Phải thuộc allowlist trong `contracts/data_contract.yaml` và `transform/cleaning_rules.py` |
| chunk_text | string | Có | Tối thiểu 8 ký tự; không giữ nội dung stale/forbidden |
| effective_date | date | Có | Chuẩn ISO `YYYY-MM-DD`; raw `DD/MM/YYYY` được normalize |
| exported_at | datetime | Có | Dùng cho manifest/freshness; giữ nguyên từ raw export |

---

## 3. Freshness contract

| Boundary | Trường manifest | SLA | Ý nghĩa |
|----------|-----------------|-----|---------|
| `source_export` | `latest_exported_at` | 24 giờ | Dữ liệu nguồn mới nhất trong snapshot có còn đủ tươi cho agent không |
| `pipeline_publish` | `run_timestamp` | 2 giờ | Pipeline/index có vừa được publish gần thời điểm kiểm tra không |

Quy tắc diễn giải:

- Overall `PASS`: cả source snapshot và publish đều trong SLA.
- Overall `FAIL`: `source_export` quá SLA; agent đang đọc snapshot nguồn cũ dù pipeline có thể vừa chạy.
- Overall `WARN`: thiếu/không parse được timestamp, hoặc source còn tươi nhưng publish đã cũ.

Với dữ liệu lab hiện tại, `source_export` dự kiến `FAIL` vì `latest_exported_at=2026-04-11T00:00:00`. Đây là evidence để viết runbook, không phải lý do dùng `--skip-validate`.

---

## 4. Quy tắc quarantine vs drop

Record không đạt rule được ghi vào `artifacts/quarantine/quarantine_<run_id>.csv` kèm `reason`. Nhóm chỉ merge lại khi xác định được source canonical, sửa mapping/rule, và rerun pipeline với cùng câu hỏi eval. Các lỗi hiện tại:

- `unknown_doc_id`: source chưa thuộc allowlist hoặc export lạ.
- `missing_effective_date` / `invalid_effective_date_format`: không đủ metadata version để publish.
- `stale_hr_policy_effective_date` / `stale_hr_policy_10d_annual_leave`: bản HR cũ hoặc nội dung cũ bị gắn ngày mới.
- `ambiguous_chunk_text` / `noisy_chunk_text`: nội dung có marker parser/OCR không đủ tin cậy để publish.
- `non_p1_sla_scope`: chunk ngoài phạm vi P1 trong dataset `sla_p1_2026`.
- `duplicate_chunk_text`: giữ bản đầu để tránh phình vector store.
- `missing_chunk_text`: không có nội dung để embed.

---

## 5. Phiên bản & canonical

Source of truth:

- Refund: `data/docs/policy_refund_v4.txt`, effective date `2026-02-01`, cửa sổ đúng là 7 ngày làm việc.
- HR leave: `data/docs/hr_leave_policy.txt`, effective date `2026-01-01`, nhân viên dưới 3 năm kinh nghiệm là 12 ngày phép năm.
- Access control: `data/docs/access_control_sop.txt`, effective date `2026-01-01`, Level 4 Admin Access cần IT Manager + CISO.

Allowlist hiện đồng bộ với grading: `policy_refund_v4`, `sla_p1_2026`, `it_helpdesk_faq`, `hr_leave_policy`, `access_control_sop`.
