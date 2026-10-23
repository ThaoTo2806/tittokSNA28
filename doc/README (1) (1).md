# Các độ đo Centrality (độ trung tâm) trong mạng

Nguồn chính: Das, Samanta, Pal (2018), *Study on centrality measures in social networks: a survey*, SNAM 8:13.
Mục tiêu: giải thích ngắn gọn cho người mới + công thức + ví dụ tính tay trên đồ thị nhỏ.

**Centrality = "node này quan trọng đến mức nào?"** – mỗi độ đo trả lời bằng một định nghĩa "quan trọng" khác nhau (nhiều bạn, gần mọi người, nằm trên đường đi, bạn của người quan trọng...).

---

## 0. Ký hiệu & đồ thị ví dụ

- `n` = số node, `m` = số cạnh, `A` = ma trận kề (`A_ij = 1` nếu có cạnh i–j), `d(i,j)` = độ dài đường đi ngắn nhất, `σ_st` = số đường đi ngắn nhất s→t, `σ_st(v)` = số đường trong đó đi qua v.

### Đồ thị vô hướng U (8 node, 11 cạnh) – dùng cho hầu hết ví dụ

```
      A
     /|\
    B-+-C---E---F---G---H
     \|/   /
      D---+
```
Cạnh: `A-B, A-C, A-D, B-C, B-D, C-D` (4 node A,B,C,D nối đủ với nhau), `C-E, D-E, E-F, F-G, G-H`.

Bậc: A=3, B=3, C=4, D=4, E=3, F=2, G=2, H=1.

### Đồ thị có hướng D (6 node, 11 cạnh) – dùng cho PageRank, HITS, Katz có hướng

Cạnh `X→Y`: `A→B, A→C, B→C, B→E, C→A, D→A, D→C, D→E, E→C, E→F, F→C`.

> Công cụ kiểm tra: toàn bộ số liệu bên dưới tính bằng Python (`networkx`, `numpy`). Làm tròn 3–4 chữ số.

## Bảng tổng quan: độ đo nào dùng cho đồ thị nào

| # | Độ đo | Nhóm | Vô hướng | Có hướng | Trong paper? |
|---|---|---|:-:|:-:|:-:|
| 1 | Degree | Local | ✅ | ✅ (in/out) | ✅ |
| 2 | Closeness | Path-based | ✅ | ✅ (in/out) | ✅ |
| 3 | Harmonic | Path-based | ✅ | ✅ | ❌ (bạn thêm) |
| 4 | Betweenness | Path-based | ✅ | ✅ | ✅ |
| 5 | Eccentricity | Path-based | ✅ | ✅ (in/out) | ✅ |
| 6 | Stress | Path-based | ✅ | ✅ | ✅ |
| 7 | Information | Path-based (mọi đường) | ✅ | ❌ (gốc chỉ vô hướng) | ✅ |
| 8 | Eigenvector | Spectral | ✅ | ✅ (cần liên thông mạnh) | ✅ |
| 9 | Katz | Spectral | ✅ | ✅ | ✅ |
| 10 | PageRank | Spectral | ✅ | ✅ (thiết kế cho có hướng) | ❌ |
| 11 | HITS | Spectral | ⚠️ (suy biến, hub=authority) | ✅ | ❌ |
| 12 | Subgraph | Spectral (closed walk) | ✅ | ⚠️ (bản gốc vô hướng) | ✅ |
| 13 | Functional | Spectral (closed walk) | ✅ | ⚠️ (bản gốc vô hướng) | ✅ |
| 14 | Leverage | Local-neighbor | ✅ | ❌ (bản gốc vô hướng) | ✅ |
| 15 | K-shell | Core | ✅ | ⚠️ (có biến thể) | ✅ |
| 16 | Neighborhood coreness | Core | ✅ | ❌ | ✅ |
| 17 | Neighborhood centrality | Core/Local | ✅ | ❌ | ✅ |

Paper còn nhắc tên (không có công thức) các nhóm: *Current flow*, *Random process*, *Vitality* (vd. closeness vitality, current-flow betweenness) và bản mở rộng đồ thị có trọng số (Opsahl 2010: strength thay cho degree).

---

# PHẦN 1 – DEGREE (bậc)

