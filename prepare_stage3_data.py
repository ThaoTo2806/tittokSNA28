"""
Stage 3 - Chuan bi du lieu thoi gian cho phan tich mang dong (chay LOCAL truoc khi upload Kaggle).

Ghep video_hashtag_mapping.csv (hashtag da chuan hoa giong Stage 1) voi createTime trong cleaned_data.csv.
Dau ra: data/processed/temporal/video_hashtag_time.csv  (file nho, upload len Kaggle)
"""
import os

import pandas as pd

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
CLEANED = os.path.join(PROJECT_DIR, "data", "processed", "cleaned_data.csv")
MAPPING = os.path.join(PROJECT_DIR, "data", "processed", "network", "video_hashtag_mapping.csv")
OUT_DIR = os.path.join(PROJECT_DIR, "data", "processed", "temporal")


def main():
    cols = ["id", "createTime", "source_file", "playCount", "diggCount"]
    meta = pd.read_csv(CLEANED, encoding="utf-8-sig", usecols=lambda c: c in cols, dtype={"id": str}, low_memory=False)
    meta = meta.rename(columns={"id": "video_id", "createTime": "create_time"})
    mapping = pd.read_csv(MAPPING, encoding="utf-8-sig", dtype={"video_id": str})

    df = mapping.merge(meta, on="video_id", how="left", validate="one_to_one")
    missing = int(df["create_time"].isna().sum())
    if missing:
        raise SystemExit(f"{missing} video khong tim thay createTime - kiem tra lai khoa video_id")

    df["create_time"] = df["create_time"].astype("int64")
    df["create_date"] = pd.to_datetime(df["create_time"], unit="s", utc=True).dt.strftime("%Y-%m-%d")
    df = df.sort_values("create_time")
    os.makedirs(OUT_DIR, exist_ok=True)
    out = os.path.join(OUT_DIR, "video_hashtag_time.csv")
    df[["video_id", "create_time", "create_date", "hashtags", "hashtag_count", "source_file", "playCount", "diggCount"]] \
        .to_csv(out, index=False, encoding="utf-8")

    print(f"Video co hashtag: {len(df)}")
    print(f"Khoang thoi gian: {df['create_date'].min()} -> {df['create_date'].max()}")
    print(df["create_date"].str[:7].value_counts().sort_index().tail(12).to_string())
    print(f"Da luu: {out}")


if __name__ == "__main__":
    main()
