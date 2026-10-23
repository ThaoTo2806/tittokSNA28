"""
Stage 2 - Tinh 17 do do centrality tren mang dong xuat hien hashtag (vo huong).

Dau vao  : data/processed/network/{adjacency_matrix.npz, node_index.csv, nodes.csv}
Dau ra   : data/processed/centrality/
             centrality_all.csv, top20_by_measure.csv, correlation_spearman_lcc.csv,
             degree_distribution.csv, centrality_summary.json

Quy uoc:
  * 17 do do trong doc/README (1) (1).md duoc tinh tren do thi KHONG TRONG SO (cau truc).
    Trong so (so video dong xuat hien) chi dung cho cac cot bo sung: strength, pagerank_weighted.
  * Do thi khong lien thong (nhieu thanh phan):
      - Degree, Harmonic, Betweenness, Stress, Katz, PageRank, Functional, Leverage, K-shell,
        Neighborhood coreness / centrality: tinh tren toan do thi.
      - Closeness, Eccentricity, Information: chi tinh tren thanh phan lien thong lon nhat (LCC),
        cac node ngoai LCC de trong (NaN) vi cac do do nay yeu cau do thi lien thong.
      - Eigenvector / HITS: vector rieng chinh nam tren LCC, node ngoai LCC = 0.
      - Subgraph: LCC dung xap xi pho (K cap rieng lon nhat), cac thanh phan nho tinh chinh xac.
  * Chay `py compute_centrality.py --self-test` de doi chieu voi vi du trong README.
"""
import argparse
import json
import math
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd
import scipy.sparse as sp
from scipy.sparse.csgraph import connected_components
from scipy.sparse.linalg import eigsh, splu
from scipy.special import logsumexp

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
DENSE_MAX = 2500  # thanh phan <= DENSE_MAX node: dung eigh day du

MEASURES_MAIN = [
    "degree", "closeness", "harmonic", "betweenness", "eccentricity_centrality", "stress",
    "information", "eigenvector", "katz", "pagerank", "hits_authority", "subgraph",
    "functional", "leverage", "kshell", "neighborhood_coreness", "neighborhood_coreness_plus",
    "neighborhood_centrality_degree", "neighborhood_centrality_kshell",
]
MEASURES_TOP = MEASURES_MAIN + ["strength", "pagerank_weighted"]


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


# --------------------------------------------------------------------------- #
# BFS theo lo (batch) bang nhan ma tran thua: closeness, harmonic, eccentricity,
# betweenness, stress, neighborhood centrality, phan bo do dai duong di.
# --------------------------------------------------------------------------- #
_G = {}


def _init_worker(indptr, indices, n, deg, ks, radius, p):
    A = sp.csr_matrix((np.ones(len(indices)), indices, indptr), shape=(n, n))
    _G["A"] = A
    _G["V"] = np.vstack([deg, ks]).astype(float)
    _G["R"] = radius
    _G["p"] = p


def _bfs_batch(sources):
    A, V, R, p = _G["A"], _G["V"], _G["R"], _G["p"]
    n = A.shape[0]
    b = len(sources)
    cols = np.arange(b)

    sigma = np.zeros((n, b))
    dist = np.full((n, b), -1, dtype=np.int16)
    sigma[sources, cols] = 1.0
    dist[sources, cols] = 0
    frontier = sigma.copy()
    level = 0
    while True:
        nxt = A @ frontier
        new = (nxt > 0) & (dist < 0)
        if not new.any():
            break
        level += 1
        dist[new] = level
        frontier = np.where(new, nxt, 0.0)
        sigma += frontier
    max_level = level

    reached = dist > 0
    sumd = np.where(reached, dist, 0).sum(axis=0)
    cnt = reached.sum(axis=0)
    harm = ((1.0 / np.maximum(dist, 1)) * reached).sum(axis=0)
    ecc = dist.max(axis=0)
    hist = np.bincount(dist[reached])

    nc = np.zeros((2, b))
    for h in range(R + 1):
        nc += (p ** h) * (V @ (dist == h))

    bc = np.zeros(n)
    st = np.zeros(n)
    if max_level >= 2:
        safe_sigma = np.where(sigma > 0, sigma, 1.0)
        delta = np.zeros((n, b))
        theta = np.zeros((n, b))
        for lv in range(max_level, 1, -1):
            at_lv = dist == lv
            coef = np.where(at_lv, (1.0 + delta) / safe_sigma, 0.0)
            thp = np.where(at_lv, 1.0 + theta, 0.0)
            both = A @ np.hstack([coef, thp])
            parent = dist == (lv - 1)
            delta = np.where(parent, sigma * both[:, :b], delta)
            theta = np.where(parent, both[:, b:], theta)
        bc = delta.sum(axis=1)
        st = (sigma * theta).sum(axis=1)

    return dict(src=sources, sumd=sumd, cnt=cnt, harm=harm, ecc=ecc, nc=nc, bc=bc, st=st, hist=hist)