## 1. Degree centrality
**Là gì:** đếm số hàng xóm trực tiếp. Nhiều bạn → quan trọng. Chỉ nhìn cục bộ, không biết cấu trúc toàn mạng. Rất nhanh: O(m).

**Công thức:** `C_D(x) = d_x`,  chuẩn hóa `C_D'(x) = d_x / (n−1)`.
**Đồ thị:** vô hướng ✅. Có hướng: tách `in-degree` (số cạnh vào) và `out-degree` (số cạnh ra).

**Ví dụ (U):**

| Node | A | B | C | D | E | F | G | H |
|---|---|---|---|---|---|---|---|---|
| d | 3 | 3 | 4 | 4 | 3 | 2 | 2 | 1 |
| d/7 | 0.429 | 0.429 | 0.571 | 0.571 | 0.429 | 0.286 | 0.286 | 0.143 |

**Ví dụ có hướng (D):**

| Node | A | B | C | D | E | F |
|---|---|---|---|---|---|---|
| in | 2 | 1 | 5 | 0 | 2 | 1 |
| out | 2 | 2 | 1 | 3 | 2 | 1 |

C có in-degree 5: ai cũng trỏ vào C. D có out=3, in=0: chỉ "đi ra".

---

# PHẦN 2 – PATH-BASED (dựa trên đường đi ngắn nhất)

Bảng khoảng cách dùng chung (U). Ví dụ hàng E: d(E,C)=1, d(E,D)=1, d(E,F)=1, d(E,A)=2, d(E,B)=2, d(E,G)=2, d(E,H)=3 → tổng = 12.

| Node | A | B | C | D | E | F | G | H |
|---|---|---|---|---|---|---|---|---|
| Σ d(x,y) | 17 | 17 | 13 | 13 | **12** | 14 | 18 | 24 |

## 2. Closeness centrality
**Là gì:** "gần tất cả mọi người". Tổng khoảng cách càng nhỏ → càng trung tâm. Lỗi: đồ thị không liên thông thì khoảng cách = ∞ → không dùng được (hãy dùng Harmonic).

**Công thức:** `C_C(x) = 1 / Σ_y d(x,y)`,  chuẩn hóa `(n−1) / Σ_y d(x,y)`.
**Đồ thị:** vô hướng ✅; có hướng ✅ (in-closeness: khoảng cách *tới* x; out-closeness: *từ* x), cần liên thông mạnh.

**Ví dụ (U):** E: 7/12 = 0.583 (cao nhất).

| Node | A | B | C | D | E | F | G | H |
|---|---|---|---|---|---|---|---|---|
| C_C (chuẩn hóa) | 0.412 | 0.412 | 0.538 | 0.538 | **0.583** | 0.500 | 0.389 | 0.292 |

→ E ở "giữa" cả đồ thị nên gần mọi nơi nhất, dù bậc của E (3) thấp hơn C, D (4).

## 3. Harmonic centrality *(không có trong paper, bạn yêu cầu)*
**Là gì:** như closeness nhưng cộng **nghịch đảo** khoảng cách: node gần đóng góp nhiều, node không tới được đóng góp 0 (1/∞=0). Nên dùng được cho đồ thị không liên thông.

**Công thức:** `C_H(x) = Σ_{y≠x} 1 / d(x,y)`,  chuẩn hóa chia `(n−1)`.
**Đồ thị:** vô hướng ✅, có hướng ✅.

**Ví dụ (U), tính E:** 1+1+1 (3 hàng xóm) + ½+½+½ (A,B,G) + ⅓ (H) = **4.833**.

| Node | A | B | C | D | E | F | G | H |
|---|---|---|---|---|---|---|---|---|
| C_H | 4.283 | 4.283 | **5.083** | **5.083** | 4.833 | 4.167 | 3.667 | 2.733 |
| /7 | 0.612 | 0.612 | 0.726 | 0.726 | 0.690 | 0.595 | 0.524 | 0.390 |

Lưu ý khác closeness: Harmonic xếp C,D trên E (vì C, D có nhiều node ở khoảng cách 1).

