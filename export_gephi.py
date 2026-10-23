"""
Stage 4 - Xuat file GEXF de truc quan hoa / mo phong tren Gephi.

Dau vao:
  data/processed/network/{node_index.csv, edges.csv}           (Stage 1)
  data/processed/centrality/centrality_all.csv                 (Stage 2)
  data/processed/temporal/video_hashtag_time.csv               (Stage 3 - du lieu theo thoi gian)
  kaggle/stage3_results/stage3_output/{partitions.csv, community_timeline.csv}   (Stage 3 - ket qua Kaggle)

Dau ra: data/processed/gephi/
  1_static_backbone.gexf     mang "xuong song" (top N hashtag theo degree, canh weight >= min) - de ve dep
  2_static_full.gexf         toan bo mang 24,869 node / 213,266 canh (nang)
  3_dynamic_communities.gexf mang DONG theo thang (Timeline cua Gephi) - mo phong tien hoa cong dong
  4_community_evolution.gexf do thi tien hoa cong dong: node = (cong dong, thang), da dat san vi tri
  static_communities.csv     cong dong Leiden tren mang tinh: kich thuoc + hashtag tieu bieu
  gephi_export_summary.json  tom tat (modularity mang tinh, so node/canh tung file)

Chay: py export_gephi.py
"""
import argparse
import colorsys
import itertools
import json
import math
import os
import re
import sys
import time
from collections import Counter, defaultdict
from xml.sax.saxutils import escape, quoteattr

import numpy as np
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
NET_DIR = os.path.join(PROJECT_DIR, "data", "processed", "network")
CEN_FILE = os.path.join(PROJECT_DIR, "data", "processed", "centrality", "centrality_all.csv")
TEMPORAL_FILE = os.path.join(PROJECT_DIR, "data", "processed", "temporal", "video_hashtag_time.csv")
STAGE3_DIR = os.path.join(PROJECT_DIR, "kaggle", "stage3_results", "stage3_output")
OUT_DIR = os.path.join(PROJECT_DIR, "data", "processed", "gephi")

# 20 mau de phan biet (tab20) + mau xam cho "khac"
TAB20 = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd", "#8c564b", "#e377c2", "#17becf",
         "#bcbd22", "#7f7f7f", "#aec7e8", "#ffbb78", "#98df8a", "#ff9896", "#c5b0d5", "#c49c94",
         "#f7b6d2", "#9edae5", "#dbdb8d", "#393b79"]
GRAY = (200, 200, 200)

CENTRALITY_ATTRS = [
    ("video_frequency", "integer"), ("degree", "integer"), ("strength", "double"),
    ("in_lcc", "integer"), ("closeness", "double"), ("harmonic_norm", "double"),
    ("betweenness_norm", "double"), ("eccentricity", "double"), ("stress", "double"),
    ("information", "double"), ("eigenvector", "double"), ("katz", "double"),
    ("pagerank", "double"), ("pagerank_weighted", "double"), ("hits_authority", "double"),
    ("subgraph_log10", "double"), ("functional", "double"), ("leverage", "double"),
    ("kshell", "integer"), ("neighborhood_coreness", "double"),
    ("neighborhood_centrality_degree", "double"), ("triangles", "double"), ("clustering", "double"),
]

_INVALID_XML = re.compile("[^\u0009\u000A\u000D\u0020-\uD7FF\uE000-\uFFFD\U00010000-\U0010FFFF]")


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def color(i):
    """Mau co dinh cho chi so i (0, 1, 2, ...)."""
    if i is None or i < 0:
        return GRAY
    if i < len(TAB20):
        h = TAB20[i].lstrip("#")
        return tuple(int(h[k:k + 2], 16) for k in (0, 2, 4))
    r, g, b = colorsys.hsv_to_rgb((i * 0.618033988749895) % 1.0, 0.65, 0.9)
    return int(r * 255), int(g * 255), int(b * 255)


# --------------------------------------------------------------------------- #
# Ghi GEXF 1.2 (Gephi doc tot nhat)
# --------------------------------------------------------------------------- #
def _attr(s):
    return quoteattr(_INVALID_XML.sub("", str(s)))


def _isnull(v):
    if v is None:
        return True
    try:
        return isinstance(v, (float, np.floating)) and math.isnan(v)
    except TypeError:
        return False


