"""
Stage 3 - Phat hien cong dong va phan tich tien hoa cong dong trong mang hashtag DONG.

Cau hoi nghien cuu: cac cong dong hashtag hinh thanh, mo rong, phan tach, hop nhat
hoac bien mat nhu the nao theo thoi gian?

Snapshot: chia video theo createTime (mac dinh theo thang), moi snapshot la mot mang dong
xuat hien hashtag vo huong, trong so = so video (giong Stage 1).

Phuong phap (4):
  louvain            - Louvain doc lap tren tung snapshot (Blondel 2008)          [baseline]
  leiden             - Leiden doc lap tren tung snapshot (Traag 2019)             [baseline SOTA tinh]
  leiden_warm        - Leiden khoi tao bang phan hoach snapshot truoc            [dong, online/nhan qua]
                       (Aynaud & Guillaume 2010 - "static algorithms for evolving networks")
  leiden_multislice  - Leiden toi uu modularity da lop (multislice) co lien ket   [dong, offline]
                       giua cac snapshot voi trong so omega (Mucha et al. 2010)

Theo doi tien hoa: so khop cong dong giua cac snapshot bang Jaccard (Greene et al. 2010),
gan nhan su kien: birth, death, grow, shrink, merge, split, continue.

Che do chay:
  synthetic : TEST - mang dong tong hop co cong dong + su kien da biet (ground truth)
  tune      : TRAIN - chon gamma (resolution) va omega (interslice) tren snapshot train
  run       : EVALUATE - chay 4 phuong phap tren toan bo snapshot, danh gia train/test
  all       : synthetic -> tune -> run
"""
import argparse
import itertools
import json
import os
import random
import sys
import time
from collections import Counter, defaultdict

import igraph as ig
import leidenalg as la
import numpy as np
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ig.set_random_number_generator(random)

METHODS = ["louvain", "leiden", "leiden_warm", "leiden_multislice"]
EVENT_TYPES = ["birth", "death", "merge", "split", "grow", "shrink"]


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def relabel(labels):
    return np.unique(np.asarray(labels), return_inverse=True)[1].ravel().tolist()


# =========================================================================== #
# 1. Snapshot
# =========================================================================== #
def build_graph(tag_lists, weighting="count"):
    freq = Counter()
    pairs = Counter()
    for tags in tag_lists:
        tags = sorted(set(t for t in tags if t))
        freq.update(tags)
        k = len(tags)
        if k < 2:
            continue
        w = 1.0 if weighting == "count" else 1.0 / (k - 1)
        for a, b in itertools.combinations(tags, 2):
            pairs[(a, b)] += w
    names = sorted(freq)
    pos = {n: i for i, n in enumerate(names)}
    g = ig.Graph(n=len(names), edges=[(pos[a], pos[b]) for a, b in pairs], directed=False)
    g.vs["name"] = names
    g.vs["id"] = names
    g.vs["freq"] = [freq[n] for n in names]
    g.es["weight"] = [float(w) for w in pairs.values()]
    return g


def load_snapshots(path, freq="M", start=None, end=None, max_videos=0, seed=0, weighting="count"):
    df = pd.read_csv(path, dtype={"video_id": str}, encoding="utf-8")
    df = df[df["hashtags"].notna()].copy()
    ts = pd.to_datetime(df["create_time"], unit="s")
    mask = pd.Series(True, index=df.index)
    if start:
        mask &= ts >= pd.Timestamp(start)
    if end:
        mask &= ts < pd.Timestamp(end)
    df, ts = df[mask].copy(), ts[mask]
    df["snapshot"] = ts.dt.to_period(freq).astype(str)

    if max_videos and max_videos > 0:
        rng = np.random.default_rng(seed)
        keep = []
        for _, grp in df.groupby("snapshot"):
            idx = grp.index.to_numpy()
            keep.extend(idx if len(idx) <= max_videos else rng.choice(idx, max_videos, replace=False))
        df = df.loc[sorted(keep)]

    labels = sorted(df["snapshot"].unique())
    graphs, info = [], []
    for lab in labels:
        sub = df[df["snapshot"] == lab]
        g = build_graph(sub["hashtags"].str.split("|"), weighting)
        graphs.append(g)
        info.append({"snapshot": lab, "n_videos": len(sub), "n_nodes": g.vcount(), "n_edges": g.ecount(),
                     "total_weight": float(sum(g.es["weight"])) if g.ecount() else 0.0})
    return labels, graphs, pd.DataFrame(info)