## 4. Betweenness centrality
**Là gì:** node nằm trên nhiều đường đi ngắn nhất giữa các cặp khác → "cầu nối", kiểm soát luồng thông tin. Nếu một cặp có nhiều đường ngắn nhất, chia đều theo tỉ lệ. Tính bằng thuật toán Brandes O(mn).

**Công thức:** `C_B(v) = Σ_{s≠v≠t} σ_st(v) / σ_st`,  chuẩn hóa chia `(n−1)(n−2)/2` (vô hướng).
**Đồ thị:** vô hướng ✅ (mỗi cặp {s,t} tính 1 lần); có hướng ✅ (cặp có thứ tự, chuẩn hóa chia `(n−1)(n−2)`).

**Ví dụ (U), tính tay:**
- **E**: mọi cặp {A,B,C,D} × {F,G,H} (4×3=12 cặp) đều phải qua E → **12**.
- **C**: cặp A–E có 2 đường ngắn nhất (A-C-E, A-D-E), C nằm trên 1 → +½. Cặp {A,B} × {E,F,G,H} = 8 cặp, mỗi cặp 2 đường (qua C hoặc D) → 8 × ½ = **4**.
- **F**: {A,B,C,D,E} × {G,H} = **10**. **G**: {A..F} × {H} = **6**. **H, A, B**: không nằm giữa ai → 0.

| Node | A | B | C | D | E | F | G | H |
|---|---|---|---|---|---|---|---|---|
| C_B | 0 | 0 | 4 | 4 | **12** | 10 | 6 | 0 |
| /21 | 0 | 0 | 0.190 | 0.190 | 0.571 | 0.476 | 0.286 | 0 |

→ E, F là "cầu nối" của cái đuôi E-F-G-H với cụm ABCD.

## 5. Eccentricity centrality
**Là gì:** nhìn vào node *xa nhất* của x. Xa nhất càng gần → càng trung tâm. Nhạy với một node ngoại lai.

**Công thức (theo paper):** `C_EC(x) = 1 / max_y d(x,y)`.
**Đồ thị:** vô hướng ✅; có hướng ✅ (out- hoặc in-eccentricity), cần liên thông.

**Ví dụ (U):** max d: A=5 (đến H), B=5, C=4, D=4, E=3 (đến H), F=3 (đến A,B), G=4, H=5.

| Node | A | B | C | D | E | F | G | H |
|---|---|---|---|---|---|---|---|---|
| max d | 5 | 5 | 4 | 4 | 3 | 3 | 4 | 5 |
| C_EC | 0.200 | 0.200 | 0.250 | 0.250 | **0.333** | **0.333** | 0.250 | 0.200 |

## 6. Stress centrality
**Là gì:** giống betweenness nhưng **đếm số đường ngắn nhất đi qua node** (không chia tỉ lệ). Node càng "chịu tải" nhiều.

**Công thức:** `C_S(v) = Σ_{s≠v≠t} σ_st(v)`. (Paper ghi `s∉N, t∉N` – là lỗi in; đúng là `s ≠ v ≠ t`.)
**Đồ thị:** vô hướng ✅, có hướng ✅.

**Ví dụ (U):** C: các cặp A–E, A–F, A–G, A–H, B–E, ... mỗi cặp có 2 đường, 1 đường qua C → 8 đường.

| Node | A | B | C | D | E | F | G | H |
|---|---|---|---|---|---|---|---|---|
| C_S | 0 | 0 | 8 | 8 | **18** | 14 | 8 | 0 |

(E: 12 cặp, nhưng cặp A-F có 2 đường đều qua E → tổng 18.)

## 7. Information centrality (Stephenson–Zelen)
**Là gì:** giống closeness nhưng xét **mọi đường đi** (không chỉ ngắn nhất), đường dài đóng góp ít hơn; coi mạng như mạch điện. Đồ thị phải liên thông. O(n³).

**Công thức:** `B = (D − A + U)^{-1}` (D = ma trận bậc chéo, U = ma trận toàn 1),
`T = Σ_j B_jj`, `R_k = Σ_j B_kj`, 
`C_I(k) = 1 / ( B_kk + (T − 2R_k)/n )`.
**Đồ thị:** vô hướng ✅ (bản gốc), có hướng ❌.

**Ví dụ (U):** cần nghịch đảo ma trận 8×8 → dùng máy. T = 6.2.