def _fmt(v, typ):
    if typ == "integer":
        return str(int(round(float(v))))
    if typ == "double":
        return f"{float(v):.8g}"
    return str(v)


def write_gexf(path, nodes, edges, node_attrs=(), dyn_node_attrs=(), edge_attrs=(),
               dynamic=False, directed=False, description=""):
    n_nodes = n_edges = 0
    with open(path, "w", encoding="utf-8") as f:
        w = f.write
        w('<?xml version="1.0" encoding="UTF-8"?>\n')
        w('<gexf xmlns="http://www.gexf.net/1.2draft" xmlns:viz="http://www.gexf.net/1.2draft/viz" version="1.2">\n')
        w(f'  <meta><creator>tiktokSNA28 export_gephi.py</creator>'
          f'<description>{escape(description)}</description></meta>\n')
        g = f'defaultedgetype="{"directed" if directed else "undirected"}" mode="{"dynamic" if dynamic else "static"}"'
        if dynamic:
            g += ' timeformat="date"'
        w(f"  <graph {g}>\n")
        for cls, mode, attrs in (("node", "static", node_attrs), ("node", "dynamic", dyn_node_attrs),
                                 ("edge", "static", edge_attrs)):
            if attrs:
                w(f'    <attributes class="{cls}" mode="{mode}">\n')
                for aid, typ in attrs:
                    w(f'      <attribute id="{aid}" title="{aid}" type="{typ}"/>\n')
                w("    </attributes>\n")

        w("    <nodes>\n")
        for nd in nodes:
            n_nodes += 1
            w(f'      <node id="{nd["id"]}" label={_attr(nd["label"])}>\n')
            vals = []
            a = nd.get("attrs", {})
            for aid, typ in node_attrs:
                v = a.get(aid)
                if not _isnull(v):
                    vals.append(f'<attvalue for="{aid}" value={_attr(_fmt(v, typ))}/>')
            d = nd.get("dyn", {})
            for aid, typ in dyn_node_attrs:
                for v, s, e in d.get(aid, []):
                    vals.append(f'<attvalue for="{aid}" value={_attr(_fmt(v, typ))} start="{s}" end="{e}"/>')
            if vals:
                w("        <attvalues>" + "".join(vals) + "</attvalues>\n")
            if nd.get("spells"):
                w("        <spells>" + "".join(f'<spell start="{s}" end="{e}"/>' for s, e in nd["spells"])
                  + "</spells>\n")
            if nd.get("color"):
                r, gg, b = nd["color"]
                w(f'        <viz:color r="{r}" g="{gg}" b="{b}"/>\n')
            if nd.get("size") is not None:
                w(f'        <viz:size value="{nd["size"]:.3f}"/>\n')
            if nd.get("pos") is not None:
                x, y = nd["pos"]
                w(f'        <viz:position x="{x:.2f}" y="{y:.2f}" z="0.0"/>\n')
            w("      </node>\n")
        w("    </nodes>\n    <edges>\n")
        for i, ed in enumerate(edges):
            n_edges += 1
            inner = []
            a = ed.get("attrs", {})
            vals = [f'<attvalue for="{aid}" value={_attr(_fmt(a[aid], typ))}/>'
                    for aid, typ in edge_attrs if not _isnull(a.get(aid))]
            if vals:
                inner.append("<attvalues>" + "".join(vals) + "</attvalues>")
            if ed.get("spells"):
                inner.append("<spells>" + "".join(f'<spell start="{s}" end="{e}"/>' for s, e in ed["spells"])
                             + "</spells>")
            head = (f'      <edge id="e{i}" source="{ed["source"]}" target="{ed["target"]}" '
                    f'weight="{float(ed["weight"]):.6g}"')
            w(head + (">" + "".join(inner) + "</edge>\n" if inner else "/>\n"))
        w("    </edges>\n  </graph>\n</gexf>\n")
    log(f"  -> {os.path.basename(path)}: {n_nodes:,} node, {n_edges:,} canh")
    return n_nodes, n_edges


def read_csv_text(path, text_cols):
    """Doc CSV, giu nguyen cac chuoi nhu 'nan', 'null' (co the la hashtag that)."""
    df = pd.read_csv(path, encoding="utf-8-sig", keep_default_na=False, dtype={c: str for c in text_cols})
    for c in df.columns:
        if c not in text_cols and df[c].dtype == object:
            df[c] = pd.to_numeric(df[c].replace("", np.nan), errors="coerce")
    return df


