#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build an undirected weighted hashtag co-occurrence network from cleaned_data.csv."""
from __future__ import annotations
import ast, json, re, sys, unicodedata
from collections import Counter
from itertools import combinations
from pathlib import Path
import pandas as pd

PROJECT_DIR = Path(__file__).resolve().parent
INPUT_FILE = PROJECT_DIR / "data" / "processed" / "cleaned_data.csv"
OUTPUT_DIR = PROJECT_DIR / "data" / "processed" / "network"
MIN_EDGE_WEIGHT = 1
ADD_HASHTAGS_FROM_CAPTION = False
MAX_HASHTAG_LENGTH = 100
HASHTAG_RE = re.compile(r"#([^\s#]+)", flags=re.UNICODE)

def _strip_edge_punctuation(tag):
    """Remove punctuation at the edges, but preserve emoji/symbols and accents."""
    start, end = 0, len(tag)
    while start < end and unicodedata.category(tag[start]).startswith("P"):
        start += 1
    while end > start and unicodedata.category(tag[end - 1]).startswith("P"):
        end -= 1
    return tag[start:end]


def normalize_hashtag(value):
    """Normalize hashtags without dropping multilingual text or emoji sequences."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None

    tag = unicodedata.normalize("NFC", str(value).strip())
    if not tag:
        return None
    if tag.startswith("#"):
        tag = tag[1:]

    # Trim punctuation at the edges, but keep symbols (emoji/flags) and Unicode marks.
    tag = _strip_edge_punctuation(tag).lower()
    tag = unicodedata.normalize("NFC", tag)
    if not tag or len(tag) > MAX_HASHTAG_LENGTH:
        return None

    # Reject whitespace, hashtag delimiter, controls and surrogates. Keep format
    # characters such as ZWJ because they are required by some emoji sequences.
    for ch in tag:
        category = unicodedata.category(ch)
        if ch.isspace() or ch in {"|", "#"} or category in {"Cc", "Cs", "Zl", "Zp", "Zs"}:
            return None

    # Allow text/numbers as well as symbol-only hashtags such as ❤️ and 🇻🇳.
    if not any(unicodedata.category(ch)[0] in {"L", "N", "S"} for ch in tag):
        return None
    return tag

def parse_hashtag_cell(value):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return []
    if isinstance(value, (list, tuple, set)):
        raw_items = list(value)
    else:
        s = str(value).strip()
        if not s or s.lower() in {"nan", "none", "null", "[]"}:
            return []
        raw_items = None
        if s.startswith(("[", "(")):
            try:
                parsed = ast.literal_eval(s)
                if isinstance(parsed, (list, tuple, set)):
                    raw_items = list(parsed)
            except (ValueError, SyntaxError):
                pass
        if raw_items is None:
            raw_items = s.split("|") if "|" in s else [s]
    return sorted({tag for item in raw_items if (tag := normalize_hashtag(item))})

def find_column(columns, candidates):
    return next((name for name in candidates if name in columns), None)

def main():
    print("=" * 68)
    print("XÂY DỰNG MẠNG ĐỒNG XUẤT HIỆN HASHTAG")
    print("=" * 68)
    if not INPUT_FILE.exists():
        print(f"Không tìm thấy file đầu vào: {INPUT_FILE}")
        print("Đặt script ở thư mục dự án có data/processed/cleaned_data.csv.")
        sys.exit(1)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(INPUT_FILE, low_memory=False, encoding="utf-8-sig")
    print(f"Đọc {len(df):,} video, {len(df.columns):,} cột.")

    list_col = find_column(df.columns, ["hashtags_clean_list", "hashtags_list", "hashtags"])
    string_col = find_column(df.columns, ["hashtags_clean", "source_hashtags_all"])
    caption_col = "text" if "text" in df.columns else None
    if not list_col and not string_col and not (ADD_HASHTAGS_FROM_CAPTION and caption_col):
        print("Không tìm thấy cột hashtag. Các cột có chứa 'hashtag':")
        print([c for c in df.columns if "hashtag" in str(c).lower()])
        sys.exit(1)
    print(f"Cột list: {list_col or 'không có'}; cột chuỗi: {string_col or 'không có'}")

    node_frequency, edge_weight = Counter(), Counter()
    video_tag_rows, videos_with_tags, videos_without_tags = [], 0, 0
    videos_with_one_tag, total_mentions, max_tags = 0, 0, 0
    id_col = "id" if "id" in df.columns else ("webVideoUrl" if "webVideoUrl" in df.columns else None)

    for idx, row in df.iterrows():
        tags = parse_hashtag_cell(row.get(list_col)) if list_col else []
        if not tags and string_col:
            tags = parse_hashtag_cell(row.get(string_col))
        if ADD_HASHTAGS_FROM_CAPTION and caption_col:
            caption = row.get(caption_col, "")
            if caption is not None and not (isinstance(caption, float) and pd.isna(caption)):
                tags = sorted(set(tags + [t for raw in HASHTAG_RE.findall(str(caption)) if (t := normalize_hashtag(raw))]))
        if not tags:
            videos_without_tags += 1
            continue

        videos_with_tags += 1
        total_mentions += len(tags)
        max_tags = max(max_tags, len(tags))
        node_frequency.update(tags)
        if len(tags) == 1:
            videos_with_one_tag += 1
        else:
            for pair in combinations(tags, 2):
                edge_weight[pair] += 1
        video_tag_rows.append({
            "video_id": row.get(id_col, idx) if id_col else idx,
            "hashtags": "|".join(tags),
            "hashtag_count": len(tags),
        })
        if (idx + 1) % 5000 == 0:
            print(f"  Đã xử lý {idx + 1:,}/{len(df):,} video...")

    edges = [(a, b, w) for (a, b), w in edge_weight.items() if w >= MIN_EDGE_WEIGHT]
    edges.sort(key=lambda x: (-x[2], x[0], x[1]))
    nodes = [{"node_id": tag, "hashtag": tag, "video_frequency": int(freq)}
             for tag, freq in sorted(node_frequency.items(), key=lambda x: (-x[1], x[0]))]
    edge_rows = [{"source": a, "target": b, "weight": int(w),
                  "relation": "co_occurs_in_same_video"} for a, b, w in edges]

    pd.DataFrame(nodes, columns=["node_id", "hashtag", "video_frequency"]).to_csv(
        OUTPUT_DIR / "nodes.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(edge_rows, columns=["source", "target", "weight", "relation"]).to_csv(
        OUTPUT_DIR / "edges.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(video_tag_rows, columns=["video_id", "hashtags", "hashtag_count"]).to_csv(
        OUTPUT_DIR / "video_hashtag_mapping.csv", index=False, encoding="utf-8-sig")

    # Export GraphML for Gephi.
    import xml.etree.ElementTree as ET
    ns = "http://graphml.graphdrawing.org/xmlns"
    ET.register_namespace("", ns)
    root = ET.Element(f"{{{ns}}}graphml")
    ET.SubElement(root, f"{{{ns}}}key", id="hashtag", **{"for":"node","attr.name":"hashtag","attr.type":"string"})
    ET.SubElement(root, f"{{{ns}}}key", id="video_frequency", **{"for":"node","attr.name":"video_frequency","attr.type":"int"})
    ET.SubElement(root, f"{{{ns}}}key", id="weight", **{"for":"edge","attr.name":"weight","attr.type":"int"})
    graph = ET.SubElement(root, f"{{{ns}}}graph", id="hashtag_network", edgedefault="undirected")
    for node in nodes:
        n = ET.SubElement(graph, f"{{{ns}}}node", id=node["node_id"])
        ET.SubElement(n, f"{{{ns}}}data", key="hashtag").text = node["hashtag"]
        ET.SubElement(n, f"{{{ns}}}data", key="video_frequency").text = str(node["video_frequency"])
    for i, edge in enumerate(edge_rows):
        e = ET.SubElement(graph, f"{{{ns}}}edge", id=f"e{i}", source=edge["source"], target=edge["target"])
        ET.SubElement(e, f"{{{ns}}}data", key="weight").text = str(edge["weight"])
    ET.ElementTree(root).write(OUTPUT_DIR / "hashtag_network.graphml", encoding="utf-8", xml_declaration=True)

    summary = {
        "input_file": str(INPUT_FILE), "output_directory": str(OUTPUT_DIR),
        "input_video_rows": int(len(df)), "videos_with_at_least_one_hashtag": videos_with_tags,
        "videos_without_hashtags": videos_without_tags, "videos_with_exactly_one_hashtag": videos_with_one_tag,
        "unique_nodes": len(nodes), "unique_edges_before_weight_filter": len(edge_weight),
        "unique_edges_after_weight_filter": len(edges), "min_edge_weight": MIN_EDGE_WEIGHT,
        "total_video_hashtag_mentions": total_mentions, "max_unique_hashtags_in_one_video": max_tags,
        "network_type": "undirected weighted co-occurrence network",
        "node_definition": "one normalized hashtag",
        "hashtag_normalization": "Unicode NFC + lowercase; trims edge punctuation; preserves multilingual characters, emoji/symbols and ZWJ sequences; rejects whitespace, internal # or |, controls/surrogates, and tags longer than 100 characters",
        "hashtag_normalization": "lowercase; trim edge punctuation; preserve Unicode letters, combining marks and symbols/emoji; reject whitespace/control characters and embedded # or |",
        "edge_definition": "two distinct hashtags co-occur in the same video",
        "edge_weight_definition": "number of videos in which the hashtag pair co-occurs",
        "interpretation_note": "A video with k distinct hashtags contributes k*(k-1)/2 pairwise co-occurrence counts."
    }
    (OUTPUT_DIR / "network_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\nHOÀN TẤT XÂY DỰNG MẠNG")
    print(f"Video đầu vào: {len(df):,}")
    print(f"Video có hashtag: {videos_with_tags:,}; không có hashtag: {videos_without_tags:,}")
    print(f"Node: {len(nodes):,}")
    print(f"Edge trước lọc: {len(edge_weight):,}; sau lọc: {len(edges):,}")
    print(f"Đầu ra: {OUTPUT_DIR}")
    print("  nodes.csv, edges.csv, video_hashtag_mapping.csv, hashtag_network.graphml, network_summary.json")
    print("Node = hashtag; edge/link = hai hashtag cùng xuất hiện trong một video; weight = số video cùng chứa cặp đó.")

if __name__ == "__main__":
    main()