# =========================================================================== #
# 2. Phat hien cong dong
# =========================================================================== #
def modularity(g, memb):
    if g.ecount() == 0:
        return np.nan
    return g.modularity(memb, weights="weight")


def nmi(a, b):
    return ig.compare_communities(relabel(a), relabel(b), method="nmi")


def _louvain(g, gamma, seed):
    if g.ecount() == 0:
        return list(range(g.vcount()))
    random.seed(seed)
    return list(g.community_multilevel(weights="weight", resolution=gamma).membership)


def _leiden(g, gamma, seed, init=None):
    if g.ecount() == 0:
        return list(range(g.vcount()))
    p = la.find_partition(g, la.RBConfigurationVertexPartition, weights="weight",
                          resolution_parameter=gamma, seed=seed, n_iterations=-1, initial_membership=init)
    return list(p.membership)


def _pairwise_nmi(runs):
    if len(runs) < 2:
        return np.nan
    return float(np.mean([nmi(a, b) for a, b in itertools.combinations(runs, 2)]))


def _best_of(g, runs):
    qs = [modularity(g, m) for m in runs]
    return runs[int(np.nanargmax(qs))], _pairwise_nmi(runs)


def _warm_init(prev_g, prev_m, g):
    pos = dict(zip(prev_g.vs["name"], prev_m))
    nxt = max(prev_m) + 1 if prev_m else 0
    init = []
    for n in g.vs["name"]:
        if n in pos:
            init.append(pos[n])
        else:
            init.append(nxt)
            nxt += 1
    return relabel(init)


def detect(graphs, method, gamma=1.0, omega=1.0, seeds=(0, 1, 2)):
    """Tra ve (memberships theo snapshot, do on dinh giua cac seed theo snapshot)."""
    T = len(graphs)
    memb = [None] * T
    stab = [np.nan] * T
    if method in ("louvain", "leiden"):
        fn = _louvain if method == "louvain" else _leiden
        for t, g in enumerate(graphs):
            memb[t], stab[t] = _best_of(g, [fn(g, gamma, s) for s in seeds])
    elif method == "leiden_warm":
        for t, g in enumerate(graphs):
            init = None if t == 0 else _warm_init(graphs[t - 1], memb[t - 1], g)
            memb[t], stab[t] = _best_of(g, [_leiden(g, gamma, s, init) for s in seeds])
    elif method == "leiden_multislice":
        runs, quals = [], []
        for s in seeds:
            gs = [g.copy() for g in graphs]
            m, imp = la.find_partition_temporal(
                gs, la.RBConfigurationVertexPartition, interslice_weight=omega,
                vertex_id_attr="id", n_iterations=-1, seed=s, resolution_parameter=gamma)
            runs.append([list(x) for x in m])
            quals.append(imp)
        memb = runs[int(np.argmax(quals))]
        for t in range(T):
            stab[t] = _pairwise_nmi([r[t] for r in runs])
    else:
        raise ValueError(method)
    return memb, stab


# =========================================================================== #
# 3. Danh gia chat luong / on dinh
# =========================================================================== #
def partition_stats(g, memb, min_size):
    m = np.asarray(relabel(memb))
    K = int(m.max()) + 1 if len(m) else 0
    sizes = np.bincount(m, minlength=K)
    out = {"n_communities": int(K), "n_communities_tracked": int((sizes >= min_size).sum()),
           "largest_comm_frac": float(sizes.max() / len(m)) if len(m) else np.nan,
           "nodes_in_tracked_frac": float(sizes[sizes >= min_size].sum() / len(m)) if len(m) else np.nan}
    if g.ecount() == 0:
        return {**out, "modularity": np.nan, "coverage": np.nan, "mean_conductance": np.nan}
    E = np.asarray(g.get_edgelist()).reshape(-1, 2)
    w = np.asarray(g.es["weight"], dtype=float)
    total = w.sum()
    same = m[E[:, 0]] == m[E[:, 1]]
    internal = np.bincount(m[E[same, 0]], weights=w[same], minlength=K)
    vol = np.bincount(m, weights=np.asarray(g.strength(weights="weight")), minlength=K)
    cut = vol - 2 * internal
    denom = np.minimum(vol, 2 * total - vol)
    ok = (sizes >= min_size) & (denom > 0)
    out.update(modularity=modularity(g, m.tolist()), coverage=float(internal.sum() / total),
               mean_conductance=float(np.mean(cut[ok] / denom[ok])) if ok.any() else np.nan)
    return out