# --------------------------------------------------------------------------- #
# Phan 1-2: mang tinh
# --------------------------------------------------------------------------- #
def static_leiden(n, src, dst, weight, seeds):
    import igraph as ig
    import leidenalg as la

    g = ig.Graph(n=n, edges=list(zip(src.tolist(), dst.tolist())), directed=False)
    g.es["weight"] = weight.astype(float).tolist()
    best_m, best_q = None, -1.0
    for s in seeds:
        p = la.find_partition(g, la.ModularityVertexPartition, weights="weight", seed=s, n_iterations=-1)
        q = g.modularity(p.membership, weights="weight")
        if q > best_q:
            best_m, best_q = list(p.membership), q
    sizes = Counter(best_m)
    order = {c: i for i, (c, _) in enumerate(sorted(sizes.items(), key=lambda x: (-x[1], x[0])))}
    return np.array([order[c] for c in best_m]), best_q, g.modularity(best_m)


def static_nodes(df, top_label_n):
    top = set(df.nlargest(top_label_n, "pagerank")["matrix_index"])
    nodes = []
    for r in df.to_dict("records"):
        attrs = {k: r.get(k) for k, _ in CENTRALITY_ATTRS}
        attrs.update(hashtag=r["hashtag"], leiden_community=r["leiden_community"],
                     leiden_comm_size=r["leiden_comm_size"],
                     label_top=r["hashtag"] if r["matrix_index"] in top else "")
        nodes.append({"id": f"n{r['matrix_index']}", "label": r["hashtag"], "attrs": attrs})
    return nodes


STATIC_NODE_ATTRS = ([("hashtag", "string"), ("label_top", "string"), ("leiden_community", "integer"),
                      ("leiden_comm_size", "integer")] + CENTRALITY_ATTRS)


def export_static(args, summary):
    log("Doc mang Stage 1 + centrality Stage 2 ...")
    idx = read_csv_text(os.path.join(NET_DIR, "node_index.csv"), ["node_id", "hashtag"])
    cen = read_csv_text(CEN_FILE, ["node_id", "hashtag"]).drop(columns=["node_id", "hashtag"])
    df = idx.merge(cen, on="matrix_index", how="left", validate="one_to_one").sort_values("matrix_index")
    df = df.reset_index(drop=True)
    pos = dict(zip(df["node_id"], df["matrix_index"]))
    edges = read_csv_text(os.path.join(NET_DIR, "edges.csv"), ["source", "target", "relation"])
    edges["s"] = edges["source"].map(pos)
    edges["t"] = edges["target"].map(pos)
    if edges[["s", "t"]].isna().any().any():
        raise SystemExit("edges.csv co endpoint khong co trong node_index.csv")
    edges["s"] = edges["s"].astype(int)
    edges["t"] = edges["t"].astype(int)

    log("Leiden (modularity) tren toan mang tinh ...")
    comm, q_w, q_unw = static_leiden(len(df), edges["s"].to_numpy(), edges["t"].to_numpy(), edges["weight"],
                                     range(args.seeds))
    df["leiden_community"] = comm
    df["leiden_comm_size"] = df["leiden_community"].map(df["leiden_community"].value_counts())
    n_comm = int(df["leiden_community"].nunique())
    log(f"  modularity (co trong so) = {q_w:.4f}, khong trong so = {q_unw:.4f}, so cong dong = {n_comm}")

    rows = []
    for c, grp in df.groupby("leiden_community"):
        grp = grp.sort_values("video_frequency", ascending=False)
        rows.append({"leiden_community": c, "size": len(grp), "total_video_frequency": int(grp["video_frequency"].sum()),
                     "top_hashtags": "|".join(grp["hashtag"].head(15)),
                     "top_by_pagerank": "|".join(grp.sort_values("pagerank", ascending=False)["hashtag"].head(10))})
    pd.DataFrame(rows).to_csv(os.path.join(args.output, "static_communities.csv"), index=False, encoding="utf-8-sig")
    summary["static"] = {"modularity_weighted": q_w, "modularity_unweighted_same_partition": q_unw,
                         "n_communities": n_comm,
                         "n_communities_size_ge_10": int((df["leiden_community"].value_counts() >= 10).sum()),
                         "largest_communities": df["leiden_community"].value_counts().head(10).tolist()}

    # 1. Backbone
    log(f"Ghi backbone: top {args.top_n} hashtag theo degree, canh weight >= {args.min_weight} ...")
    keep = set(df.nlargest(args.top_n, ["degree", "strength"])["matrix_index"])
    eb = edges[edges["s"].isin(keep) & edges["t"].isin(keep) & (edges["weight"] >= args.min_weight)]
    used = set(eb["s"]) | set(eb["t"])
    bdf = df[df["matrix_index"].isin(used)]
    n, m = write_gexf(
        os.path.join(args.output, "1_static_backbone.gexf"), static_nodes(bdf, args.label_top),
        ({"source": f"n{s}", "target": f"n{t}", "weight": wt} for s, t, wt in zip(eb["s"], eb["t"], eb["weight"])),
        node_attrs=STATIC_NODE_ATTRS,
        description=f"Backbone: top {args.top_n} hashtag theo degree, canh weight >= {args.min_weight}")
    summary["files"]["1_static_backbone.gexf"] = {"nodes": n, "edges": m}

    # 2. Full
    if not args.skip_full:
        log("Ghi toan bo mang tinh ...")
        n, m = write_gexf(
            os.path.join(args.output, "2_static_full.gexf"), static_nodes(df, args.label_top),
            ({"source": f"n{s}", "target": f"n{t}", "weight": wt}
             for s, t, wt in zip(edges["s"], edges["t"], edges["weight"])),
            node_attrs=STATIC_NODE_ATTRS, description="Toan bo mang dong xuat hien hashtag (Stage 1)")
        summary["files"]["2_static_full.gexf"] = {"nodes": n, "edges": m}


