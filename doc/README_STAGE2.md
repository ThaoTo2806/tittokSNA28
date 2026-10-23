# TikTok Hashtag Co-occurrence SNA — README Stage 2 (Centrality)

## 1. Mục tiêu giai đoạn 2

Tính 17 độ đo centrality đã tổng hợp trong `doc/README (1) (1).md` cùng các chỉ số toàn mạng (density, path length, diameter, clustering coefficient, degree distribution) trên mạng đồng xuất hiện hashtag đã dựng và kiểm định ở Stage 1 (24,869 node, 213,266 cạnh, **vô hướng, có trọng số**).

## 2. Các bước thực hiện

1. **Đọc mạng từ Stage 1:** `adjacency_matrix.npz` (CSR đối xứng), `node_index.csv` (chỉ số hàng/cột → hashtag), `nodes.csv` (tần suất video). Kiểm tra lại ma trận đối xứng và thứ tự chỉ số khớp.
2. **Self-test:** trước mỗi lần chạy, script tính lại toàn bộ độ đo trên đồ thị ví dụ U (8 node) trong README lý thuyết và so với bảng kết quả trong đó. Sai lệch → dừng chương trình.
3. **Phân tích thành phần liên thông:** mạng không liên thông (nhiều thành phần + node cô lập), xác định thành phần liên thông lớn nhất (LCC).
4. **Độ đo cục bộ:** Degree (+ strength có trọng số), K-shell, Neighborhood coreness (và bản mở rộng `+`), Leverage, triangles và clustering coefficient.
5. **Độ đo dựa trên đường đi ngắn nhất:** chạy BFS từ mọi node (theo lô, song song nhiều tiến trình) để có cùng lúc Closeness, Harmonic, Betweenness (Brandes), Stress, Eccentricity, Neighborhood centrality, phân bố độ dài đường đi, diameter, radius, average path length.
6. **Độ đo phổ:** Eigenvector (và HITS) từ vector riêng chính; Subgraph từ các cặp riêng lớn nhất; Katz và Functional từ `(I − αA)⁻¹` (phân rã LU thưa); PageRank bằng lặp lũy thừa (cả bản không trọng số và có trọng số).
7. **Information centrality:** từ nghịch đảo giả của Laplacian (LU thưa trên Laplacian bỏ 1 node), tương đương công thức Stephenson–Zelen.
8. **Tổng hợp:** lưu bảng độ đo cho mọi node, top 20 mỗi độ đo, ma trận tương quan Spearman giữa các độ đo, phân bố bậc và file tóm tắt JSON.

## 3. Quy ước áp dụng cho dữ liệu này

| Vấn đề | Cách xử lý |
|---|---|
| Trọng số cạnh | 17 độ đo tính trên đồ thị **không trọng số** (cấu trúc), đúng như định nghĩa trong README lý thuyết. Trọng số chỉ dùng cho `strength` và `pagerank_weighted`. |
| Đồ thị không liên thông | Closeness, Eccentricity, Information chỉ tính trên **LCC** (node ngoài LCC = trống/NaN). Harmonic, Betweenness, Stress… tính trên toàn đồ thị. |
| Eigenvector / HITS | Đồ thị vô hướng → Hub = Authority = eigenvector (chuẩn hóa tổng = 1). Node ngoài LCC = 0. |
| Katz / Functional | `α = 0.5 / λ₁` (đảm bảo `α < 1/λ₁`); Functional dùng `a_j = α^j` → `[(I − αA)⁻¹]_ii`. |
| Subgraph | Trên LCC xấp xỉ bằng 100 cặp riêng lớn nhất (giá trị rất lớn nên có thêm cột `subgraph_log10`); thành phần nhỏ tính chính xác. Sai số cắt cụt ghi trong `subgraph_truncation_check`. |
| Betweenness / Stress | Mỗi cặp vô hướng `{s,t}` đếm 1 lần; chuẩn hóa chia `(n−1)(n−2)/2`. Có kiểm tra `Σ betweenness = Σ_{cặp} (d − 1)`. |
| Neighborhood centrality | Dạng theo lớp khoảng cách, `n = 2`, `p = 0.5`, với `d` = bậc và `d` = k-shell. |
| PageRank | `d = 0.85`. |

## 4. Cách chạy

Chạy từ thư mục gốc dự án:

```powershell
py -m pip install pandas scipy numpy
py compute_centrality.py --self-test   # chỉ kiểm tra công thức với ví dụ trong README
py compute_centrality.py               # tính toàn bộ và lưu kết quả
```

Tùy chọn:

| Tham số | Mặc định | Ý nghĩa |
|---|---|---|
| `--workers` | `min(6, số CPU − 2)` | Số tiến trình BFS song song. Máy ít RAM: `--workers 2` |
| `--batch` | 64 | Số node nguồn mỗi lô BFS |
| `--alpha-factor` | 0.5 | `α = factor / λ₁` cho Katz/Functional |
| `--damping` | 0.85 | Hệ số PageRank |
| `--nc-radius`, `--nc-p` | 2, 0.5 | Tham số Neighborhood centrality |
| `--subgraph-k` | 100 | Số cặp riêng cho Subgraph trên LCC |
| `--skip-information` | tắt | Bỏ qua Information centrality |