def compare_common(g1, m1, g2, m2):
    pos = {n: i for i, n in enumerate(g2.vs["name"])}
    ia, ib = [], []
    for i, n in enumerate(g1.vs["name"]):
        j = pos.get(n)
        if j is not None:
            ia.append(i)
            ib.append(j)
    if len(ia) < 2:
        return np.nan, np.nan, len(ia)
    a = relabel(np.asarray(m1)[ia])
    b = relabel(np.asarray(m2)[ib])
    return (ig.compare_communities(a, b, method="nmi"),
            ig.compare_communities(a, b, method="adjusted_rand"), len(ia))


def predictive_modularity(g_next, g, memb):
    """Modularity cua phan hoach P_t khi ap len snapshot t+1 (tren node chung) - kiem tra 'tuong lai'."""
    pos = dict(zip(g.vs["name"], memb))
    idx = [v.index for v in g_next.vs if v["name"] in pos]
    if len(idx) < 2:
        return np.nan
    sub = g_next.induced_subgraph(idx)
    if sub.ecount() == 0:
        return np.nan
    return sub.modularity(relabel([pos[n] for n in sub.vs["name"]]), weights="weight")


def evaluate_sequence(graphs, memb, stab, labels, min_size, split_idx):
    rows = []
    T = len(graphs)
    for t, g in enumerate(graphs):
        row = {"t": t, "snapshot": labels[t], "split": "train" if t < split_idx else "test",
               "n_nodes": g.vcount(), "n_edges": g.ecount(), **partition_stats(g, memb[t], min_size),
               "seed_stability_nmi": stab[t]}
        if t > 0:
            row["nmi_prev"], row["ari_prev"], row["common_nodes_prev"] = compare_common(
                graphs[t - 1], memb[t - 1], g, memb[t])
        row["pred_modularity_next"] = predictive_modularity(graphs[t + 1], g, memb[t]) if t < T - 1 else np.nan
        rows.append(row)
    return pd.DataFrame(rows)


# =========================================================================== #
# 4. Theo doi tien hoa cong dong (Greene et al. 2010, co mo rong)
# =========================================================================== #
def communities_from(g, memb, min_size):
    groups = defaultdict(list)
    for n, c in zip(g.vs["name"], memb):
        groups[c].append(n)
    comms = [frozenset(v) for v in groups.values() if len(v) >= min_size]
    comms.sort(key=lambda c: (-len(c), min(c)))
    return comms