# --------------------------------------------------------------------------- #
# Phan 3-4: mang dong (Stage 3)
# --------------------------------------------------------------------------- #
def month_bounds(label):
    p = pd.Period(label, freq="M")
    return p.start_time.strftime("%Y-%m-%d"), p.end_time.strftime("%Y-%m-%d")


def merge_spells(month_idx, months):
    """Gop cac thang lien tiep thanh 1 khoang [dau thang dau, cuoi thang cuoi]."""
    out = []
    for _, grp in itertools.groupby(enumerate(sorted(month_idx)), key=lambda x: x[1] - x[0]):
        g = [i for _, i in grp]
        out.append((month_bounds(months[g[0]])[0], month_bounds(months[g[-1]])[1]))
    return out


def export_dynamic(args, summary):
    pfile = os.path.join(args.stage3_dir, "partitions.csv")
    tfile = os.path.join(args.stage3_dir, "community_timeline.csv")
    if not (os.path.exists(pfile) and os.path.exists(tfile)):
        log(f"Bo qua phan dong: khong thay {pfile} hoac {tfile}")
        return
    log(f"Doc ket qua Stage 3 (method = {args.method}) ...")
    parts = read_csv_text(pfile, ["method", "snapshot", "hashtag"])
    parts = parts[parts["method"] == args.method]
    tl = read_csv_text(tfile, ["method", "snapshot", "event", "related", "top_hashtags"])
    tl = tl[tl["method"] == args.method]
    if parts.empty or tl.empty:
        raise SystemExit(f"Khong co ket qua cho method = {args.method}")
    months = sorted(parts["snapshot"].unique())
    m_idx = {m: i for i, m in enumerate(months)}
    life = tl.groupby("dyn_id")["t"].nunique()
    max_size = tl.groupby("dyn_id")["size"].max()
    first_t = tl.groupby("dyn_id")["t"].min()
    # Mau theo thu tu: song lau nhat, lon nhat truoc
    rank = sorted(life.index, key=lambda d: (-life[d], -max_size[d], d))
    dyn_color = {d: color(i) for i, d in enumerate(rank)}

    # 3. Mang dong
    keep_dyn = set(life[life >= args.dyn_min_lifetime].index)
    sel = parts[parts["dyn_id"].isin(keep_dyn)]
    node_set = set(sel["hashtag"])
    pres = parts[parts["hashtag"].isin(node_set)].copy()
    pres["dyn"] = np.where(pres["dyn_id"].isin(keep_dyn), pres["dyn_id"], -1)
    log(f"Mang dong: {len(keep_dyn)} cong dong song >= {args.dyn_min_lifetime} thang, {len(node_set):,} hashtag")

    hid = {h: f"h{i}" for i, h in enumerate(sorted(node_set))}
    nodes = []
    for h, grp in pres.groupby("hashtag"):
        grp = grp.sort_values("snapshot")
        ks = [d for d in grp["dyn"] if d >= 0]
        main = Counter(ks).most_common(1)[0][0] if ks else -1
        dyn_vals = {"community": [], "freq": []}
        for r in grp.itertuples():
            s, e = month_bounds(r.snapshot)
            dyn_vals["community"].append((r.dyn, s, e))
            dyn_vals["freq"].append((r.freq, s, e))
        nodes.append({"id": hid[h], "label": h, "color": dyn_color.get(main, GRAY),
                      "attrs": {"hashtag": h, "main_community": main, "total_freq": int(grp["freq"].sum()),
                                "months_present": len(grp),
                                "main_community_lifetime": int(life.get(main, 0)) if main >= 0 else 0},
                      "dyn": dyn_vals,
                      "spells": merge_spells([m_idx[s] for s in grp["snapshot"]], months)})

    log("  Dem canh dong xuat hien theo thang tu video_hashtag_time.csv ...")
    vids = read_csv_text(TEMPORAL_FILE, ["video_id", "create_date", "hashtags", "source_file"])
    vids["month"] = pd.to_datetime(vids["create_time"], unit="s").dt.to_period("M").astype(str)
    vids = vids[vids["month"].isin(list(m_idx))]
    ew = defaultdict(Counter)
    for month, tags in zip(vids["month"], vids["hashtags"]):
        tags = sorted(set(t for t in tags.split("|") if t in node_set))
        for a, b in itertools.combinations(tags, 2):
            ew[(a, b)][month] += 1

    def dyn_edges():
        for (a, b), cnt in ew.items():
            total = sum(cnt.values())
            if total < args.dyn_min_weight:
                continue
            yield {"source": hid[a], "target": hid[b], "weight": total,
                   "spells": merge_spells([m_idx[mm] for mm in cnt], months)}

    n, m = write_gexf(
        os.path.join(args.output, "3_dynamic_communities.gexf"), nodes, dyn_edges(),
        node_attrs=[("hashtag", "string"), ("main_community", "integer"), ("main_community_lifetime", "integer"),
                    ("total_freq", "integer"), ("months_present", "integer")],
        dyn_node_attrs=[("community", "integer"), ("freq", "integer")], dynamic=True,
        description=f"Mang hashtag dong theo thang {months[0]}..{months[-1]}, cong dong = {args.method} (dyn_id)")
    summary["files"]["3_dynamic_communities.gexf"] = {"nodes": n, "edges": m, "communities": len(keep_dyn),
                                                      "months": months}

    # 4. Do thi tien hoa cong dong
    keep_evo = set(life[life >= args.evo_min_lifetime].index)
    log(f"Do thi tien hoa: {len(keep_evo)} cong dong song >= {args.evo_min_lifetime} thang")
    members = parts[parts["dyn_id"] >= 0].groupby(["snapshot", "dyn_id"])["hashtag"].apply(set).to_dict()
    lanes = sorted(keep_evo, key=lambda d: (-life[d], first_t[d], -max_size[d], d))
    lane = {d: i for i, d in enumerate(lanes)}
    tk = tl[tl["dyn_id"].isin(keep_evo)].sort_values(["dyn_id", "t"])
    appear = defaultdict(list)  # dyn -> [t,...]
    evo_nodes = []
    for r in tk.itertuples():
        appear[r.dyn_id].append(r.t)
        top = r.top_hashtags.split("|")
        evo_nodes.append({
            "id": f"c{r.dyn_id}_t{r.t}", "label": ", ".join(top[:2]),
            "color": dyn_color[r.dyn_id], "size": 4 + 2.5 * math.sqrt(r.size),
            "pos": (r.t * args.x_gap, -lane[r.dyn_id] * args.y_gap),
            "attrs": {"dyn_id": r.dyn_id, "snapshot": r.snapshot, "t": r.t, "size": r.size,
                      "share": r.share, "event": r.event, "lifetime": int(life[r.dyn_id]),
                      "top_hashtags": r.top_hashtags}})

    def shared(t1, d1, t2, d2):
        a = members.get((months[t1], d1), set())
        b = members.get((months[t2], d2), set())
        return max(1, len(a & b))

    def last_before(d, t):
        ts = [x for x in appear.get(d, []) if x < t]
        return max(ts) if ts else None

    evo_edges = []
    for d, ts in appear.items():
        for t1, t2 in zip(ts, ts[1:]):
            evo_edges.append({"source": f"c{d}_t{t1}", "target": f"c{d}_t{t2}", "weight": shared(t1, d, t2, d),
                              "attrs": {"relation": "continue"}})
    for r in tk.itertuples():
        if r.event not in ("split_child", "merge") or not r.related:
            continue
        for p in str(r.related).split("|"):
            p = int(float(p))
            if p not in keep_evo:
                continue
            tp = last_before(p, r.t)
            if tp is None:
                continue
            evo_edges.append({"source": f"c{p}_t{tp}", "target": f"c{r.dyn_id}_t{r.t}",
                              "weight": shared(tp, p, r.t, r.dyn_id),
                              "attrs": {"relation": "split" if r.event == "split_child" else "merge"}})
    n, m = write_gexf(
        os.path.join(args.output, "4_community_evolution.gexf"), evo_nodes, evo_edges,
        node_attrs=[("dyn_id", "integer"), ("snapshot", "string"), ("t", "integer"), ("size", "integer"),
                    ("share", "double"), ("event", "string"), ("lifetime", "integer"), ("top_hashtags", "string")],
        edge_attrs=[("relation", "string")], directed=True,
        description="Tien hoa cong dong: truc x = thang, moi hang = 1 cong dong dong; canh = so hashtag chung")
    summary["files"]["4_community_evolution.gexf"] = {"nodes": n, "edges": m, "communities": len(keep_evo)}

    legend = pd.DataFrame({"dyn_id": lanes, "lane": [lane[d] for d in lanes],
                           "lifetime": [int(life[d]) for d in lanes],
                           "max_size": [int(max_size[d]) for d in lanes],
                           "color": ["#%02x%02x%02x" % dyn_color[d] for d in lanes],
                           "top_hashtags_last": [tl[tl["dyn_id"] == d].sort_values("t")["top_hashtags"].iloc[-1]
                                                 for d in lanes]})
    legend.to_csv(os.path.join(args.output, "dynamic_community_legend.csv"), index=False, encoding="utf-8-sig")