| Node | A | B | C | D | E | F | G | H |
|---|---|---|---|---|---|---|---|---|
| C_I | 0.731 | 0.731 | 0.821 | 0.821 | **0.894** | 0.731 | 0.535 | 0.382 |

(E cao nhất như closeness; F bằng A, B nhờ nó "nằm trên đường" nối đuôi.)

---

# PHẦN 3 – SPECTRAL (dựa trên ma trận kề / giá trị riêng) – "quan trọng nếu bạn bè quan trọng"

## 8. Eigenvector centrality
**Là gì:** điểm của node = tổng điểm hàng xóm (x_i = (1/λ) Σ_j A_ij x_j). Kết bạn với người quan trọng thì mình quan trọng. Lời giải là vector riêng ứng với giá trị riêng lớn nhất λ.

**Công thức:** `A x = λ x`,  `x_i = (1/λ) Σ_j A_ij x_j`.
**Đồ thị:** vô hướng ✅; có hướng ✅ (cần liên thông mạnh; vector trái = điểm theo cạnh *vào*).

**Ví dụ (U):** λ_max = 3.357. Chuẩn hóa max = 1:

| Node | A | B | C | D | E | F | G | H |
|---|---|---|---|---|---|---|---|---|
| x | 0.848 | 0.848 | **1.000** | **1.000** | 0.661 | 0.218 | 0.071 | 0.021 |

Kiểm tra E: (x_C + x_D + x_F)/λ = (1 + 1 + 0.218)/3.357 = 0.661 ✓. Điểm tụt rất nhanh về phía đuôi (E→H).

## 9. Katz centrality
**Là gì:** đếm **tổng số bước đi (walk)** từ mọi node đến node i, bước càng dài càng bị giảm trọng số `α^k`. Là eigenvector "có giảm dần" – khắc phục việc eigenvector cho 0 ở node không có đường vào.

**Công thức:** `C_K(i) = Σ_{k≥1} Σ_j α^k (A^k)_ji` = tổng cột của `(I − αA)^{-1} − I`; yêu cầu `α < 1/λ_max`.
**Đồ thị:** vô hướng ✅, có hướng ✅ (đếm walk *đi vào* i).

**Ví dụ (U):** α = 0.2 (1/λ = 0.298 nên hợp lệ).

| Node | A | B | C | D | E | F | G | H |
|---|---|---|---|---|---|---|---|---|
| C_K | 1.957 | 1.957 | **2.414** | **2.414** | 1.741 | 0.876 | 0.641 | 0.328 |

**Ví dụ có hướng (D):** α = 0.3 (λ_max = 1.534 → 1/λ = 0.652 hợp lệ):

| Node | A | B | C | D | E | F |
|---|---|---|---|---|---|---|
| C_K | 1.358 | 0.707 | **2.526** | 0.000 | 0.812 | 0.544 |

D = 0 vì không có cạnh nào đi vào D.

## 10. PageRank *(không có trong paper, bạn yêu cầu)*
**Là gì:** người "lướt ngẫu nhiên": mỗi bước đi theo 1 cạnh ra ngẫu nhiên, với xác suất (1−d) thì nhảy tới node bất kỳ. PageRank = xác suất đứng ở node đó lâu dài. Được trỏ tới bởi node quan trọng *và ít trỏ đi nơi khác* thì điểm cao. Tổng điểm = 1.

**Công thức:** `PR(i) = (1−d)/n + d · Σ_{j→i} PR(j) / out(j)`,  thường d = 0.85.
**Đồ thị:** có hướng ✅ (thiết kế cho nó); vô hướng ✅ (coi mỗi cạnh là 2 chiều).

**Ví dụ (D)**, khởi tạo 1/6 mỗi node. Một vòng cho C: nhận từ A (out=2), B (out=2), D (out=3), E (out=2), F (out=1):
`0.15/6 + 0.85 × (⅙·½ + ⅙·½ + ⅙·⅓ + ⅙·½ + ⅙·1) = 0.025 + 0.85×0.3889 = 0.4264`. Lặp đến hội tụ:

| Node | A | B | C | D | E | F |
|---|---|---|---|---|---|---|
| PR | 0.3155 | 0.1591 | **0.3334** | 0.0250 | 0.0997 | 0.0674 |