def bfs_pass(Ab, deg, ks, radius, p, workers, batch, verbose=True):
    n = Ab.shape[0]
    log_ = log if verbose else (lambda *_: None)
    sources = np.flatnonzero(deg > 0)
    chunks = np.array_split(sources, max(1, math.ceil(len(sources) / batch)))
    init = (Ab.indptr, Ab.indices, n, deg, ks, radius, p)

    out = dict(
        sumd=np.zeros(n), cnt=np.zeros(n), harm=np.zeros(n), ecc=np.zeros(n),
        nc_deg=np.zeros(n), nc_ks=np.zeros(n), bc=np.zeros(n), st=np.zeros(n),
    )
    hist = np.zeros(1, dtype=np.int64)

    def merge(r):
        nonlocal hist
        s = r["src"]
        out["sumd"][s] = r["sumd"]
        out["cnt"][s] = r["cnt"]
        out["harm"][s] = r["harm"]
        out["ecc"][s] = r["ecc"]
        out["nc_deg"][s] = r["nc"][0]
        out["nc_ks"][s] = r["nc"][1]
        out["bc"] += r["bc"]
        out["st"] += r["st"]
        h = r["hist"]
        if len(h) > len(hist):
            hist = np.pad(hist, (0, len(h) - len(hist)))
        hist[: len(h)] += h

    t0 = time.time()
    if workers <= 1:
        _init_worker(*init)
        for i, c in enumerate(chunks, 1):
            merge(_bfs_batch(c))
            if i % 10 == 0 or i == len(chunks):
                log_(f"  BFS batch {i}/{len(chunks)} ({time.time() - t0:.0f}s)")
    else:
        with ProcessPoolExecutor(max_workers=workers, initializer=_init_worker, initargs=init) as ex:
            for i, r in enumerate(ex.map(_bfs_batch, chunks), 1):
                merge(r)
                if i % 10 == 0 or i == len(chunks):
                    log_(f"  BFS batch {i}/{len(chunks)} ({time.time() - t0:.0f}s)")
    out["bc"] /= 2.0  # moi cap vo huong {s,t} duoc dem 2 lan
    out["st"] /= 2.0
    out["hist"] = hist  # so cap CO THU TU theo khoang cach
    return out


# --------------------------------------------------------------------------- #
# Cac ham phu
# --------------------------------------------------------------------------- #
def core_numbers(Ab):
    """K-shell (core number): boc dan node co bac <= k."""
    n = Ab.shape[0]
    d = np.asarray(Ab.sum(axis=1)).ravel().copy()
    core = np.zeros(n, dtype=np.int64)
    alive = np.ones(n, dtype=bool)
    k = 0
    while alive.any():
        k = max(k, int(d[alive].min()))
        while True:
            rem = alive & (d <= k)
            if not rem.any():
                break
            core[rem] = k
            alive[rem] = False
            d -= Ab @ rem.astype(float)
    return core


def top_eigs(A, k):
    """k cap rieng lon nhat (giam dan)."""
    n = A.shape[0]
    if n <= DENSE_MAX:
        w, v = np.linalg.eigh(A.toarray())
        order = np.argsort(w)[::-1][:k]
        return w[order], v[:, order]
    w, v = eigsh(A.astype(float), k=k, which="LA")
    order = np.argsort(w)[::-1]
    return w[order], v[:, order]


def log_subgraph(w, v):
    """ln( sum_k exp(lambda_k) * u_k(i)^2 ) qua log-sum-exp (tranh tran so)."""
    with np.errstate(divide="ignore"):
        terms = w[None, :] + 2.0 * np.log(np.abs(v))
    return logsumexp(terms, axis=1)