def track_communities(comm_seq, node_sets, theta=0.3, min_overlap=2, delta=0.25, patience=1,
                      match="persistent"):
    """
    comm_seq[t]  : list cac cong dong (frozenset node) tai snapshot t (da loc theo kich thuoc)
    node_sets[t] : tap node cua snapshot t
    match        : 'persistent' -> Jaccard chi tinh tren node co mat o ca hai snapshot
                   (loai nhieu do hashtag xuat hien/bien mat); 'all' -> Jaccard thuong.
    Kich thuoc so sanh theo ti le |C| / |V_t| de khong bi anh huong boi so video moi snapshot.
    """
    fronts = {}
    active = set()
    next_id = 0
    rows, events = [], []
    for t, comms in enumerate(comm_seq):
        Vt = node_sets[t]
        nV = max(len(Vt), 1)
        inv = defaultdict(list)
        for d in active:
            for v in fronts[d]["nodes"]:
                inv[v].append(d)
        f_in_Vt = {d: len(fronts[d]["nodes"] & Vt) for d in active}
        cs_cache = {}
        cand = []
        for j, C in enumerate(comms):
            inter = Counter()
            for v in C:
                for d in inv.get(v, ()):
                    inter[d] += 1
            for d, k in inter.items():
                if k < min_overlap:
                    continue
                F = fronts[d]
                if match == "persistent":
                    key = (j, F["t"])
                    if key not in cs_cache:
                        cs_cache[key] = len(C & node_sets[F["t"]])
                    union = cs_cache[key] + f_in_Vt[d] - k
                else:
                    union = len(C) + len(F["nodes"]) - k
                J = k / union if union > 0 else 0.0
                if J >= theta:
                    cand.append((J, d, j))
        cand.sort(key=lambda x: (-x[0], x[1], x[2]))

        cont_f, cont_c = {}, {}
        by_c, by_f = defaultdict(list), defaultdict(list)
        for J, d, j in cand:
            by_c[j].append((J, d))
            by_f[d].append((J, j))
            if d not in cont_f and j not in cont_c:
                cont_f[d] = (j, J)
                cont_c[j] = (d, J)
        absorbed = defaultdict(list)
        for d in sorted(active):
            if d not in cont_f and d in by_f:
                absorbed[max(by_f[d])[1]].append(d)
        children = defaultdict(list)
        for j in range(len(comms)):
            if j not in cont_c and j in by_c:
                children[max(by_c[j])[1]].append(j)

        comm_dyn = {}
        for j, C in enumerate(comms):
            share = len(C) / nV
            related, J = [], np.nan
            if j in cont_c:
                d, J = cont_c[j]
                if absorbed.get(j):
                    ev, related = "merge", list(absorbed[j])
                elif children.get(d):
                    ev = "split"
                else:
                    r = share / fronts[d]["share"]
                    ev = "grow" if r >= 1 + delta else ("shrink" if r <= 1 - delta else "continue")
            elif j in by_c:
                J, parent = max(by_c[j])
                d, ev, related = next_id, "split_child", [parent]
                next_id += 1
            else:
                d, ev = next_id, ("initial" if t == 0 else "birth")
                next_id += 1
            comm_dyn[j] = d
            rows.append({"t": t, "comm_idx": j, "dyn_id": d, "size": len(C), "share": share,
                         "event": ev, "jaccard": J, "related": "|".join(map(str, related))})
            if ev in ("birth", "grow", "shrink", "merge"):
                events.append({"t": t, "event": ev, "dyn_id": d, "comm_idx": j, "size": len(C),
                               "related": "|".join(map(str, related))})
        for d, kids in children.items():
            events.append({"t": t, "event": "split", "dyn_id": d, "comm_idx": cont_f[d][0] if d in cont_f else -1,
                           "size": len(comms[cont_f[d][0]]) if d in cont_f else 0,
                           "related": "|".join(str(comm_dyn[c]) for c in kids)})

        for j, C in enumerate(comms):
            d = comm_dyn[j]
            fronts[d] = {"nodes": set(C), "t": t, "share": len(C) / nV, "size": len(C), "comm_idx": j}
            active.add(d)
        for lst in absorbed.values():
            for d in lst:
                active.discard(d)
        for d in sorted(active):
            if t - fronts[d]["t"] > patience:
                events.append({"t": fronts[d]["t"] + 1, "event": "death", "dyn_id": d,
                               "comm_idx": fronts[d]["comm_idx"], "size": fronts[d]["size"],
                               "related": "", "last_seen_t": fronts[d]["t"]})
                active.discard(d)
    ev = pd.DataFrame(events, columns=["t", "event", "dyn_id", "comm_idx", "size", "related", "last_seen_t"])
    return pd.DataFrame(rows), ev


def event_scores(detected, truth):
    det = Counter(zip(detected["event"], detected["t"]))
    tru = Counter(truth)
    tp = sum(min(c, det.get(k, 0)) for k, c in tru.items())
    n_det = sum(det[k] for k in det if k[0] in EVENT_TYPES)
    p = tp / n_det if n_det else 0.0
    r = tp / sum(tru.values()) if tru else 0.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    per_type = {f"recall_{e}": float(np.mean([min(c, det.get(k, 0)) / c for k, c in tru.items() if k[0] == e]))
                for e in EVENT_TYPES if any(k[0] == e for k in tru)}
    return {"event_precision": p, "event_recall": r, "event_f1": f, "n_detected_events": n_det, **per_type}