D = 0.15/6 = 0.025 (không ai trỏ vào, chỉ nhận phần "nhảy ngẫu nhiên"). A cao gần bằng C vì được C (chỉ có 1 cạnh ra) "dồn" toàn bộ điểm.

## 11. HITS (Hubs & Authorities) *(không có trong paper, bạn yêu cầu)*
**Là gì:** mỗi node có **2 điểm**: *Authority* = được nhiều *hub tốt* trỏ tới (nguồn nội dung); *Hub* = trỏ tới nhiều *authority tốt* (trang danh mục/tổng hợp). Hai điểm định nghĩa vòng tròn lẫn nhau, lặp đến hội tụ.

**Công thức:** `auth(i) = Σ_{j→i} hub(j)`,  `hub(i) = Σ_{i→j} auth(j)`, sau mỗi vòng chuẩn hóa. Dạng ma trận: `auth ∝ AᵀA·auth`, `hub ∝ AAᵀ·hub`.
**Đồ thị:** có hướng ✅. Vô hướng: Hub = Authority = eigenvector centrality → mất ý nghĩa.

**Ví dụ (D):** bắt đầu hub = 1 cho mọi node.
- Vòng 1: auth = in-degree = (A2, B1, C5, D0, E2, F1). Hub(A) = auth(B)+auth(C) = 1+5 = 6; hub(D) = auth(A)+auth(C)+auth(E) = 2+5+2 = 9...
- Lặp đến hội tụ (chuẩn hóa tổng = 1):

| Node | A | B | C | D | E | F |
|---|---|---|---|---|---|---|
| Authority | 0.148 | 0.081 | **0.461** | 0.000 | 0.229 | 0.081 |
| Hub | 0.168 | 0.214 | 0.046 | **0.260** | 0.168 | 0.143 |

→ C là authority lớn nhất (ai cũng trỏ vào), D là hub lớn nhất (trỏ ra A, C, E mà không ai trỏ vào).

---

# PHẦN 4 – CÁC ĐỘ ĐO CÒN LẠI TRONG PAPER

## 12. Subgraph centrality
**Là gì:** đếm số **closed walk** (đi vòng về chính mình) tại node, walk dài bị giảm trọng số `1/k!`. Node nằm trong nhiều tam giác/vòng nhỏ (cụm chặt) có điểm cao.

**Công thức:** `μ_k(i) = (A^k)_ii`,  `C_SG(i) = Σ_{k≥0} μ_k(i)/k!` = phần tử đường chéo của `e^A`.
**Đồ thị:** vô hướng ✅ (bản gốc).

**Ví dụ (U):** μ_2(i) = bậc; μ_3(i) = 2 × số tam giác chứa i. Vd A nằm trong 3 tam giác (ABC, ABD, ACD) nên μ_3 = 6. E nằm trong 1 tam giác (CDE) → μ_3 = 2. F, G, H không trong tam giác → 0.

| Node | A | B | C | D | E | F | G | H |
|---|---|---|---|---|---|---|---|---|
| μ_2 | 3 | 3 | 4 | 4 | 3 | 2 | 2 | 1 |
| μ_3 | 6 | 6 | 8 | 8 | 2 | 0 | 0 | 0 |
| C_SG | 5.833 | 5.833 | **7.575** | **7.575** | 4.404 | 2.374 | 2.231 | 1.591 |

## 13. Functional centrality
**Là gì:** tổng quát hóa subgraph: tự chọn trọng số `a_j` cho closed walk độ dài j (subgraph là trường hợp a_j = 1/j!). Dùng dò protein "chí mạng" trong mạng tương tác protein.

**Công thức:** `C_F(i) = Σ_{j≥0} a_j μ_j(i)`.
**Đồ thị:** vô hướng ✅ (bản gốc).

**Ví dụ (U):** chọn `a_j = 0.2^j` → `C_F(i) = [(I − 0.2A)^{-1}]_ii`:

| Node | A | B | C | D | E | F | G | H |
|---|---|---|---|---|---|---|---|---|
| C_F | 1.284 | 1.284 | **1.385** | **1.385** | 1.212 | 1.096 | 1.089 | 1.044 |

