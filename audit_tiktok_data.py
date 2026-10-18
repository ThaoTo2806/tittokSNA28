# -*- coding: utf-8 -*-
"""Kiểm tra chất lượng dữ liệu TikTok sau giai đoạn 1.

Chạy tại project:
    py audit_tiktok_data.py

Mặc định đọc:
    data/raw/*.csv
    data/processed/cleaned_data.csv
    data/processed/duplicate_records.csv
    data/processed/data_quality_report.csv
    data/processed/hashtag_stats.csv

Báo cáo được lưu vào data/processed/audit/.
Script chỉ đọc dữ liệu nguồn, không sửa/xóa file raw hoặc processed.
"""
from pathlib import Path
import csv
import hashlib
import re
import json
from collections import Counter
import pandas as pd

PROJECT_DIR = Path(r"D:\HOCTAP\abc\tittokSNA28")
RAW_DIR = PROJECT_DIR / "data" / "raw"
PROCESSED_DIR = PROJECT_DIR / "data" / "processed"
AUDIT_DIR = PROCESSED_DIR / "audit"
EXPECTED_FILE_COUNT = None

HASHTAG_COL_RE = re.compile(r"^hashtags/(\d+)/name$")
CAPTION_TAG_RE = re.compile(r"#([^\s#]+)")
TRIM_PUNCT = ".,!?;:'\"()[]{}<>，。！？；：、…"


def read_csv_safely(path):
    last_error = None
    for enc in ("utf-8-sig", "utf-8", "cp1258", "latin1"):
        try:
            return pd.read_csv(path, encoding=enc, low_memory=False, on_bad_lines="warn")
        except UnicodeDecodeError as exc:
            last_error = exc
    if last_error:
        raise last_error
    return pd.read_csv(path, low_memory=False)