def diag_inverse(M, block=256):
    """Duong cheo cua M^-1 (M doi xung xac dinh duong, thua) bang LU + giai theo lo."""
    M = M.tocsc()
    m = M.shape[0]
    lu = splu(M, permc_spec="MMD_AT_PLUS_A")
    d = np.empty(m)
    for s in range(0, m, block):
        e = min(m, s + block)
        E = np.zeros((m, e - s))
        E[np.arange(s, e), np.arange(e - s)] = 1.0
        d[s:e] = lu.solve(E)[np.arange(s, e), np.arange(e - s)]
    return d, lu


def information_centrality(A):
    """
    Stephenson-Zelen tren do thi lien thong: B = (L + J)^-1, C_I(k) = 1 / (B_kk + (T - 2 R_k)/n).
    Do R_k = 1/n va B = L^+ + J/n^2 nen C_I(k) = 1 / (L^+_kk + tr(L^+)/n).
    L^+ tinh tu nghich dao cua Laplacian "noi dat" (bo 1 node) -> khong can ma tran day du.
    """
    n = A.shape[0]
    deg = np.asarray(A.sum(axis=1)).ravel()
    L = (sp.diags(deg) - A).tocsr()
    r = int(deg.argmax())
    keep = np.r_[0:r, r + 1:n]
    gd, lu = diag_inverse(L[keep][:, keep])
    g1 = lu.solve(np.ones(n - 1))
    Gd = np.zeros(n)
    G1 = np.zeros(n)
    Gd[keep] = gd
    G1[keep] = g1
    lp_diag = Gd - 2.0 * G1 / n + G1.sum() / n ** 2
    trace = lp_diag.sum()
    return 1.0 / (lp_diag + trace / n), trace


def pagerank(A, d=0.85, tol=1e-12, maxit=1000):
    n = A.shape[0]
    s = np.asarray(A.sum(axis=1)).ravel()
    inv = np.divide(1.0, s, out=np.zeros(n), where=s > 0)
    dangling = s == 0
    x = np.full(n, 1.0 / n)
    for _ in range(maxit):
        xn = d * (A @ (x * inv)) + (d * x[dangling].sum() + 1.0 - d) / n
        if np.abs(xn - x).sum() < tol:
            x = xn
            break
        x = xn
    return x / x.sum()


def triangles_per_node(Ab, chunk=512):
    n = Ab.shape[0]
    tri = np.zeros(n)
    for s in range(0, n, chunk):
        e = min(n, s + chunk)
        rows = Ab[s:e]
        tri[s:e] = np.asarray((rows @ Ab).multiply(rows).sum(axis=1)).ravel() / 2.0
    return tri