## 5. File đầu ra

Lưu trong `data/processed/centrality/`.

| File | Nội dung |
|---|---|
| `centrality_all.csv` | Mỗi dòng 1 hashtag: `video_frequency`, thành phần liên thông, và toàn bộ độ đo (degree, closeness, harmonic, betweenness, eccentricity, stress, information, eigenvector, katz, pagerank, hits, subgraph, functional, leverage, kshell, neighborhood coreness/centrality, triangles, clustering) |
| `top20_by_measure.csv` | Top 20 hashtag theo từng độ đo |
| `correlation_spearman_lcc.csv` | Tương quan hạng Spearman giữa 19 cột độ đo chính (trên LCC) |
| `degree_distribution.csv` | Phân bố bậc: `degree`, `n_nodes`, `pdf`, `ccdf` (vẽ log-log) |
| `centrality_summary.json` | Chỉ số toàn mạng: density, số thành phần, kích thước LCC, diameter, radius, average path length, phân bố độ dài đường đi, λ₁, α, average clustering, transitivity, số tam giác, các phép kiểm tra và thời gian chạy |

## 6. Kiểm chứng

- Self-test trên đồ thị U: 18/18 cột khớp bảng trong `README (1) (1).md`.
- Đã đối chiếu thêm trên đồ thị ngẫu nhiên không liên thông (Barabási–Albert 300 node + thành phần nhỏ + node cô lập) với `networkx` và đại số tuyến tính dày đặc: Betweenness, Harmonic, PageRank, K-shell, Clustering, Subgraph, Closeness, Eccentricity, Diameter, Average path length, Katz, Functional, Information, Stress đều khớp.

## 7. Kết quả lần chạy hiện tại

Chạy `py compute_centrality.py` (workers = 6), thời gian 499.5 s. Self-test PASS.

| Chỉ số toàn mạng | Kết quả |
|---|---:|
| Số node / số cạnh | 24,869 / 213,266 |
| Density | 0.00069 |
| Số thành phần liên thông | 436 (120 node cô lập; thành phần lớn thứ 2: 30 node) |
| LCC | 23,471 node (94.4%) |
| Diameter (LCC) / Radius (LCC) | 8 / 4 |
| Average path length (LCC) | 3.094 |
| Bậc trung bình / trung vị / lớn nhất | 17.15 / 6 / 5,328 |
| Average clustering (mọi node / bậc ≥ 2) | 0.864 / 0.884 |
| Transitivity (global clustering) | 0.109 |
| Số tam giác | 2,589,721 |
| K-shell lớn nhất | 148 |
| λ₁ (giá trị riêng lớn nhất) | 183.37 → α = 0.5/λ₁ = 0.00273 |

Phân bố độ dài đường đi (cặp có thứ tự trong cùng thành phần): d=2: 81.8M, d=3: 344.8M, d=4: 114.2M, d=5: 9.1M, d≥6: 0.58M → phần lớn cặp hashtag cách nhau 3 bước (tính chất *small-world*: path length ngắn + clustering trung bình cao).

Kiểm tra nội bộ:
- `Σ betweenness = Σ_{cặp}(d − 1)` → sai lệch tương đối 2e-16.
- Subgraph: kết quả với 100 và 50 cặp riêng trùng nhau (λ₁ = 183 áp đảo nên xấp xỉ chính xác).
- Closeness / Eccentricity / Information để trống ở 1,398 node ngoài LCC, đúng như quy ước.

Top 5 hashtag (trích `top20_by_measure.csv`):

| Nhóm độ đo | Top 5 |
|---|---|
| Degree, Strength, Harmonic, Closeness, Information, Katz, Functional, Stress | xuhuong, fyp, viral, trending, xuhuongtiktok (thứ tự thay đổi nhẹ) |
| Betweenness, PageRank | xuhuong, fyp, viral, xuhuongtiktok, vietnam |
| Eigenvector, HITS, Subgraph, Neighborhood coreness+ | fyp, viral, trending, foryou, trend |
| K-shell | game, travel, anime, animeedit, animefyp (nhiều node đồng hạng 148) |

Nhận xét nhanh:
- Các hashtag "chung chung" (xuhuong, fyp, viral) chiếm top hầu hết độ đo → đóng vai trò hub nối các chủ đề.
- Eigenvector/Subgraph ưu tiên cụm hashtag quốc tế (fyp, foryou, trend) vì chúng dính chặt với nhau.
- Betweenness/PageRank đưa `vietnam` vào top → cầu nối giữa các cụm chủ đề trong nước.
- K-shell = 148 do một video có 149 hashtag tạo thành một clique 149 node; giá trị này phản ánh hành vi "nhồi hashtag" hơn là độ trung tâm thật, cần lưu ý khi diễn giải.

## 8. Phạm vi và việc tiếp theo

Stage 2 hoàn tất phần tính và lưu độ đo centrality cùng các chỉ số toàn mạng. **Modularity** (có trong yêu cầu mục 2) cần một phân hoạch cộng đồng nên sẽ tính ở Stage 3 cùng thuật toán phát hiện cộng đồng (Louvain/Leiden). Trực quan hóa (Gephi/NetworkX) và ứng dụng minh họa thuộc các giai đoạn sau.