## 14. Leverage centrality
**Là gì:** so bậc của node với bậc hàng xóm. Dương = node có bậc *cao hơn* hàng xóm trung bình (có "đòn bẩy", ảnh hưởng lên hàng xóm); âm = hàng xóm "to" hơn mình. Giá trị trong khoảng (−1, 1).

**Công thức:** `C_L(i) = (1/k_i) Σ_{j∈N_i} (k_i − k_j) / (k_i + k_j)`.
**Đồ thị:** vô hướng ✅ (bản gốc, mạng não).

**Ví dụ (U), A (k=3; hàng xóm B:3, C:4, D:4):** (1/3)·[0 + (3−4)/7 + (3−4)/7] = **−0.095**.
G (k=2; hàng xóm F:2, H:1): (1/2)·[0 + (2−1)/3] = **+0.167**.

| Node | A | B | C | D | E | F | G | H |
|---|---|---|---|---|---|---|---|---|
| C_L | −0.095 | −0.095 | 0.107 | 0.107 | −0.029 | −0.100 | **0.167** | −0.333 |

(H là lá, mọi hàng xóm đều lớn hơn → thấp nhất.)

## 15. K-shell (k-core decomposition)
**Là gì:** "bóc hành". Lặp: xóa mọi node bậc ≤ 1 (gán shell 1) cho đến khi hết; rồi xóa node bậc ≤ 2 (shell 2)... Node càng ở lõi (k_s cao) càng là "siêu lan truyền" (Kitsak 2010). Nhược điểm: nhiều node cùng điểm, không phân biệt được. O(m).

**Công thức:** không có công thức đóng; điểm = chỉ số shell `k_s(i)`.
**Đồ thị:** vô hướng ✅ (có biến thể có hướng/có trọng số).

**Ví dụ (U) – các bước bóc:**
1. Bậc ≤ 1: H (bậc 1) → xóa, k_s=1. Giờ G bậc 1 → xóa k_s=1; F bậc 1 → xóa k_s=1.
2. Còn A,B,C,D,E. E bậc 2 (C, D) → xóa, k_s = 2.
3. Còn A,B,C,D, mỗi node bậc 3 → k_s = 3.

| Node | A | B | C | D | E | F | G | H |
|---|---|---|---|---|---|---|---|---|
| k_s | 3 | 3 | 3 | 3 | 2 | 1 | 1 | 1 |

## 16. Neighborhood coreness (Bae & Kim 2014)
**Là gì:** cộng k-shell của hàng xóm → "có nhiều bạn đang ở lõi". Phân biệt tốt hơn k-shell thuần. Bản mở rộng cộng thêm một vòng nữa.

**Công thức:** `C_NC(v) = Σ_{w∈N(v)} k_s(w)`,  mở rộng `C_NC+(v) = Σ_{w∈N(v)} C_NC(w)`.
**Đồ thị:** vô hướng ✅.

**Ví dụ (U):** C: hàng xóm A(3)+B(3)+D(3)+E(2) = **11**. E: C(3)+D(3)+F(1) = **7**. A: C_NC+ = C_NC(B)+C_NC(C)+C_NC(D) = 9+11+11 = **31**.

| Node | A | B | C | D | E | F | G | H |
|---|---|---|---|---|---|---|---|---|
| C_NC | 9 | 9 | **11** | **11** | 7 | 3 | 2 | 1 |
| C_NC+ | 31 | 31 | **36** | **36** | 25 | 9 | 4 | 2 |

## 17. Neighborhood centrality (Liu et al. 2015)
**Là gì:** cộng điểm của node và hàng xóm tới `n` bước, hàng xóm càng xa càng giảm trọng số `p^bước`. Điểm gốc `d` có thể là bậc hoặc k-shell. `p` ∈ [0,1] điều chỉnh.

**Công thức (paper):** `C_N(i) = d_i + p Σ_{j∈N(i)} d_j + p² Σ_{k∈N(j)\i} d_k + … + pⁿ Σ …`.
Dưới đây dùng **dạng đơn giản theo lớp khoảng cách** (ví dụ cho dễ tính): `C_N(i) = Σ_{h=0}^{n} p^h Σ_{j: d(i,j)=h} d_j`.
**Đồ thị:** vô hướng ✅.

