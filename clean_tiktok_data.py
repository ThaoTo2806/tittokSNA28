# -*- coding: utf-8 -*-
"""
Giai đoạn 1 - Gộp và làm sạch 45 file CSV TikTok cho đề tài SNA.
Cách chạy:
  1) Cài thư viện: py -m pip install pandas
  2) Sửa RAW_DIR nếu thư mục dữ liệu của bạn khác.
  3) Chạy: py clean_tiktok_data.py

Script không ghi đè file raw. Các kết quả được lưu vào data/processed.
"""
from pathlib import Path
import re
import json
import pandas as pd

# ====== CẤU HÌNH ======
PROJECT_DIR = Path(r"D:\HOCTAP\abc\tittokSNA28")
RAW_DIR = PROJECT_DIR / "data" / "raw"
OUT_DIR = PROJECT_DIR / "data" / "processed"

# Các cột tương tác nên chuyển thành số nếu tồn tại
NUMERIC_COLS = [
    "playCount", "diggCount", "commentCount", "shareCount",
    "collectCount", "repostCount", "createTime",
    "searchHashtag/views", "videoMeta/duration",
    "videoMeta/width", "videoMeta/height",
]
TIME_COLS = ["createTimeISO"]
VIDEO_ID_COLS = ["id"]
URL_COLS = ["webVideoUrl"]

def normalize_column_names(df):
    """Loại khoảng trắng thừa ở tên cột, không đổi tên các cột dạng authorMeta/..."""
    df.columns = [str(c).strip() for c in df.columns]
    return df

def read_csv_safely(path):
    """Thử một số encoding thường gặp; giữ nguyên cấu trúc cột."""
    last_error = None
    for enc in ("utf-8-sig", "utf-8", "cp1258", "latin1"):
        try:
            return pd.read_csv(path, encoding=enc, low_memory=False, on_bad_lines="warn")
        except UnicodeDecodeError as e:
            last_error = e
    raise last_error

def clean_hashtag(value):
    if pd.isna(value):
        return ""
    value = str(value).strip().lower()
    value = value.lstrip("#").strip()
    # Xóa khoảng trắng bên trong hashtag, vì hashtag chuẩn không chứa khoảng trắng
    value = re.sub(r"\s+", "", value)
    return value

def extract_hashtags(row):
    """
    Ưu tiên các cột hashtags/0/name, hashtags/1/name, ...
    Đồng thời lấy hashtag trong caption text để bù trường hợp dữ liệu cấu trúc thiếu.
    Trả về hashtag không rỗng, không trùng trong cùng video.
    """
    found = []
    hashtag_cols = [
        c for c in row.index
        if re.fullmatch(r"hashtags/\d+/name", str(c))
    ]
    hashtag_cols.sort(key=lambda c: int(re.search(r"/(\d+)/", c).group(1)))

    for col in hashtag_cols:
        tag = clean_hashtag(row.get(col))
        if tag:
            found.append(tag)

    caption = row.get("text", "")
    if pd.notna(caption):
        # Lấy các chuỗi ngay sau #; giữ chữ/số/_ và ký tự Unicode
        found.extend(re.findall(r"#([^\s#]+)", str(caption)))

    result = []
    seen = set()
    for tag in found:
        tag = clean_hashtag(tag).strip(".,!?;:'\"()[]{}<>")
        if tag and tag not in seen:
            seen.add(tag)
            result.append(tag)
    return result

def first_nonempty(series):
    for x in series:
        if pd.notna(x) and str(x).strip():
            return str(x).strip()
    return ""

