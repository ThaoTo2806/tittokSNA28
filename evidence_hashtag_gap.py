# -*- coding: utf-8 -*-
"""
Bằng chứng giải thích chênh lệch số hashtag:
  clean_tiktok_data.py (summary.json)      : unique_hashtags  (24,880)
  build_hashtag_network_fixed.py (nodes)   : số node         (24,869)

Script dùng chính normalize_hashtag() của build_hashtag_network_fixed.py để phân loại
từng hashtag trong cleaned_data.csv thành: giữ nguyên / bị gộp (cùng dạng chuẩn hóa) / bị loại.

Chạy: py evidence_hashtag_gap.py
Đầu ra (data/processed/network/):
  hashtag_gap_evidence.csv   - chi tiết từng hashtag có thay đổi
  hashtag_gap_summary.json   - tổng kết và phép cộng trừ khớp 24,880 -> 24,869
"""
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import build_hashtag_network_fixed as builder

PROJECT_DIR = Path(__file__).resolve().parent
CLEANED = PROJECT_DIR / "data" / "processed" / "cleaned_data.csv"
SUMMARY = PROJECT_DIR / "data" / "processed" / "summary.json"
NODES = PROJECT_DIR / "data" / "processed" / "network" / "nodes.csv"
OUT_DIR = PROJECT_DIR / "data" / "processed" / "network"

csv.field_size_limit(sys.maxsize)


def main():
    raw_freq = Counter()  # hashtag thô trong hashtags_clean -> số video
    with open(CLEANED, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            seen = {t.strip() for t in (row.get("hashtags_clean") or "").split("|") if t.strip()}
            raw_freq.update(seen)

    mapping = {}
    groups = defaultdict(list)
    for tag in raw_freq:
        norm = builder.normalize_hashtag(tag)
        mapping[tag] = norm
        if norm is not None:
            groups[norm].append(tag)

    dropped = sorted(t for t, n in mapping.items() if n is None)
    merged_groups = {n: sorted(ts) for n, ts in groups.items() if len(ts) > 1}
    merged_loss = sum(len(ts) - 1 for ts in merged_groups.values())

    with open(NODES, encoding="utf-8-sig", newline="") as f:
        node_ids = {r["node_id"] for r in csv.DictReader(f)}

    rows = []
    for tag in dropped:
        rows.append({"raw_hashtag": tag, "repr": ascii(tag), "video_count": raw_freq[tag],
                     "status": "DROPPED", "normalized_to": "",
                     "reason": "builder.normalize_hashtag() trả về None (ký tự không hợp lệ / rỗng / quá dài)"})
    for norm, tags in sorted(merged_groups.items()):
        for tag in tags:
            rows.append({"raw_hashtag": tag, "repr": ascii(tag), "video_count": raw_freq[tag],
                         "status": "MERGED", "normalized_to": norm,
                         "reason": "nhiều dạng thô cùng chuẩn hóa về một node (NFC / bỏ dấu câu ở biên)"})
    out_csv = OUT_DIR / "hashtag_gap_evidence.csv"
    with open(out_csv, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["raw_hashtag", "repr", "video_count", "status", "normalized_to", "reason"])
        w.writeheader()
        w.writerows(rows)

    raw_unique_summary = json.loads(SUMMARY.read_text(encoding="utf-8")).get("unique_hashtags")
    normalized_set = {n for n in mapping.values() if n}
    result = {
        "unique_hashtags_in_cleaned_data_recomputed": len(raw_freq),
        "unique_hashtags_in_summary_json": raw_unique_summary,
        "dropped_hashtags": len(dropped),
        "merged_forms_lost": merged_loss,
        "expected_nodes": len(raw_freq) - len(dropped) - merged_loss,
        "nodes_csv_rows": len(node_ids),
        "normalized_set_equals_nodes_csv": normalized_set == node_ids,
        "equation": f"{len(raw_freq)} - {len(dropped)} (dropped) - {merged_loss} (merged) = {len(raw_freq) - len(dropped) - merged_loss}",
        "check_pass": (len(raw_freq) - len(dropped) - merged_loss == len(node_ids)) and normalized_set == node_ids,
    }
    (OUT_DIR / "hashtag_gap_summary.json").write_text(
        json.dumps(result, ensure_ascii=True, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=True, indent=2))
    print(f"Chi tiết: {out_csv}")


if __name__ == "__main__":
    main()