def sha256_file(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def normalize_tag(value):
    if pd.isna(value):
        return ""
    tag = str(value).strip().lower().lstrip("#").strip()
    tag = re.sub(r"\s+", "", tag).strip(TRIM_PUNCT)
    return tag


def extract_tags_from_row(row):
    tags = []
    hashtag_cols = []
    for col in row.index:
        match = HASHTAG_COL_RE.fullmatch(str(col))
        if match:
            hashtag_cols.append((int(match.group(1)), col))
    for _, col in sorted(hashtag_cols):
        tag = normalize_tag(row.get(col))
        if tag:
            tags.append(tag)
    caption = row.get("text", "")
    if pd.notna(caption):
        tags.extend(normalize_tag(x) for x in CAPTION_TAG_RE.findall(str(caption)))
    # Giữ thứ tự và loại trùng trong cùng video
    result, seen = [], set()
    for tag in tags:
        if tag and tag not in seen:
            result.append(tag)
            seen.add(tag)
    return result


def write_csv(rows, path):
    pd.DataFrame(rows).to_csv(path, index=False, encoding="utf-8-sig")


def main():
    if not RAW_DIR.exists():
        raise FileNotFoundError(f"Không tìm thấy thư mục raw: {RAW_DIR}. Hãy sửa PROJECT_DIR trong script.")
    if not PROCESSED_DIR.exists():
        raise FileNotFoundError(f"Không tìm thấy thư mục processed: {PROCESSED_DIR}. Hãy chạy clean_tiktok_data.py trước.")
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 72)
    print("KIỂM TRA CHẤT LƯỢNG DỮ LIỆU TIKTOK")
    print("=" * 72)

    # 1. Kiểm kê file raw, kích thước, số dòng, hash file và phát hiện file trùng byte.
    raw_files = sorted([p for p in RAW_DIR.iterdir() if p.is_file() and p.suffix.lower() == ".csv"])
    file_rows, hash_groups, read_errors = [], {}, []
    print(f"\n[1/4] Kiểm kê file raw: tìm thấy {len(raw_files)} CSV (dự kiến {EXPECTED_FILE_COUNT}).")
    for path in raw_files:
        try:
            df = read_csv_safely(path)
            digest = sha256_file(path)
            hash_groups.setdefault(digest, []).append(path.name)
            file_rows.append({
                "file": path.name,
                "rows_data": len(df),
                "columns": len(df.columns),
                "size_bytes": path.stat().st_size,
                "sha256": digest,
                "status": "OK",
                "note": "",
            })
        except Exception as exc:
            read_errors.append({"file": path.name, "error": str(exc)})
            file_rows.append({
                "file": path.name, "rows_data": "", "columns": "",
                "size_bytes": path.stat().st_size, "sha256": "",
                "status": "ERROR", "note": str(exc),
            })
    write_csv(file_rows, AUDIT_DIR / "raw_file_inventory.csv")

    exact_duplicate_files = []
    for digest, names in hash_groups.items():
        if len(names) > 1:
            exact_duplicate_files.append({"sha256": digest, "files": " | ".join(names), "count": len(names)})
    write_csv(exact_duplicate_files, AUDIT_DIR / "exact_duplicate_files.csv")

    # So sánh với manifest tùy chọn do người dùng cung cấp.
    manifest_path = PROJECT_DIR / "expected_raw_files.txt"
    manifest_result = {"manifest_found": manifest_path.exists(), "missing_expected_files": [], "unexpected_files": []}
    if manifest_path.exists():
        expected_names = {line.strip() for line in manifest_path.read_text(encoding="utf-8-sig").splitlines() if line.strip() and not line.strip().startswith("#")}
        actual_names = {p.name for p in raw_files}
        manifest_result["missing_expected_files"] = sorted(expected_names - actual_names)
        manifest_result["unexpected_files"] = sorted(actual_names - expected_names)
    likely_unexpected = []
    for p in raw_files:
        if not p.name.lower().startswith("dataset_"):
            likely_unexpected.append({"file": p.name, "reason": "Tên không theo mẫu dataset_*.csv; cần xác nhận thủ công"})
        if p.stat().st_size == 0:
            likely_unexpected.append({"file": p.name, "reason": "File rỗng"})
    write_csv(likely_unexpected, AUDIT_DIR / "files_to_review.csv")

    print(f"- File đọc lỗi: {len(read_errors)}")
    print(f"- Nhóm file giống hệt từng byte: {len(exact_duplicate_files)}")
    print(f"- File cần xem thủ công do tên bất thường/rỗng: {len(likely_unexpected)}")
    if EXPECTED_FILE_COUNT is not None and len(raw_files) != EXPECTED_FILE_COUNT:
        print(f"- CẢNH BÁO: số file thực tế lệch dự kiến {abs(len(raw_files)-EXPECTED_FILE_COUNT)} file.")
        print("  Không thể khẳng định file nào là 'file thứ 46' nếu chưa có danh sách 45 file gốc.")
        print("  Nếu có danh sách chuẩn, tạo expected_raw_files.txt (mỗi dòng một tên file) để so sánh chính xác.")
    if manifest_result["manifest_found"]:
        print(f"- Theo manifest: thiếu {len(manifest_result['missing_expected_files'])}, ngoài danh sách {len(manifest_result['unexpected_files'])}.")
    (AUDIT_DIR / "manifest_comparison.json").write_text(json.dumps(manifest_result, ensure_ascii=False, indent=2), encoding="utf-8")

    # 2. Đọc các báo cáo giai đoạn 1 và tóm tắt thiếu/trùng.
    print("\n[2/4] Kiểm tra báo cáo dữ liệu trùng và dữ liệu thiếu...")
    duplicate_path = PROCESSED_DIR / "duplicate_records.csv"
    quality_path = PROCESSED_DIR / "data_quality_report.csv"
    duplicates = read_csv_safely(duplicate_path) if duplicate_path.exists() else pd.DataFrame()
    quality = read_csv_safely(quality_path) if quality_path.exists() else pd.DataFrame()
    duplicate_summary = {
        "duplicate_records_file_exists": duplicate_path.exists(),
        "duplicate_rows_in_report": int(len(duplicates)),
        "quality_report_exists": quality_path.exists(),
        "quality_columns_reported": int(len(quality)),
    }
    if not quality.empty and "missing_count" in quality.columns:
        quality["missing_count_num"] = pd.to_numeric(quality["missing_count"], errors="coerce").fillna(0)
        quality["missing_percent_num"] = pd.to_numeric(quality.get("missing_percent", 0), errors="coerce").fillna(0)
        quality_sorted = quality.sort_values(["missing_count_num", "missing_percent_num"], ascending=False)
        quality_sorted.to_csv(AUDIT_DIR / "missing_values_ranked.csv", index=False, encoding="utf-8-sig")
        important_cols = [c for c in ["column", "dtype", "missing_count", "missing_percent", "unique_non_null"] if c in quality_sorted.columns]
        quality_top = quality_sorted[important_cols].head(30).to_dict(orient="records")
    else:
        quality_top = []
    (AUDIT_DIR / "duplicate_quality_summary.json").write_text(
        json.dumps({**duplicate_summary, "top_missing_columns": quality_top}, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    print(f"- Số dòng trong duplicate_records.csv: {len(duplicates):,}")
    print(f"- Số cột trong data_quality_report.csv: {len(quality):,}")
    if quality_top:
        print("- 10 cột có tỷ lệ thiếu cao nhất:")
        for item in quality_top[:10]:
            print(f"  • {item.get('column')}: thiếu {item.get('missing_count')} ({item.get('missing_percent')}%)")

    # 3. Kiểm tra hashtag_stats: top hashtag, hashtag bất thường, thống kê phân phối.
    print("\n[3/4] Kiểm tra thống kê hashtag...")
    stats_path = PROCESSED_DIR / "hashtag_stats.csv"
    stats = read_csv_safely(stats_path) if stats_path.exists() else pd.DataFrame()
    if not stats.empty:
        tag_col = "hashtag" if "hashtag" in stats.columns else stats.columns[0]
        count_col = "video_count" if "video_count" in stats.columns else (stats.columns[1] if len(stats.columns) > 1 else None)
        if count_col:
            stats[count_col] = pd.to_numeric(stats[count_col], errors="coerce")
            stats_sorted = stats.sort_values(count_col, ascending=False)
        else:
            stats_sorted = stats.copy()
        stats_sorted.head(100).to_csv(AUDIT_DIR / "hashtag_top100.csv", index=False, encoding="utf-8-sig")
        weird_rows = []
        for _, row in stats.iterrows():
            tag = str(row.get(tag_col, ""))
            reasons = []
            if not tag or tag.lower() in {"nan", "none", "<na>"}:
                reasons.append("hashtag rỗng/null")
            if any(ch.isspace() for ch in tag):
                reasons.append("chứa khoảng trắng")
            if len(tag) > 80:
                reasons.append("dài hơn 80 ký tự")
            if tag.startswith("#"):
                reasons.append("vẫn còn ký tự # ở đầu")
            if re.search(r"[<>\[\]{}\\/|]", tag):
                reasons.append("chứa ký tự đáng ngờ")
            if tag.count("#"):
                reasons.append("chứa # ở giữa hashtag")
            if reasons:
                item = {"hashtag": tag, "reason": "; ".join(reasons)}
                if count_col:
                    item["video_count"] = row.get(count_col)
                weird_rows.append(item)
        write_csv(weird_rows, AUDIT_DIR / "hashtag_suspicious.csv")
        print(f"- Tổng số hashtag trong bảng thống kê: {len(stats):,}")
        print("- Top 15 hashtag theo số video:")
        for _, row in stats_sorted.head(15).iterrows():
            print(f"  • {row.get(tag_col)}: {row.get(count_col, '')}")
        print(f"- Hashtag cần xem lại theo heuristic: {len(weird_rows):,}")
    else:
        print("- Không tìm thấy hoặc không đọc được hashtag_stats.csv.")

    # 4. Kiểm chứng các video có hashtag_count = 0 bằng cách tính lại từ cột hashtags/*/name và caption text.
    print("\n[4/4] Kiểm chứng các video đang được báo là không có hashtag...")
    cleaned_path = PROCESSED_DIR / "cleaned_data.csv"
    if not cleaned_path.exists():
        print(f"- Không tìm thấy {cleaned_path}; bỏ qua bước kiểm chứng zero hashtag.")
        zero_summary = {"cleaned_data_exists": False}
    else:
        clean = read_csv_safely(cleaned_path)
        if "hashtags_clean" in clean.columns:
            stored_zero = clean["hashtags_clean"].fillna("").astype(str).str.strip().eq("")
        elif "hashtag_count" in clean.columns:
            stored_zero = pd.to_numeric(clean["hashtag_count"], errors="coerce").fillna(0).eq(0)
        else:
            stored_zero = pd.Series([False] * len(clean), index=clean.index)
        zero_df = clean.loc[stored_zero].copy()
        raw_hashtag_cols = [c for c in clean.columns if HASHTAG_COL_RE.fullmatch(str(c))]
        raw_hashtag_present = pd.Series(False, index=zero_df.index)
        for col in raw_hashtag_cols:
            raw_hashtag_present |= zero_df[col].notna() & zero_df[col].astype(str).str.strip().ne("")
        caption_hashtag_present = zero_df.get("text", pd.Series([""] * len(zero_df), index=zero_df.index)).fillna("").astype(str).str.contains(CAPTION_TAG_RE)
        can_reextract = bool(raw_hashtag_cols) or "text" in zero_df.columns
        recalc_tags = zero_df.apply(extract_tags_from_row, axis=1) if can_reextract else pd.Series([[] for _ in range(len(zero_df))], index=zero_df.index)
        recovered = recalc_tags.apply(bool)
        # Save row-level audit with identifiers and evidence columns.
        keep_cols = [c for c in ["id", "webVideoUrl", "source_file", "source_hashtag", "text", "hashtags_clean", "hashtag_count"] if c in zero_df.columns]
        zero_audit = zero_df[keep_cols].copy()
        zero_audit["raw_structured_hashtag_present"] = raw_hashtag_present.values
        zero_audit["caption_hashtag_present"] = caption_hashtag_present.values
        zero_audit["hashtag_recovered_by_recheck"] = recovered.values
        zero_audit["rechecked_hashtags"] = recalc_tags.apply(lambda x: "|".join(x)).values
        zero_audit["interpretation"] = [
            "CÓ hashtag ở dữ liệu gốc nhưng hashtags_clean trống: lỗi trích xuất/chuẩn hóa cần sửa" if a else
            "Trích xuất lại tìm thấy hashtag trong caption: cần sửa logic trích xuất" if b else
            "Không thấy hashtag trong cột cấu trúc hoặc caption đã lưu; nhiều khả năng video gốc không có hashtag, cần kiểm tra mẫu thủ công"
            for a, b in zip(raw_hashtag_present.tolist(), recovered.tolist())
        ]
        zero_audit.to_csv(AUDIT_DIR / "zero_hashtag_video_audit.csv", index=False, encoding="utf-8-sig")
        zero_summary = {
            "cleaned_data_exists": True,
            "cleaned_rows": int(len(clean)),
            "stored_zero_hashtag_rows": int(len(zero_df)),
            "zero_rows_with_structured_hashtag_values": int(raw_hashtag_present.sum()),
            "zero_rows_with_caption_hashtag_pattern": int(caption_hashtag_present.sum()),
            "zero_rows_recovered_by_recheck": int(recovered.sum()),
            "hashtag_structured_columns_found": len(raw_hashtag_cols),
            "text_column_found": "text" in clean.columns,
            "note": "Đây là kiểm chứng trên cột gốc còn lưu trong cleaned_data.csv; nếu không có cột gốc thì cần đối chiếu raw CSV theo source_file/id."
        }
        (AUDIT_DIR / "zero_hashtag_summary.json").write_text(json.dumps(zero_summary, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"- Dòng không hashtag theo cleaned_data: {len(zero_df):,}")
        print(f"- Trong số đó có hashtag ở cột cấu trúc gốc: {int(raw_hashtag_present.sum()):,}")
        print(f"- Có dấu # trong caption: {int(caption_hashtag_present.sum()):,}")
        print(f"- Trích xuất lại tìm được hashtag: {int(recovered.sum()):,}")
        print("- Xem chi tiết: zero_hashtag_video_audit.csv")

    # Tạo file tổng hợp dễ gửi lại để được hỗ trợ.
    summary = {
        "raw_csv_count": len(raw_files),
        "expected_raw_csv_count": EXPECTED_FILE_COUNT,
        "raw_read_errors": read_errors,
        "exact_duplicate_file_groups": exact_duplicate_files,
        "files_to_review": likely_unexpected,
        "manifest_comparison": manifest_result,
        "duplicate_quality_summary": duplicate_summary,
        "hashtag_stats_rows": int(len(stats)),
        "suspicious_hashtag_count": int(len(weird_rows)) if not stats.empty else None,
        "zero_hashtag_audit": zero_summary,
        "audit_output_dir": str(AUDIT_DIR),
    }
    (AUDIT_DIR / "audit_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    print("\n" + "=" * 72)
    print("HOÀN TẤT KIỂM TRA")
    print(f"Thư mục báo cáo: {AUDIT_DIR}")
    print("File nên xem trước:")
    print("  1. audit_summary.json")
    print("  2. raw_file_inventory.csv")
    print("  3. files_to_review.csv và exact_duplicate_files.csv")
    print("  4. missing_values_ranked.csv và duplicate_quality_summary.json")
    print("  5. hashtag_top100.csv và hashtag_suspicious.csv")
    print("  6. zero_hashtag_summary.json và zero_hashtag_video_audit.csv")
    print("Lưu ý: script gắn cờ để bạn xem lại, không tự xóa hoặc sửa bất kỳ bản ghi nào.")


if __name__ == "__main__":
    main()
