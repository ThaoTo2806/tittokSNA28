# -*- coding: utf-8 -*-
"""
Finalize and audit Stage 1 of the TikTok hashtag co-occurrence SNA project.

Expected layout (default):
  PROJECT_DIR/
    data/processed/cleaned_data.csv
    data/processed/network/nodes.csv
    data/processed/network/edges.csv

Run from anywhere:
  py finalize_stage1.py
  py finalize_stage1.py --project-dir "D:\\HOCTAP\\abc\\tittokSNA28"

Outputs in data/processed/network/:
  adjacency_matrix.npz          (SciPy CSR sparse matrix; undirected, weighted)
  node_index.csv                 (matrix row/column index -> hashtag)
  stage1_final_report.json       (machine-readable summary)
  stage1_validation_report.csv   (individual checks and statuses)

This script does not modify the input CSV files.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

try:
    from scipy.sparse import coo_matrix, save_npz
except ImportError:
    print("Thiếu scipy. Cài bằng: py -m pip install scipy", file=sys.stderr)
    raise

HASHTAG_RE = re.compile(r"^[\w.-]+$", flags=re.UNICODE)


def parse_hashtags(value):
    """Parse the pipe-delimited hashtags_clean column into unique normalized tags."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return []
    s = str(value).strip()
    if not s or s.lower() in {"nan", "none", "null", "[]"}:
        return []
    # cleaned_data.csv is generated with '|'. Avoid splitting a single tag otherwise.
    items = s.split("|") if "|" in s else [s]
    result = []
    seen = set()
    for item in items:
        tag = item.strip().strip("#").strip().lower()
        if tag and tag not in seen:
            seen.add(tag)
            result.append(tag)
    return result


def read_csv(path):
    return pd.read_csv(path, encoding="utf-8-sig", low_memory=False)


def add_check(checks, name, status, observed=None, expected=None, details=""):
    checks.append({
        "check": name,
        "status": status,
        "observed": observed,
        "expected": expected,
        "details": details,
    })