def main():
    if not RAW_DIR.exists():
        raise FileNotFoundError(
            f"Không tìm thấy thư mục raw: {RAW_DIR}\n"
            "Hãy sửa biến RAW_DIR ở đầu script cho đúng đường dẫn."
        )
    files = sorted(RAW_DIR.glob("*.csv"))
    if not files:
        raise FileNotFoundError(f"Không tìm thấy file CSV nào trong: {RAW_DIR}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    frames = []
    file_report = []

    print(f"Tìm thấy {len(files)} file CSV. Bắt đầu đọc...")
    for i, path in enumerate(files, start=1):
        try:
            part = read_csv_safely(path)
            part = normalize_column_names(part)
            original_rows = len(part)
            # Giữ tên file để truy nguyên dữ liệu
            part["source_file"] = path.name
            # 'input' trong mẫu dữ liệu là hashtag được dùng khi crawl
            if "input" in part.columns:
                part["source_hashtag"] = part["input"].astype("string").fillna("").str.strip()
            else:
                part["source_hashtag"] = path.stem.removeprefix("dataset_")
            frames.append(part)
            file_report.append({
                "file": path.name,
                "rows_read": original_rows,
                "columns": len(part.columns),
                "status": "OK",
                "error": "",
            })
            print(f"[{i}/{len(files)}] {path.name}: {original_rows:,} dòng")
        except Exception as e:
            file_report.append({
                "file": path.name, "rows_read": 0, "columns": 0,
                "status": "ERROR", "error": str(e),
            })
            print(f"[LỖI] {path.name}: {e}")

    if not frames:
        raise RuntimeError("Không đọc được file CSV nào. Kiểm tra lỗi ở trên.")

    # Gộp tất cả file; những cột không đồng nhất sẽ được giữ lại, giá trị không có sẽ để trống.
    merged = pd.concat(frames, ignore_index=True, sort=False)
    merged.to_csv(OUT_DIR / "merged_raw.csv", index=False, encoding="utf-8-sig")
    print(f"\nĐã gộp: {len(merged):,} dòng, {len(merged.columns):,} cột.")

    # Chuẩn hóa chuỗi rỗng và khoảng trắng ở các cột dạng text.
    for col in merged.select_dtypes(include=["object", "string"]).columns:
        merged[col] = merged[col].map(
            lambda x: x.strip() if isinstance(x, str) else x
        )
        merged[col] = merged[col].replace(r"^\s*$", pd.NA, regex=True)

    # Chuẩn hóa cột thời gian. errors='coerce' đưa giá trị không hợp lệ về NaT.
    for col in TIME_COLS:
        if col in merged.columns:
            merged[col] = pd.to_datetime(merged[col], errors="coerce", utc=True)

    # Chuẩn hóa các cột số; giá trị không chuyển đổi được thành số sẽ thành NA.
    for col in NUMERIC_COLS:
        if col in merged.columns:
            merged[col] = pd.to_numeric(merged[col], errors="coerce")

    # Tạo danh sách hashtag sạch cho từng video.
    merged["hashtags_clean_list"] = merged.apply(extract_hashtags, axis=1)
    merged["hashtags_clean"] = merged["hashtags_clean_list"].apply(
        lambda tags: "|".join(tags)
    )
    merged["hashtag_count"] = merged["hashtags_clean_list"].apply(len)

    # Chuẩn hóa ID và URL để khử trùng lặp. Ưu tiên ID, sau đó URL.
    # Không xóa theo text vì nhiều video khác nhau có thể có caption giống nhau.
    if "id" in merged.columns:
        merged["_dedup_key"] = merged["id"].astype("string").str.strip()
        merged.loc[merged["_dedup_key"].isin(["", "nan", "<NA>"]), "_dedup_key"] = pd.NA
    else:
        merged["_dedup_key"] = pd.NA

    if "webVideoUrl" in merged.columns:
        url_key = merged["webVideoUrl"].astype("string").str.strip().str.rstrip("/")
        url_key = url_key.mask(url_key.isin(["", "nan", "<NA>"]))
        merged["_dedup_key"] = merged["_dedup_key"].fillna(url_key)

    # Những dòng không có ID/URL được giữ lại; không thể khẳng định chúng là video trùng.
    has_key = merged["_dedup_key"].notna()
    duplicate_mask = has_key & merged.duplicated(subset=["_dedup_key"], keep="first")
    duplicates = merged.loc[duplicate_mask].copy()
    duplicates.to_csv(OUT_DIR / "duplicate_records.csv", index=False, encoding="utf-8-sig")

    # Trước khi loại trùng, tổng hợp mọi hashtag nguồn đã crawl ra cho mỗi video.
    source_map = {}
    if "source_hashtag" in merged.columns:
        keyed = merged.loc[has_key, ["_dedup_key", "source_hashtag"]]
        for key, group in keyed.groupby("_dedup_key", dropna=True):
            vals = []
            seen = set()
            for value in group["source_hashtag"].dropna().astype(str):
                value = value.strip()
                if value and value.lower() not in seen:
                    seen.add(value.lower())
                    vals.append(value)
            source_map[str(key)] = "|".join(vals)

    clean = merged.loc[~duplicate_mask].copy()
    if source_map:
        clean["source_hashtags_all"] = clean["_dedup_key"].map(
            lambda x: source_map.get(str(x), "") if pd.notna(x) else ""
        )

    # Các cột tiện cho phân tích; không loại các cột gốc.
    clean.drop(columns=["_dedup_key", "hashtags_clean_list"], inplace=True, errors="ignore")
    clean.to_csv(OUT_DIR / "cleaned_data.csv", index=False, encoding="utf-8-sig")

    # Báo cáo chất lượng theo cột: số thiếu và tỷ lệ thiếu.
    quality_rows = []
    for col in clean.columns:
        missing = int(clean[col].isna().sum())
        quality_rows.append({
            "column": col,
            "dtype": str(clean[col].dtype),
            "missing_count": missing,
            "missing_percent": round(missing / len(clean) * 100, 2) if len(clean) else 0,
            "unique_non_null": int(clean[col].nunique(dropna=True)),
        })
    pd.DataFrame(quality_rows).to_csv(
        OUT_DIR / "data_quality_report.csv", index=False, encoding="utf-8-sig"
    )
    pd.DataFrame(file_report).to_csv(
        OUT_DIR / "file_read_report.csv", index=False, encoding="utf-8-sig"
    )

    # Thống kê hashtag: tần suất số video chứa mỗi hashtag.
    hashtag_counts = {}
    for tags in clean["hashtags_clean"].fillna("").astype(str):
        for tag in tags.split("|"):
            tag = tag.strip()
            if tag:
                hashtag_counts[tag] = hashtag_counts.get(tag, 0) + 1
    hashtag_stats = pd.DataFrame(
        [{"hashtag": tag, "video_count": count}
         for tag, count in sorted(hashtag_counts.items(), key=lambda x: (-x[1], x[0]))]
    )
    hashtag_stats.to_csv(OUT_DIR / "hashtag_stats.csv", index=False, encoding="utf-8-sig")

    # Báo cáo tổng quan dưới dạng JSON.
    summary = {
        "csv_files_found": len(files),
        "csv_files_read_successfully": sum(x["status"] == "OK" for x in file_report),
        "rows_before_deduplication": int(len(merged)),
        "duplicate_rows_removed": int(duplicate_mask.sum()),
        "rows_after_deduplication": int(len(clean)),
        "unique_video_ids": int(clean["id"].nunique(dropna=True)) if "id" in clean.columns else None,
        "unique_hashtags": int(len(hashtag_counts)),
        "rows_with_zero_hashtags": int((clean["hashtag_count"] == 0).sum()),
        "output_directory": str(OUT_DIR),
    }
    with open(OUT_DIR / "summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print("\n========== HOÀN TẤT GIAI ĐOẠN 1 ==========")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"\nCác file kết quả nằm tại: {OUT_DIR}")
    print("Kiểm tra summary.json, data_quality_report.csv và duplicate_records.csv trước khi sang giai đoạn 2.")

if __name__ == "__main__":
    main()