# --------------------------------------------------------------------------- #
# Tinh toan chinh
# --------------------------------------------------------------------------- #
def compute_all(Aw, alpha=None, alpha_factor=0.5, damping=0.85, radius=2, p=0.5,
                subgraph_k=100, workers=1, batch=64, do_information=True, verbose=True):
    t_start = time.time()
    say = log if verbose else (lambda *_: None)
    Aw = Aw.tocsr().astype(float)
    Ab = Aw.copy()
    Ab.data[:] = 1.0
    n = Ab.shape[0]
    deg = np.asarray(Ab.sum(axis=1)).ravel()
    m = int(deg.sum() // 2)
    summary = {"n_nodes": n, "n_edges": m}

    ncomp, labels = connected_components(Ab, directed=False)
    sizes = np.bincount(labels)
    lcc_label = int(sizes.argmax())
    lcc = np.flatnonzero(labels == lcc_label)
    n_l = len(lcc)
    in_lcc = labels == lcc_label
    summary.update(n_components=int(ncomp), lcc_size=int(n_l), lcc_fraction=n_l / n,
                   n_isolated_nodes=int((deg == 0).sum()),
                   second_largest_component=int(np.sort(sizes)[-2]) if ncomp > 1 else 0)
    say(f"Do thi: n={n}, m={m}, thanh phan={ncomp}, LCC={n_l}")

    res = {"component_id": labels, "in_lcc": in_lcc.astype(int)}

    # 1. Degree / strength
    res["degree"] = deg
    res["degree_norm"] = deg / (n - 1)
    res["strength"] = np.asarray(Aw.sum(axis=1)).ravel()

    # 15. K-shell, 16. Neighborhood coreness, 14. Leverage
    say("K-shell, neighborhood coreness, leverage ...")
    ks = core_numbers(Ab)
    res["kshell"] = ks
    nc1 = Ab @ ks
    res["neighborhood_coreness"] = nc1
    res["neighborhood_coreness_plus"] = Ab @ nc1
    coo = Ab.tocoo()
    ki, kj = deg[coo.row], deg[coo.col]
    lev = np.bincount(coo.row, weights=(ki - kj) / (ki + kj), minlength=n)
    res["leverage"] = np.divide(lev, deg, out=np.zeros(n), where=deg > 0)

    # 2,3,4,5,6,17: BFS theo lo
    say(f"BFS theo lo (workers={workers}, batch={batch}) ...")
    t = time.time()
    bf = bfs_pass(Ab, deg, ks, radius, p, workers, batch, verbose)
    say(f"BFS xong sau {time.time() - t:.0f}s")

    res["harmonic"] = bf["harm"]
    res["harmonic_norm"] = bf["harm"] / (n - 1)
    res["betweenness"] = bf["bc"]
    res["betweenness_norm"] = bf["bc"] / ((n - 1) * (n - 2) / 2.0) if n > 2 else bf["bc"]
    res["stress"] = bf["st"]
    res["neighborhood_centrality_degree"] = bf["nc_deg"]
    res["neighborhood_centrality_kshell"] = bf["nc_ks"]

    clo = np.full(n, np.nan)
    ecc = np.full(n, np.nan)
    ecc_c = np.full(n, np.nan)
    if n_l > 1:
        clo[lcc] = (n_l - 1) / bf["sumd"][lcc]
        ecc[lcc] = bf["ecc"][lcc]
        ecc_c[lcc] = 1.0 / bf["ecc"][lcc]
    res["closeness"], res["eccentricity"], res["eccentricity_centrality"] = clo, ecc, ecc_c

    hist = bf["hist"]
    d_axis = np.arange(len(hist))
    pairs = hist.sum()
    summary["diameter_all_components"] = int(len(hist) - 1)
    summary["avg_path_length_reachable_pairs"] = float((hist * d_axis).sum() / pairs)
    if n_l > 1:
        summary["diameter_lcc"] = int(bf["ecc"][lcc].max())
        summary["radius_lcc"] = int(bf["ecc"][lcc].min())
        summary["avg_path_length_lcc"] = float(bf["sumd"][lcc].sum() / (n_l * (n_l - 1)))
    expected_bc = float((hist * np.maximum(d_axis - 1, 0)).sum() / 2.0)
    summary["betweenness_sum_check"] = {
        "sum_betweenness": float(bf["bc"].sum()),
        "sum_over_pairs_of_(d-1)": expected_bc,
        "relative_diff": float(abs(bf["bc"].sum() - expected_bc) / max(expected_bc, 1.0)),
    }
    summary["path_length_distribution_ordered_pairs"] = {int(d): int(c) for d, c in zip(d_axis[1:], hist[1:])}

    # 8. Eigenvector, 11. HITS (vo huong: hub = authority = vector rieng chinh)
    say("Eigenvector / HITS / Subgraph (cap rieng) ...")
    A_l = Ab[lcc][:, lcc].tocsr()
    k_eig = min(subgraph_k, n_l - 1) if n_l > DENSE_MAX else n_l
    t = time.time()
    w, v = top_eigs(A_l, max(k_eig, 1))
    say(f"  eigsh/eigh: {time.time() - t:.0f}s, lambda_1 = {w[0]:.4f}")
    lam1 = float(w[0])
    x = np.abs(v[:, 0])
    eig = np.zeros(n)
    eig[lcc] = x / x.max()
    res["eigenvector"] = eig
    hits = np.zeros(n)
    hits[lcc] = x / x.sum()
    res["hits_hub"] = hits
    res["hits_authority"] = hits.copy()
    summary["lambda_1"] = lam1
    summary["lambda_k"] = {"k": int(len(w)), "value": float(w[-1])}

    # 12. Subgraph centrality
    lse = np.zeros(n)  # ln(exp(A)_ii); node co lap = e^0 = 1
    lse[lcc] = log_subgraph(w, v)
    if n_l > DENSE_MAX and len(w) >= 4:
        half = len(w) // 2
        lse_half = log_subgraph(w[:half], v[:, :half])
        summary["subgraph_truncation_check"] = {
            "k_used": int(len(w)), "k_half": int(half),
            "max_abs_diff_of_ln_between_k_and_k_half": float(np.abs(lse[lcc] - lse_half).max()),
        }
    summary["subgraph_lcc_method"] = "dense_exact" if n_l <= DENSE_MAX else f"top-{len(w)} eigenpairs"
    for c in range(ncomp):
        if c == lcc_label or sizes[c] < 2:
            continue
        idx = np.flatnonzero(labels == c)
        Ac = Ab[idx][:, idx].tocsr()
        kk = len(idx) if len(idx) <= DENSE_MAX else min(subgraph_k, len(idx) - 1)
        wc, vc = top_eigs(Ac, kk)
        lse[idx] = log_subgraph(wc, vc)
    res["subgraph"] = np.exp(np.minimum(lse, 700.0))
    res["subgraph_log10"] = lse / math.log(10.0)

    # 9. Katz, 13. Functional (a_j = alpha^j)
    if alpha is None:
        alpha = alpha_factor / lam1
    if alpha * lam1 >= 1.0:
        raise ValueError(f"alpha={alpha} khong hop le: can alpha < 1/lambda_1 = {1 / lam1}")
    summary["alpha"] = float(alpha)
    summary["alpha_times_lambda_1"] = float(alpha * lam1)
    say(f"Katz / Functional (alpha = {alpha:.6g}) ...")
    t = time.time()
    M = sp.identity(n, format="csr") - alpha * Ab
    fdiag, lu = diag_inverse(M)
    res["functional"] = fdiag
    res["katz"] = lu.solve(np.ones(n)) - 1.0
    say(f"  xong sau {time.time() - t:.0f}s")

    # 7. Information
    info = np.full(n, np.nan)
    if do_information and n_l > 1:
        say("Information centrality (LCC) ...")
        t = time.time()
        info_l, trace = information_centrality(A_l)
        info[lcc] = info_l
        summary["information_trace_Lplus"] = float(trace)
        say(f"  xong sau {time.time() - t:.0f}s")
    res["information"] = info

    # 10. PageRank
    say("PageRank ...")
    res["pagerank"] = pagerank(Ab, damping)
    res["pagerank_weighted"] = pagerank(Aw, damping)
    summary["pagerank_damping"] = damping

    # Bo sung: clustering coefficient
    say("Triangles / clustering ...")
    tri = triangles_per_node(Ab)
    pairs_k = deg * (deg - 1) / 2.0
    res["triangles"] = tri
    res["clustering"] = np.divide(tri, pairs_k, out=np.zeros(n), where=pairs_k > 0)
    summary["average_clustering_all_nodes"] = float(res["clustering"].mean())
    summary["average_clustering_deg_ge_2"] = float(res["clustering"][deg >= 2].mean()) if (deg >= 2).any() else 0.0
    summary["transitivity"] = float(tri.sum() / pairs_k.sum()) if pairs_k.sum() > 0 else 0.0
    summary["n_triangles"] = int(round(tri.sum() / 3))

    summary["density"] = 2.0 * m / (n * (n - 1)) if n > 1 else 0.0
    summary["degree_mean"] = float(deg.mean())
    summary["degree_median"] = float(np.median(deg))
    summary["degree_max"] = int(deg.max())
    summary["kshell_max"] = int(ks.max())
    summary["neighborhood_centrality_params"] = {"radius": radius, "p": p}
    summary["compute_seconds"] = round(time.time() - t_start, 1)
    return res, summary


# --------------------------------------------------------------------------- #
# Self-test voi vi du do thi U trong README
# --------------------------------------------------------------------------- #
def self_test():
    names = "ABCDEFGH"
    edges = ["AB", "AC", "AD", "BC", "BD", "CD", "CE", "DE", "EF", "FG", "GH"]
    idx = {c: i for i, c in enumerate(names)}
    r = [idx[e[0]] for e in edges] + [idx[e[1]] for e in edges]
    c = [idx[e[1]] for e in edges] + [idx[e[0]] for e in edges]
    A = sp.csr_matrix((np.ones(len(r)), (r, c)), shape=(8, 8))
    res, _ = compute_all(A, alpha=0.2, radius=2, p=0.5, workers=1, batch=4, verbose=False)
    expected = {
        "degree": [3, 3, 4, 4, 3, 2, 2, 1],
        "closeness": [.412, .412, .538, .538, .583, .500, .389, .292],
        "harmonic": [4.283, 4.283, 5.083, 5.083, 4.833, 4.167, 3.667, 2.733],
        "betweenness": [0, 0, 4, 4, 12, 10, 6, 0],
        "eccentricity": [5, 5, 4, 4, 3, 3, 4, 5],
        "eccentricity_centrality": [.200, .200, .250, .250, .333, .333, .250, .200],
        "stress": [0, 0, 8, 8, 18, 14, 8, 0],
        "information": [.731, .731, .821, .821, .894, .731, .535, .382],
        "eigenvector": [.848, .848, 1, 1, .661, .218, .071, .021],
        "katz": [1.957, 1.957, 2.414, 2.414, 1.741, .876, .641, .328],
        "subgraph": [5.833, 5.833, 7.575, 7.575, 4.404, 2.374, 2.231, 1.591],
        "functional": [1.284, 1.284, 1.385, 1.385, 1.212, 1.096, 1.089, 1.044],
        "leverage": [-.095, -.095, .107, .107, -.029, -.100, .167, -.333],
        "kshell": [3, 3, 3, 3, 2, 1, 1, 1],
        "neighborhood_coreness": [9, 9, 11, 11, 7, 3, 2, 1],
        "neighborhood_coreness_plus": [31, 31, 36, 36, 25, 9, 4, 2],
        "neighborhood_centrality_degree": [9.25, 9.25, 11, 11, 10, 6.75, 4.25, 2.5],
        "neighborhood_centrality_kshell": [8, 8, 8.75, 8.75, 7.25, 4.25, 2.5, 1.75],
    }
    ok = True
    for key, exp in expected.items():
        got = np.asarray(res[key], dtype=float)
        good = np.allclose(got, exp, atol=2e-3, rtol=1e-3)
        ok &= good
        print(f"  self-test {key:34s} {'OK' if good else 'FAIL ' + str(np.round(got, 4))}")
    return ok


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser(description="Stage 2: tinh 17 do do centrality")
    ap.add_argument("--input-dir", default=os.path.join(PROJECT_DIR, "data", "processed", "network"))
    ap.add_argument("--output-dir", default=os.path.join(PROJECT_DIR, "data", "processed", "centrality"))
    ap.add_argument("--workers", type=int, default=max(1, min(6, (os.cpu_count() or 2) - 2)))
    ap.add_argument("--batch", type=int, default=64, help="so node nguon moi lo BFS")
    ap.add_argument("--alpha-factor", type=float, default=0.5, help="alpha = factor / lambda_1 (Katz, Functional)")
    ap.add_argument("--damping", type=float, default=0.85, help="he so PageRank")
    ap.add_argument("--nc-radius", type=int, default=2, help="so buoc n cua Neighborhood centrality")
    ap.add_argument("--nc-p", type=float, default=0.5, help="he so giam p cua Neighborhood centrality")
    ap.add_argument("--subgraph-k", type=int, default=100, help="so cap rieng dung cho Subgraph tren LCC")
    ap.add_argument("--skip-information", action="store_true")
    ap.add_argument("--self-test", action="store_true", help="chi chay doi chieu voi vi du README roi thoat")
    args = ap.parse_args()

    log("Self-test (do thi U trong README) ...")
    if not self_test():
        log("Self-test THAT BAI - dung lai.")
        sys.exit(1)
    log("Self-test PASS")
    if args.self_test:
        return

    t0 = time.time()
    os.makedirs(args.output_dir, exist_ok=True)
    Aw = sp.load_npz(os.path.join(args.input_dir, "adjacency_matrix.npz")).tocsr()
    node_index = pd.read_csv(os.path.join(args.input_dir, "node_index.csv"), encoding="utf-8")
    nodes = pd.read_csv(os.path.join(args.input_dir, "nodes.csv"), encoding="utf-8")
    node_index = node_index.sort_values("matrix_index").reset_index(drop=True)
    assert (node_index["matrix_index"].values == np.arange(len(node_index))).all()
    assert Aw.shape[0] == len(node_index)
    assert abs(Aw - Aw.T).sum() == 0, "ma tran ke khong doi xung"
    log(f"Da doc ma tran ke {Aw.shape}, nnz={Aw.nnz}")

    res, summary = compute_all(
        Aw, alpha_factor=args.alpha_factor, damping=args.damping, radius=args.nc_radius, p=args.nc_p,
        subgraph_k=args.subgraph_k, workers=args.workers, batch=args.batch,
        do_information=not args.skip_information,
    )

    base = node_index[["matrix_index", "node_id", "hashtag"]].merge(
        nodes[["node_id", "video_frequency"]], on="node_id", how="left")
    df = pd.concat([base, pd.DataFrame(res)], axis=1)
    cols = (["matrix_index", "node_id", "hashtag", "video_frequency", "component_id", "in_lcc",
             "degree", "degree_norm", "strength", "closeness", "harmonic", "harmonic_norm",
             "betweenness", "betweenness_norm", "eccentricity", "eccentricity_centrality", "stress",
             "information", "eigenvector", "katz", "pagerank", "pagerank_weighted",
             "hits_hub", "hits_authority", "subgraph", "subgraph_log10", "functional", "leverage",
             "kshell", "neighborhood_coreness", "neighborhood_coreness_plus",
             "neighborhood_centrality_degree", "neighborhood_centrality_kshell",
             "triangles", "clustering"])
    df = df[cols]
    df.to_csv(os.path.join(args.output_dir, "centrality_all.csv"), index=False, encoding="utf-8-sig")

    # Top 20 moi do do
    tops = []
    for mname in MEASURES_TOP:
        sub = df[["node_id", "hashtag", "video_frequency", mname]].dropna(subset=[mname])
        sub = sub.sort_values([mname, "video_frequency"], ascending=[False, False]).head(20)
        for rank, (_, row) in enumerate(sub.iterrows(), 1):
            tops.append({"measure": mname, "rank": rank, "node_id": row["node_id"],
                         "hashtag": row["hashtag"], "value": row[mname]})
    pd.DataFrame(tops).to_csv(os.path.join(args.output_dir, "top20_by_measure.csv"),
                              index=False, encoding="utf-8-sig")

    # Tuong quan Spearman giua cac do do (tren LCC, noi moi do do deu xac dinh)
    lcc_df = df[df["in_lcc"] == 1]
    corr = lcc_df[MEASURES_MAIN].corr(method="spearman")
    corr.to_csv(os.path.join(args.output_dir, "correlation_spearman_lcc.csv"), encoding="utf-8-sig")

    # Phan bo bac
    vc = df["degree"].astype(int).value_counts().sort_index()
    dd = pd.DataFrame({"degree": vc.index, "n_nodes": vc.values})
    dd["pdf"] = dd["n_nodes"] / dd["n_nodes"].sum()
    dd["ccdf"] = dd["n_nodes"][::-1].cumsum()[::-1] / dd["n_nodes"].sum()
    dd.to_csv(os.path.join(args.output_dir, "degree_distribution.csv"), index=False)

    summary["parameters"] = {k: v for k, v in vars(args).items() if k not in ("input_dir", "output_dir")}
    summary["notes"] = [
        "17 do do tinh tren do thi vo huong khong trong so; strength/pagerank_weighted dung trong so.",
        "Closeness, Eccentricity, Information chi tinh tren LCC (NaN ngoai LCC).",
        "Eigenvector/HITS: hub = authority (vo huong); node ngoai LCC = 0.",
        "Subgraph tren LCC la xap xi top-K cap rieng; xem subgraph_truncation_check.",
        "Betweenness/Stress: moi cap vo huong dem 1 lan (da chia 2).",
    ]
    summary["total_seconds"] = round(time.time() - t0, 1)
    with open(os.path.join(args.output_dir, "centrality_summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2, default=lambda o: o.item() if hasattr(o, "item") else str(o))

    log(f"Hoan tat sau {summary['total_seconds']}s. Ket qua: {args.output_dir}")


if __name__ == "__main__":
    main()