def main():
    parser = argparse.ArgumentParser(description="Audit and finalize Stage 1 hashtag network.")
    parser.add_argument(
        "--project-dir", default=str(Path(__file__).resolve().parent),
        help="Project root containing data/processed/cleaned_data.csv (default: script directory)."
    )
    args = parser.parse_args()
    project_dir = Path(args.project_dir).expanduser().resolve()
    processed_dir = project_dir / "data" / "processed"
    network_dir = processed_dir / "network"
    cleaned_path = processed_dir / "cleaned_data.csv"
    nodes_path = network_dir / "nodes.csv"
    edges_path = network_dir / "edges.csv"
    summary_path = network_dir / "network_summary.json"

    missing = [str(p) for p in (cleaned_path, nodes_path, edges_path) if not p.exists()]
    if missing:
        raise FileNotFoundError(
            "Không tìm thấy file đầu vào:\n- " + "\n- ".join(missing) +
            "\nHãy đặt script ở thư mục gốc dự án hoặc dùng --project-dir."
        )
    network_dir.mkdir(parents=True, exist_ok=True)

    checks = []
    clean = read_csv(cleaned_path)
    nodes = read_csv(nodes_path)
    edges = read_csv(edges_path)

    # ---- Validate required columns ----
    if "hashtags_clean" not in clean.columns:
        raise ValueError("cleaned_data.csv thiếu cột 'hashtags_clean'.")
    node_col = "node_id" if "node_id" in nodes.columns else ("hashtag" if "hashtag" in nodes.columns else None)
    if node_col is None:
        raise ValueError("nodes.csv cần có cột 'node_id' hoặc 'hashtag'.")
    if not {"source", "target", "weight"}.issubset(edges.columns):
        raise ValueError("edges.csv cần có các cột 'source', 'target', 'weight'.")

    # ---- Video / hashtag counts from cleaned data ----
    all_tags_per_video = clean["hashtags_clean"].apply(parse_hashtags)
    clean_zero_count = int(all_tags_per_video.map(len).eq(0).sum())
    clean_tag_counter = Counter(tag for tags in all_tags_per_video for tag in tags)
    clean_unique_tags = set(clean_tag_counter)
    cleaned_video_count = int(len(clean))

    node_values = nodes[node_col].fillna("").astype(str).str.strip().str.lower()
    node_values = node_values[node_values.ne("")]
    node_list = node_values.tolist()
    node_set = set(node_list)
    duplicate_node_values = int(node_values.duplicated().sum())
    node_set_matches_clean = node_set == clean_unique_tags
    missing_from_nodes = sorted(clean_unique_tags - node_set)
    extra_in_nodes = sorted(node_set - clean_unique_tags)

    add_check(checks, "cleaned_data_readable", "PASS", cleaned_video_count, details=str(cleaned_path))
    add_check(checks, "nodes_readable", "PASS", len(nodes), details=str(nodes_path))
    add_check(checks, "edges_readable", "PASS", len(edges), details=str(edges_path))
    add_check(checks, "node_ids_unique", "PASS" if duplicate_node_values == 0 else "FAIL",
              len(node_list) - duplicate_node_values, expected=len(node_list),
              details=f"duplicate_node_ids={duplicate_node_values}")
    add_check(checks, "unique_hashtags_clean_vs_nodes",
              "PASS" if node_set_matches_clean else "WARN",
              len(node_set), expected=len(clean_unique_tags),
              details=f"missing_from_nodes={len(missing_from_nodes)}; extra_in_nodes={len(extra_in_nodes)}")
    add_check(checks, "zero_hashtag_video_count",
              "INFO", clean_zero_count,
              details="Recomputed from cleaned_data.csv column hashtags_clean; compare with network_summary.json.")

    # ---- Validate edges ----
    node_to_idx = {tag: i for i, tag in enumerate(node_list)}
    # Matrix only includes valid edges whose endpoints are present and whose weight is positive.
    normalized_pairs = []
    valid_rows = []
    duplicate_edge_rows = 0
    self_loops = 0
    invalid_weights = 0
    missing_endpoint_rows = 0
    malformed_endpoint_rows = 0
    seen_pairs = set()
    edge_weights = pd.to_numeric(edges["weight"], errors="coerce")

    for row_pos, (_, row) in enumerate(edges.iterrows()):
        a_raw, b_raw = row["source"], row["target"]
        if pd.isna(a_raw) or pd.isna(b_raw):
            malformed_endpoint_rows += 1
            continue
        a, b = str(a_raw).strip().lower(), str(b_raw).strip().lower()
        if not a or not b:
            malformed_endpoint_rows += 1
            continue
        if a not in node_to_idx or b not in node_to_idx:
            missing_endpoint_rows += 1
            continue
        if a == b:
            self_loops += 1
            continue
        w = edge_weights.iloc[row_pos]
        if pd.isna(w) or not np.isfinite(float(w)) or float(w) <= 0 or not float(w).is_integer():
            invalid_weights += 1
            continue
        pair = tuple(sorted((a, b)))
        if pair in seen_pairs:
            duplicate_edge_rows += 1
        seen_pairs.add(pair)
        valid_rows.append((pair[0], pair[1], int(w)))

    # Combine repeated unordered pairs for matrix construction so the matrix represents total weight.
    pair_weights = Counter()
    for a, b, w in valid_rows:
        pair_weights[(a, b)] += w

    add_check(checks, "duplicate_undirected_edges",
              "PASS" if duplicate_edge_rows == 0 else "WARN",
              duplicate_edge_rows, expected=0,
              details="Counts repeated unordered hashtag pairs, including reversed source/target rows.")
    add_check(checks, "self_loop_edges", "PASS" if self_loops == 0 else "FAIL",
              self_loops, expected=0)
    add_check(checks, "invalid_edge_weights", "PASS" if invalid_weights == 0 else "FAIL",
              invalid_weights, expected=0,
              details="Weight must be finite, positive, and an integer.")
    add_check(checks, "edges_with_missing_node_endpoint",
              "PASS" if missing_endpoint_rows == 0 else "FAIL",
              missing_endpoint_rows, expected=0)
    add_check(checks, "edges_with_empty_endpoint",
              "PASS" if malformed_endpoint_rows == 0 else "FAIL",
              malformed_endpoint_rows, expected=0)

    # ---- Build symmetric weighted sparse adjacency matrix ----
    row_indices, col_indices, data = [], [], []
    for (a, b), weight in pair_weights.items():
        i, j = node_to_idx[a], node_to_idx[b]
        row_indices.extend([i, j])
        col_indices.extend([j, i])
        data.extend([weight, weight])

    n = len(node_list)
    adjacency = coo_matrix(
        (np.asarray(data, dtype=np.int64),
         (np.asarray(row_indices, dtype=np.int64), np.asarray(col_indices, dtype=np.int64))),
        shape=(n, n), dtype=np.int64
    ).tocsr()
    adjacency.sum_duplicates()
    adjacency.eliminate_zeros()

    is_symmetric = (adjacency != adjacency.T).nnz == 0
    has_diagonal = bool(np.any(adjacency.diagonal() != 0))
    add_check(checks, "adjacency_matrix_symmetric",
              "PASS" if is_symmetric else "FAIL", is_symmetric, expected=True)
    add_check(checks, "adjacency_matrix_diagonal_zero",
              "PASS" if not has_diagonal else "FAIL", not has_diagonal, expected=True)
    add_check(checks, "adjacency_matrix_saved_as_sparse",
              "PASS", "CSR .npz", details="Avoids allocating a dense N x N matrix.")

    matrix_path = network_dir / "adjacency_matrix.npz"
    save_npz(matrix_path, adjacency, compressed=True)
    index_path = network_dir / "node_index.csv"
    pd.DataFrame({
        "matrix_index": np.arange(n, dtype=np.int64),
        "node_id": node_list,
        "hashtag": node_list,
    }).to_csv(index_path, index=False, encoding="utf-8-sig")

    # ---- Compare to existing network summary, when available ----
    old_summary = {}
    if summary_path.exists():
        try:
            old_summary = json.loads(summary_path.read_text(encoding="utf-8"))
        except Exception as exc:
            add_check(checks, "network_summary_json_readable", "WARN", details=str(exc))
        else:
            add_check(checks, "network_summary_json_readable", "PASS")
            comparisons = [
                ("summary_input_video_rows_vs_cleaned", old_summary.get("input_video_rows"), cleaned_video_count),
                ("summary_unique_nodes_vs_nodes_csv", old_summary.get("unique_nodes"), len(node_set)),
                ("summary_videos_without_hashtags_vs_cleaned", old_summary.get("videos_without_hashtags"), clean_zero_count),
            ]
            for name, observed, expected in comparisons:
                if observed is None:
                    status = "WARN"
                else:
                    status = "PASS" if int(observed) == int(expected) else "WARN"
                add_check(checks, name, status, observed, expected,
                          details="WARN means the existing summary and recomputed data disagree.")
    else:
        add_check(checks, "network_summary_json_available", "WARN",
                  details="network_summary.json not found; skipped comparison.")

    # Hashtag-level comparison evidence, compact in JSON.
    validation_df = pd.DataFrame(checks)
    validation_path = network_dir / "stage1_validation_report.csv"
    validation_df.to_csv(validation_path, index=False, encoding="utf-8-sig")

    fail_count = int((validation_df["status"] == "FAIL").sum())
    warn_count = int((validation_df["status"] == "WARN").sum())
    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "project_dir": str(project_dir),
        "input_files": {
            "cleaned_data_csv": str(cleaned_path),
            "nodes_csv": str(nodes_path),
            "edges_csv": str(edges_path),
            "network_summary_json": str(summary_path) if summary_path.exists() else None,
        },
        "outputs": {
            "adjacency_matrix_npz": str(matrix_path),
            "node_index_csv": str(index_path),
            "validation_report_csv": str(validation_path),
        },
        "data_counts": {
            "cleaned_video_rows": cleaned_video_count,
            "videos_without_hashtags_recomputed": clean_zero_count,
            "videos_with_hashtags_recomputed": cleaned_video_count - clean_zero_count,
            "unique_hashtags_recomputed_from_cleaned_data": len(clean_unique_tags),
            "nodes_csv_rows": int(len(nodes)),
            "unique_node_ids": len(node_set),
            "duplicate_node_id_rows": duplicate_node_values,
            "hashtags_in_cleaned_missing_from_nodes_count": len(missing_from_nodes),
            "hashtags_in_nodes_not_in_cleaned_count": len(extra_in_nodes),
            "examples_hashtags_missing_from_nodes": missing_from_nodes[:25],
            "examples_extra_nodes_not_in_cleaned": extra_in_nodes[:25],
        },
        "edge_validation": {
            "edges_csv_rows": int(len(edges)),
            "duplicate_undirected_edge_rows_after_first_occurrence": duplicate_edge_rows,
            "self_loop_rows": self_loops,
            "invalid_weight_rows": invalid_weights,
            "rows_with_missing_node_endpoint": missing_endpoint_rows,
            "rows_with_empty_endpoint": malformed_endpoint_rows,
            "unique_valid_undirected_pairs": len(pair_weights),
            "valid_undirected_edge_weight_sum": int(sum(pair_weights.values())),
        },
        "adjacency_matrix": {
            "format": "SciPy CSR sparse matrix saved as compressed NPZ",
            "shape": [int(n), int(n)],
            "nonzero_entries": int(adjacency.nnz),
            "undirected_edge_count": int(adjacency.nnz // 2),
            "is_symmetric": bool(is_symmetric),
            "diagonal_is_zero": bool(not has_diagonal),
            "dtype": str(adjacency.dtype),
            "interpretation": "A[i,j] is the aggregated co-occurrence weight between node_index[i] and node_index[j]. Matrix is symmetric.",
        },
        "validation": {
            "pass_count": int((validation_df["status"] == "PASS").sum()),
            "warn_count": warn_count,
            "fail_count": fail_count,
            "overall_status": "FAIL" if fail_count else ("WARN" if warn_count else "PASS"),
            "note": "WARN indicates discrepancy or duplicate rows needing review; inspect stage1_validation_report.csv before claiming Stage 1 is finalized.",
        },
    }
    report_path = network_dir / "stage1_final_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=" * 68)
    print("STAGE 1 FINALIZATION / AUDIT")
    print("=" * 68)
    print(f"Video trong cleaned_data.csv       : {cleaned_video_count:,}")
    print(f"Video không có hashtag (tính lại)  : {clean_zero_count:,}")
    print(f"Hashtag duy nhất (tính lại)        : {len(clean_unique_tags):,}")
    print(f"Node duy nhất trong nodes.csv      : {len(node_set):,}")
    print(f"Cạnh trong edges.csv               : {len(edges):,}")
    print(f"Cặp cạnh hợp lệ sau gộp            : {len(pair_weights):,}")
    print(f"Ma trận sparse                     : {n:,} x {n:,}; nnz={adjacency.nnz:,}; đối xứng={is_symmetric}")
    print(f"Trạng thái kiểm tra                : {report['validation']['overall_status']} "
          f"(PASS={report['validation']['pass_count']}, WARN={warn_count}, FAIL={fail_count})")
    print("Đã lưu:")
    print(f"  {matrix_path}")
    print(f"  {index_path}")
    print(f"  {report_path}")
    print(f"  {validation_path}")
    if warn_count or fail_count:
        print("LƯU Ý: Có cảnh báo/lỗi. Đọc stage1_validation_report.csv trước khi kết luận giai đoạn 1 đã đạt.")
    else:
        print("Tất cả kiểm tra đều PASS.")


if __name__ == "__main__":
    main()