**Ví dụ (U):** n=2, p=0.5, d = bậc. H: d_H=1; lớp 1 = {G} → 0.5×2 = 1; lớp 2 = {F} → 0.25×2 = 0.5 → **2.50**.
E: 3 + 0.5×(4+4+2) + 0.25×(3+3+2) = 3+5+2 = **10**.

| Node | A | B | C | D | E | F | G | H |
|---|---|---|---|---|---|---|---|---|
| C_N (d=bậc) | 9.25 | 9.25 | **11.00** | **11.00** | 10.00 | 6.75 | 4.25 | 2.50 |
| C_N (d=k_s) | 8.00 | 8.00 | **8.75** | **8.75** | 7.25 | 4.25 | 2.50 | 1.75 |

---

# Tổng hợp xếp hạng trên đồ thị U

| Node | Deg | Close | Harm | Betw | Ecc | Stress | Info | Eigen | Katz | SubG | Func | Lev | Kshell |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| A | 3 | .412 | 4.28 | 0 | .20 | 0 | .731 | .85 | 1.96 | 5.83 | 1.28 | −.10 | 3 |
| B | 3 | .412 | 4.28 | 0 | .20 | 0 | .731 | .85 | 1.96 | 5.83 | 1.28 | −.10 | 3 |
| C | **4** | .538 | **5.08** | 4 | .25 | 8 | .821 | **1** | **2.41** | **7.58** | **1.39** | .11 | 3 |
| D | **4** | .538 | **5.08** | 4 | .25 | 8 | .821 | **1** | **2.41** | **7.58** | **1.39** | .11 | 3 |
| E | 3 | **.583** | 4.83 | **12** | **.33** | **18** | **.894** | .66 | 1.74 | 4.40 | 1.21 | −.03 | 2 |
| F | 2 | .500 | 4.17 | 10 | **.33** | 14 | .731 | .22 | .88 | 2.37 | 1.10 | −.10 | 1 |
| G | 2 | .389 | 3.67 | 6 | .25 | 8 | .535 | .07 | .64 | 2.23 | 1.09 | **.17** | 1 |
| H | 1 | .292 | 2.73 | 0 | .20 | 0 | .382 | .02 | .33 | 1.59 | 1.04 | −.33 | 1 |

**Điều rút ra (cùng một đồ thị, đáp án khác nhau):**
- **C, D** thắng ở các độ đo "bạn bè / cụm chặt" (Degree, Harmonic, Eigenvector, Katz, Subgraph, K-shell).
- **E** thắng ở các độ đo "vị trí/cầu nối" (Closeness, Betweenness, Stress, Eccentricity, Information).
- **A, B** có bậc 3 nhưng Betweenness = 0: có bạn nhưng không nằm giữa ai.

## Chọn độ đo nào?
| Bài toán | Gợi ý |
|---|---|
| Ai có nhiều ảnh hưởng trực tiếp | Degree |
| Truyền thông tin nhanh tới tất cả | Closeness / Harmonic (mạng không liên thông → Harmonic) |
| Tìm "cầu nối", điểm nghẽn, node cần bảo vệ | Betweenness / Stress |
| Ai quan trọng nhờ kết nối với người quan trọng | Eigenvector / Katz / PageRank |
| Web, trích dẫn, mạng có hướng | PageRank, HITS |
| Siêu lan truyền dịch bệnh/tin đồn | K-shell, Neighborhood coreness, Neighborhood centrality |
| Mạng sinh học (protein, gene) | Subgraph, Functional, Degree |

## Lưu ý khi đối chiếu với paper
- Công thức Stress và Betweenness trong paper ghi sai chỉ số tổng (`s∉N`, `y≠z∈N`); đúng là tổng theo mọi cặp `s ≠ v ≠ t`.
- Bảng 2 trong paper ghi Closeness O(n³) còn phần text ghi O(mn); với đồ thị không trọng số, BFS từ mỗi node cho O(mn).
- Công thức Neighborhood centrality trong paper viết dạng lồng nhau khó hiểu; bản trên đã đơn giản hóa theo lớp khoảng cách (cùng tinh thần "xa thì giảm trọng số").
- Harmonic, PageRank, HITS không có trong paper; ví dụ trên tự tính.