# =========================================================================== #
# 5. TEST: mang dong tong hop co ground truth
# =========================================================================== #
def synthetic_dynamic_sbm(seed, T=8, k=10, size=50, p_in=0.3, p_out=0.005, presence=0.9):
    """
    SBM dong voi su kien da gieo:
      t=2 merge (0+1) | t=3 split (2) | t=4 death (3) + birth | t=5 grow (4, +60%) | t=6 shrink (5, -50%)
    Moi snapshot moi node co mat voi xac suat `presence` (mo phong hashtag xuat hien/bien mat).
    """
    rng = np.random.default_rng(seed)
    comms = {c: list(range(c * size, (c + 1) * size)) for c in range(k)}
    next_node, next_cid = k * size, k
    truth_events, graphs, truths = [], [], []
    for t in range(T):
        if t == 2:
            comms[0] = comms[0] + comms.pop(1)
            truth_events.append(("merge", t))
        if t == 3:
            a = comms[2]
            comms[2], comms[next_cid] = a[: len(a) // 2], a[len(a) // 2:]
            next_cid += 1
            truth_events.append(("split", t))
        if t == 4:
            comms.pop(3)
            truth_events.append(("death", t))
            comms[next_cid] = list(range(next_node, next_node + size))
            next_node += size
            next_cid += 1
            truth_events.append(("birth", t))
        if t == 5:
            add = int(size * 0.6)
            comms[4] = comms[4] + list(range(next_node, next_node + add))
            next_node += add
            truth_events.append(("grow", t))
        if t == 6:
            comms[5] = comms[5][: size // 2]
            truth_events.append(("shrink", t))
        nodes, lab = [], []
        for c, members in comms.items():
            for v in members:
                if rng.random() < presence:
                    nodes.append(v)
                    lab.append(c)
        lab = np.asarray(lab)
        n = len(nodes)
        iu = np.triu_indices(n, 1)
        P = np.where(lab[iu[0]] == lab[iu[1]], p_in, p_out)
        hit = rng.random(len(P)) < P
        g = ig.Graph(n=n, edges=list(zip(iu[0][hit].tolist(), iu[1][hit].tolist())))
        g.vs["name"] = [str(v) for v in nodes]
        g.vs["id"] = g.vs["name"]
        g.vs["freq"] = [1] * n
        g.es["weight"] = [1.0] * g.ecount()
        graphs.append(g)
        truths.append(lab.tolist())
    return graphs, truths, truth_events


def run_synthetic(args):
    log(f"[TEST] Benchmark tong hop: {args.replicates} lan lap, p_in={args.syn_p_in}, p_out={args.syn_p_out}")
    rows = []
    for rep in range(args.replicates):
        graphs, truths, truth_events = synthetic_dynamic_sbm(
            seed=1000 + rep, p_in=args.syn_p_in, p_out=args.syn_p_out, presence=args.syn_presence)
        node_sets = [set(g.vs["name"]) for g in graphs]
        for method in METHODS:
            t0 = time.time()
            memb, _ = detect(graphs, method, 1.0, args.syn_omega, seeds=list(range(args.seeds)))
            nmi_truth = [nmi(m, tr) for m, tr in zip(memb, truths)]
            nmi_cons = [compare_common(graphs[t - 1], memb[t - 1], graphs[t], memb[t])[0] for t in range(1, len(graphs))]
            comm_seq = [communities_from(g, m, args.min_size) for g, m in zip(graphs, memb)]
            _, ev = track_communities(comm_seq, node_sets, args.theta, args.min_overlap, args.delta,
                                      args.patience, args.match)
            rows.append({"replicate": rep, "method": method, "nmi_truth_mean": float(np.mean(nmi_truth)),
                         "nmi_truth_min": float(np.min(nmi_truth)), "nmi_consecutive_mean": float(np.mean(nmi_cons)),
                         "modularity_mean": float(np.mean([modularity(g, m) for g, m in zip(graphs, memb)])),
                         **event_scores(ev, truth_events), "seconds": round(time.time() - t0, 2)})
            log(f"  rep {rep} {method:18s} NMI_truth={rows[-1]['nmi_truth_mean']:.3f} "
                f"event_F1={rows[-1]['event_f1']:.3f}")
    df = pd.DataFrame(rows)
    os.makedirs(args.output, exist_ok=True)
    df.to_csv(os.path.join(args.output, "synthetic_benchmark.csv"), index=False)
    summ = df.drop(columns="replicate").groupby("method", sort=False).agg(["mean", "std"])
    summ.columns = [f"{a}_{b}" for a, b in summ.columns]
    summ.to_csv(os.path.join(args.output, "synthetic_summary.csv"))
    log(f"[TEST] Da luu synthetic_benchmark.csv, synthetic_summary.csv")
    return df


# =========================================================================== #
# 6. TRAIN: chon gamma / omega tren cac snapshot train
# =========================================================================== #
def _score(ev_df):
    q = ev_df["modularity"].mean()
    qn = ev_df["pred_modularity_next"].mean()
    return q, qn, ev_df["nmi_prev"].mean() if "nmi_prev" in ev_df else np.nan, 0.5 * (q + qn)


def run_tune(args, labels=None, graphs=None):
    if graphs is None:
        labels, graphs, _ = load_snapshots(args.input, args.freq, args.start, args.end,
                                           args.max_videos, args.sample_seed, args.weighting)
    split_idx = max(2, int(round(len(graphs) * args.train_frac)))
    train = graphs[:split_idx]
    log(f"[TRAIN] Tune tren {split_idx} snapshot train: {labels[0]} -> {labels[split_idx - 1]}")
    seeds = list(range(args.seeds))
    rows = []
    for gamma in args.gammas:
        memb, stab = detect(train, "leiden", gamma, None, seeds)
        ev = evaluate_sequence(train, memb, stab, labels, args.min_size, split_idx)
        q, qn, nm, sc = _score(ev)
        rows.append({"method": "leiden", "gamma": gamma, "omega": np.nan, "modularity": q,
                     "pred_modularity_next": qn, "nmi_prev": nm, "score": sc})
        log(f"  leiden gamma={gamma:<5} Q={q:.4f} Q_next={qn:.4f} NMI_prev={nm:.4f} score={sc:.4f}")
    best_gamma = max((r for r in rows), key=lambda r: r["score"])["gamma"]
    for omega in args.omegas:
        memb, stab = detect(train, "leiden_multislice", best_gamma, omega, seeds)
        ev = evaluate_sequence(train, memb, stab, labels, args.min_size, split_idx)
        q, qn, nm, sc = _score(ev)
        rows.append({"method": "leiden_multislice", "gamma": best_gamma, "omega": omega, "modularity": q,
                     "pred_modularity_next": qn, "nmi_prev": nm, "score": sc})
        log(f"  multislice gamma={best_gamma} omega={omega:<5} Q={q:.4f} Q_next={qn:.4f} "
            f"NMI_prev={nm:.4f} score={sc:.4f}")
    df = pd.DataFrame(rows)
    best_omega = float(df[df["method"] == "leiden_multislice"].sort_values("score").iloc[-1]["omega"])
    res = {"gamma": float(best_gamma), "omega": best_omega, "train_snapshots": labels[:split_idx],
           "criterion": "score = 0.5 * (mean modularity_t + mean predictive_modularity_{t->t+1}) tren train"}
    os.makedirs(args.output, exist_ok=True)
    df.to_csv(os.path.join(args.output, "tuning.csv"), index=False)
    with open(os.path.join(args.output, "tuning_result.json"), "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
    log(f"[TRAIN] Chon gamma={best_gamma}, omega={best_omega}")
    return res


# =========================================================================== #
# 7. EVALUATE: chay 4 phuong phap tren toan bo snapshot
# =========================================================================== #
def _top_tags(g, nodes, k=10):
    freq = dict(zip(g.vs["name"], g.vs["freq"]))
    return "|".join(sorted(nodes, key=lambda n: (-freq[n], n))[:k])


def run_evaluate(args, labels=None, graphs=None, info=None):
    if graphs is None:
        labels, graphs, info = load_snapshots(args.input, args.freq, args.start, args.end,
                                              args.max_videos, args.sample_seed, args.weighting)
    gamma, omega = args.gamma, args.omega
    tr_path = os.path.join(args.output, "tuning_result.json")
    if (gamma is None or omega is None) and os.path.exists(tr_path):
        with open(tr_path, encoding="utf-8") as f:
            tr = json.load(f)
        gamma = tr["gamma"] if gamma is None else gamma
        omega = tr["omega"] if omega is None else omega
    gamma = 1.0 if gamma is None else gamma
    omega = 1.0 if omega is None else omega
    split_idx = max(2, int(round(len(graphs) * args.train_frac)))
    info = info.copy()
    info["split"] = ["train" if t < split_idx else "test" for t in range(len(labels))]
    log(f"[EVAL] {len(graphs)} snapshot, gamma={gamma}, omega={omega}, train={split_idx}, "
        f"test={len(graphs) - split_idx}")
    node_sets = [set(g.vs["name"]) for g in graphs]
    seeds = list(range(args.seeds))

    all_metrics, all_events, all_timeline, all_parts, comp = [], [], [], [], []
    for method in METHODS:
        t0 = time.time()
        memb, stab = detect(graphs, method, gamma, omega, seeds)
        secs = time.time() - t0
        ev_df = evaluate_sequence(graphs, memb, stab, labels, args.min_size, split_idx)
        ev_df.insert(0, "method", method)
        all_metrics.append(ev_df)

        comm_seq = [communities_from(g, m, args.min_size) for g, m in zip(graphs, memb)]
        tl, events = track_communities(comm_seq, node_sets, args.theta, args.min_overlap, args.delta,
                                       args.patience, args.match)
        tl["snapshot"] = [labels[t] for t in tl["t"]]
        tl["top_hashtags"] = [_top_tags(graphs[t], comm_seq[t][j]) for t, j in zip(tl["t"], tl["comm_idx"])]
        tl.insert(0, "method", method)
        all_timeline.append(tl)
        if len(events):
            src_t = events["last_seen_t"].fillna(events["t"]).astype(int)
            events["snapshot"] = [labels[min(t, len(labels) - 1)] for t in events["t"]]
            events["top_hashtags"] = [_top_tags(graphs[s], comm_seq[s][j]) if j >= 0 else ""
                                      for s, j in zip(src_t, events["comm_idx"].astype(int))]
        events.insert(0, "method", method)
        all_events.append(events)

        dyn_lookup = {(r.t, r.comm_idx): r.dyn_id for r in tl.itertuples()}
        for t, (g, m) in enumerate(zip(graphs, memb)):
            cidx = {}
            for j, C in enumerate(comm_seq[t]):
                for n in C:
                    cidx[n] = j
            all_parts.append(pd.DataFrame({
                "method": method, "snapshot": labels[t], "hashtag": g.vs["name"], "freq": g.vs["freq"],
                "community": relabel(m),
                "dyn_id": [dyn_lookup.get((t, cidx[n]), -1) if n in cidx else -1 for n in g.vs["name"]]}))

        life = tl.groupby("dyn_id")["t"].nunique()
        for split in ("all", "train", "test"):
            sub = ev_df if split == "all" else ev_df[ev_df["split"] == split]
            evs = events if split == "all" else events[events["t"].map(
                lambda t: "train" if t < split_idx else "test") == split]
            row = {"method": method, "split": split, "n_snapshots": len(sub),
                   "modularity": sub["modularity"].mean(), "coverage": sub["coverage"].mean(),
                   "mean_conductance": sub["mean_conductance"].mean(),
                   "n_communities_tracked": sub["n_communities_tracked"].mean(),
                   "nmi_prev": sub["nmi_prev"].mean(), "ari_prev": sub["ari_prev"].mean(),
                   "pred_modularity_next": sub["pred_modularity_next"].mean(),
                   "seed_stability_nmi": sub["seed_stability_nmi"].mean()}
            for e in EVENT_TYPES:
                row[f"n_{e}"] = int((evs["event"] == e).sum()) if len(evs) else 0
            if split == "all":
                row.update(n_dynamic_communities=int(len(life)), mean_lifetime=float(life.mean()),
                           frac_lifetime_ge3=float((life >= 3).mean()), seconds=round(secs, 1))
            comp.append(row)
        log(f"  {method:18s} Q={ev_df['modularity'].mean():.4f} NMI_prev={ev_df['nmi_prev'].mean():.4f} "
            f"Q_next={ev_df['pred_modularity_next'].mean():.4f} dyn_comms={len(life)} ({secs:.1f}s)")

    os.makedirs(args.output, exist_ok=True)
    info.to_csv(os.path.join(args.output, "snapshots.csv"), index=False)
    pd.concat(all_metrics).to_csv(os.path.join(args.output, "snapshot_metrics.csv"), index=False)
    pd.DataFrame(comp).to_csv(os.path.join(args.output, "method_comparison.csv"), index=False)
    pd.concat(all_events).to_csv(os.path.join(args.output, "events.csv"), index=False, encoding="utf-8-sig")
    pd.concat(all_timeline).to_csv(os.path.join(args.output, "community_timeline.csv"), index=False,
                                   encoding="utf-8-sig")
    pd.concat(all_parts).to_csv(os.path.join(args.output, "partitions.csv"), index=False, encoding="utf-8-sig")
    cfg = {k: v for k, v in vars(args).items() if k != "func"}
    cfg.update(gamma_used=gamma, omega_used=omega, snapshots=labels, split_idx=split_idx,
               versions={"igraph": ig.__version__, "leidenalg": la.version, "pandas": pd.__version__})
    with open(os.path.join(args.output, "run_config.json"), "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2, default=str)
    log(f"[EVAL] Da luu ket qua vao {args.output}")


def run_all(args):
    run_synthetic(args)
    labels, graphs, info = load_snapshots(args.input, args.freq, args.start, args.end,
                                          args.max_videos, args.sample_seed, args.weighting)
    log("Snapshot:\n" + info.to_string(index=False))
    if args.gamma is None or args.omega is None:
        run_tune(args, labels, graphs)
    run_evaluate(args, labels, graphs, info)


# =========================================================================== #
def main():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--input", default=os.path.join("data", "processed", "temporal", "video_hashtag_time.csv"))
    common.add_argument("--output", default=os.path.join("data", "processed", "stage3"))
    common.add_argument("--freq", default="M", choices=["M", "W", "Q"], help="do dai snapshot")
    common.add_argument("--start", default="2026-01-01", help="ngay bat dau (bao gom)")
    common.add_argument("--end", default=None, help="ngay ket thuc (khong bao gom)")
    common.add_argument("--max-videos", type=int, default=0, help=">0: lay mau toi da N video/snapshot")
    common.add_argument("--sample-seed", type=int, default=42)
    common.add_argument("--weighting", default="count", choices=["count", "newman"],
                        help="count: so video; newman: moi video k hashtag dong gop 1/(k-1)")
    common.add_argument("--train-frac", type=float, default=0.7)
    common.add_argument("--seeds", type=int, default=5, help="so seed moi lan chay thuat toan")
    common.add_argument("--gamma", type=float, default=None, help="resolution; mac dinh lay tu tune")
    common.add_argument("--omega", type=float, default=None, help="interslice weight; mac dinh lay tu tune")
    common.add_argument("--gammas", type=float, nargs="+", default=[0.5, 1.0, 1.5, 2.0])
    common.add_argument("--omegas", type=float, nargs="+", default=[0.1, 0.5, 1.0, 2.0, 5.0])
    common.add_argument("--min-size", type=int, default=5, help="kich thuoc toi thieu cong dong duoc theo doi")
    common.add_argument("--theta", type=float, default=0.3, help="nguong Jaccard so khop")
    common.add_argument("--min-overlap", type=int, default=2)
    common.add_argument("--delta", type=float, default=0.25, help="nguong grow/shrink theo ti le kich thuoc")
    common.add_argument("--patience", type=int, default=1, help="so snapshot vang mat cho phep truoc khi 'death'")
    common.add_argument("--match", default="persistent", choices=["persistent", "all"])
    common.add_argument("--replicates", type=int, default=5)
    common.add_argument("--syn-p-in", type=float, default=0.3)
    common.add_argument("--syn-p-out", type=float, default=0.005)
    common.add_argument("--syn-presence", type=float, default=0.9)
    common.add_argument("--syn-omega", type=float, default=1.0)

    ap = argparse.ArgumentParser(description="Stage 3 - dynamic community detection")
    sub = ap.add_subparsers(dest="mode", required=True)
    sub.add_parser("synthetic", parents=[common]).set_defaults(func=run_synthetic)
    sub.add_parser("tune", parents=[common]).set_defaults(func=run_tune)
    sub.add_parser("run", parents=[common]).set_defaults(func=run_evaluate)
    sub.add_parser("all", parents=[common]).set_defaults(func=run_all)
    args = ap.parse_args()
    t0 = time.time()
    args.func(args)
    log(f"Hoan tat sau {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