def main():
    ap = argparse.ArgumentParser(description="Stage 4: xuat GEXF cho Gephi")
    ap.add_argument("--output", default=OUT_DIR)
    ap.add_argument("--stage3-dir", default=STAGE3_DIR)
    ap.add_argument("--method", default="leiden_multislice",
                    choices=["louvain", "leiden", "leiden_warm", "leiden_multislice"])
    ap.add_argument("--top-n", type=int, default=1000, help="so hashtag trong backbone (theo degree)")
    ap.add_argument("--min-weight", type=int, default=2, help="trong so canh toi thieu trong backbone")
    ap.add_argument("--label-top", type=int, default=60, help="so hashtag (theo PageRank) co label_top")
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--skip-full", action="store_true", help="khong ghi file toan bo mang (nang)")
    ap.add_argument("--dyn-min-lifetime", type=int, default=3, help="mang dong: chi giu cong dong song >= N thang")
    ap.add_argument("--dyn-min-weight", type=int, default=1)
    ap.add_argument("--evo-min-lifetime", type=int, default=2, help="do thi tien hoa: cong dong song >= N thang")
    ap.add_argument("--x-gap", type=float, default=400.0)
    ap.add_argument("--y-gap", type=float, default=60.0)
    args = ap.parse_args()

    t0 = time.time()
    os.makedirs(args.output, exist_ok=True)
    summary = {"parameters": {k: v for k, v in vars(args).items() if k not in ("output", "stage3_dir")}, "files": {}}
    export_static(args, summary)
    export_dynamic(args, summary)
    with open(os.path.join(args.output, "gephi_export_summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2, default=lambda o: o.item() if hasattr(o, "item") else str(o))
    log(f"Hoan tat sau {time.time() - t0:.0f}s. Ket qua: {args.output}")


if __name__ == "__main__":
    main()
