# TikTok Hashtag Co-occurrence SNA — README Stage 4 (Trực quan hóa & mô phỏng bằng Gephi)

## 1. Mục tiêu

Biến kết quả 3 giai đoạn trước thành hình ảnh dễ hiểu:

| Hình | Trả lời câu hỏi | Dữ liệu từ |
|---|---|---|
| Mạng hashtag tô màu theo cộng đồng, kích thước theo centrality | Mạng trông như thế nào? Hashtag nào là trung tâm? | Stage 1 + 2 |
| So sánh nhiều độ đo (degree, betweenness, eigenvector...) | Hashtag "nhiều bạn" khác hashtag "cầu nối" ra sao? | Stage 2 |
| **Mô phỏng theo thời gian (Timeline)** | Cộng đồng xuất hiện, lớn lên, biến mất theo tháng như thế nào? | Stage 3 |
| Đồ thị tiến hóa cộng đồng (dạng dòng chảy) | Cộng đồng nào sống lâu, tách/gộp lúc nào? | Stage 3 |

## 2. Bạn cần chạy gì

### Bước 0 — Cài đặt (một lần)

1. Tải **Gephi** bản mới nhất (0.10 trở lên) tại https://gephi.org và cài đặt.
2. **Tăng RAM cho Gephi** (cần cho file mạng đầy đủ): mở `C:\Program Files\Gephi-0.10.x\etc\gephi.conf` bằng Notepad (chạy Notepad với quyền Administrator), tìm `-J-Xmx...` trong dòng `default_options`, sửa thành `-J-Xmx6g`, lưu lại.
3. Thư viện Python (đã cài ở Stage 3, nếu máy khác thì cài lại):

```powershell
py -m pip install pandas numpy igraph leidenalg
```

### Bước 1 — Xuất file cho Gephi (chạy 1 lệnh)

Chạy từ thư mục gốc dự án:

```powershell
py export_gephi.py
```

Script đọc kết quả Stage 1, 2, 3 (bao gồm `kaggle/stage3_results/stage3_output/`) và ghi ra `data/processed/gephi/`:

| File | Nội dung | Dùng cho |
|---|---|---|
| `1_static_backbone.gexf` | "Xương sống" của mạng: 1,000 hashtag có degree cao nhất, chỉ giữ cạnh xuất hiện ≥ 2 video | **Hình chính** — nhẹ, vẽ đẹp |
| `2_static_full.gexf` | Toàn bộ 24,869 hashtag, 213,266 cạnh | Hình tổng quan (nặng) |
| `3_dynamic_communities.gexf` | Mạng **động** theo tháng 01–10/2026, chỉ gồm các cộng đồng sống ≥ 3 tháng (Leiden multislice) | **Mô phỏng Timeline** |
| `4_community_evolution.gexf` | Mỗi node = 1 cộng đồng trong 1 tháng, đã xếp sẵn vị trí: trục ngang = tháng, mỗi hàng = 1 cộng đồng | Hình tiến hóa |
| `static_communities.csv` | Cộng đồng Leiden trên mạng tĩnh: kích thước + hashtag tiêu biểu | Đặt tên cộng đồng khi viết báo cáo |
| `dynamic_community_legend.csv` | Màu + hashtag tiêu biểu của từng cộng đồng động | Chú thích màu cho hình 3, 4 |
| `gephi_export_summary.json` | Modularity của mạng tĩnh, số node/cạnh mỗi file | Ghi vào báo cáo |

Mỗi node trong file 1 và 2 đã có sẵn **tất cả độ đo Stage 2** (degree, betweenness, closeness, eigenvector, pagerank, kshell, clustering...) và cột `leiden_community` (cộng đồng Leiden trên toàn mạng, tính bằng script).

Tùy chọn: `--top-n 1500` (backbone lớn hơn), `--min-weight 3` (thưa hơn), `--skip-full` (bỏ file nặng), `--dyn-min-lifetime 2` (thêm cộng đồng ngắn hạn vào mô phỏng).

---

## 3. Làm trên Gephi — từng bước

> Giao diện Gephi có 3 tab trên cùng: **Overview** (vẽ và chỉnh), **Data Laboratory** (bảng dữ liệu), **Preview** (xuất ảnh đẹp).
> Ở tab Overview: bên trái là **Appearance** (màu/kích thước) và **Layout** (sắp xếp); bên phải là **Filters** và **Statistics**.

### Phần A — Mạng xương sống (hình chính)

**A1. Mở file**
`File → Open → 1_static_backbone.gexf` → hộp thoại Import report: Graph Type = **Undirected**, chọn **New workspace** → OK.

**A2. Tô màu theo cộng đồng**
Appearance → **Nodes** → biểu tượng **bảng màu** → **Partition** → chọn `leiden_community` → **Apply**.
(Mỗi màu = 1 cộng đồng hashtag cùng chủ đề.)

**A3. Kích thước theo độ trung tâm**
Appearance → **Nodes** → biểu tượng **vòng tròn** → **Ranking** → chọn `pagerank` → Min size = 5, Max size = 60 → **Apply**.

**A4. Sắp xếp (layout)**
Layout → chọn **ForceAtlas 2**, đặt:

| Tham số | Giá trị |
|---|---|
| Scaling | 10 |
| Gravity | 1 |
| Dissuade Hubs | ✔ (để các hub như `xuhuong`, `fyp` không đè lên nhau) |
| LinLog mode | ✔ (tách cụm rõ hơn) |
| Edge Weight Influence | 0.5 |
| Prevent Overlap | để trống lúc đầu |

Bấm **Run**, chờ 1–2 phút đến khi hình ổn định → **Stop**. Tích **Prevent Overlap** → Run thêm vài giây → Stop.
Sau đó chọn layout **Label Adjust** → Run → Stop (để nhãn không đè nhau).

**A5. Chỉ hiện nhãn hashtag quan trọng**
Tab **Data Laboratory** → Nodes → nút **Copy data to other column** (dưới bảng) → chọn cột `label_top` → copy sang **Label** → OK.
(Chỉ 60 hashtag có PageRank cao nhất giữ nhãn, còn lại để trống.)

**A6. Xuất ảnh**
Tab **Preview** → Presets: **Default Curved** → chỉnh:
- Node Labels: ✔ Show Labels, Font: **Segoe UI** (hiển thị đúng tiếng Việt/emoji), ✔ Proportional size.
- Edges: Thickness 0.5, ✔ Rescale weight, Opacity 30.

Bấm **Refresh** → **Export** (góc dưới trái) → chọn **PNG** (Options: 4000×4000 px) hoặc **SVG/PDF**.
Lưu thành `fig4_1_backbone_community.png`.

**A7. Thêm hình so sánh centrality** (Stage 2)
Quay lại Overview, chỉ đổi **Size → Ranking** sang độ đo khác → Apply → Preview → Export:

| File ảnh | Size theo | Ý nghĩa |
|---|---|---|
| `fig4_2_degree.png` | `degree` | Hashtag đi kèm với nhiều hashtag khác nhất |
| `fig4_3_betweenness.png` | `betweenness_norm` | Hashtag "cầu nối" giữa các cụm chủ đề (vd. `vietnam`) |
| `fig4_4_eigenvector.png` | `eigenvector` | Hashtag nằm giữa cụm hashtag quan trọng (`fyp`, `foryou`, `trend`) |
| `fig4_5_kshell.png` | Color → Ranking → `kshell` | Lõi dày đặc của mạng |

**A8. Lọc để kể chuyện** (tùy chọn)
Filters → Library:
- **Attributes → Partition → leiden_community**: kéo vào Queries, chọn 1 cộng đồng → **Filter** → chỉ xem 1 chủ đề.
- **Topology → Ego Network**: kéo vào Queries, nhập ID node của `vietnam` (xem trong Data Laboratory), Depth = 1 → **Filter** → hàng xóm trực tiếp của `vietnam`.
Bấm **Filter** lần nữa để tắt lọc.

**A9. Đối chiếu số liệu Stage 2 bằng Gephi** (tùy chọn, để chứng minh dùng công cụ SNA)
Mở `2_static_full.gexf` (Phần B), Statistics → bấm **Run** cạnh: Average Degree, Graph Density, Network Diameter, Avg. Clustering Coefficient, Modularity. So với Stage 2: density 0.00069, diameter 8, average path length 3.09, bậc trung bình 17.15. Gephi có thể cho kết quả hơi khác ở clustering (cách lấy trung bình) và modularity (Louvain ngẫu nhiên).

### Phần B — Toàn bộ mạng (hình tổng quan, tùy chọn)

1. `File → Open → 2_static_full.gexf` → Undirected → New workspace (chờ 1–2 phút).
2. Filters → **Topology → Giant Component** → Filter (bỏ các cụm nhỏ rời rạc, giữ 94.4% node).
3. Color: Partition → `leiden_community`. Size: Ranking → `degree` (Min 2, Max 40).
4. ForceAtlas 2: ✔ **Approximate Repulsion**, Scaling 2, Gravity 1, ✔ Dissuade Hubs, Threads = 8. Run 3–5 phút → Stop.
5. Data Laboratory → copy `label_top` → Label. Preview: Edges Opacity 10, Thickness 0.2 → Export `fig4_6_full_network.png`.

### Phần C — **Mô phỏng tiến hóa cộng đồng theo thời gian** (Timeline)

1. `File → Open → 3_dynamic_communities.gexf` → Undirected → New workspace. Gephi tự nhận đây là mạng động.
2. **Sắp xếp một lần trước khi chạy Timeline**: ForceAtlas 2 (Scaling 10, Gravity 1, ✔ LinLog, ✔ Dissuade Hubs) → Run → Stop → ✔ Prevent Overlap → Run → Stop. Vị trí node giữ cố định trong suốt mô phỏng, nhờ vậy dễ thấy cụm nào xuất hiện/biến mất.
3. Màu **đã được gán sẵn** theo cộng đồng động (`main_community`), cùng màu với file 4. Không cần tô lại.
4. Size: Ranking → `total_freq` (Min 3, Max 40) → Apply.
5. Bật Timeline: menu **Window → Timeline** → thanh Timeline hiện ở dưới → bấm **Enable Timeline**.
6. Kéo hai đầu cửa sổ thời gian cho **rộng đúng 1 tháng** (vd. 2026-01-01 → 2026-01-31).
7. Bấm biểu tượng **bánh răng** trên Timeline → **Play settings**: Delay = 1500 ms, Step = 1 tháng (hoặc 30 ngày), Mode = cửa sổ trượt (one bound/both bounds) → bấm **Play ▶**.
   → Mạng sẽ thay đổi từng tháng: node xuất hiện/biến mất, cụm màu lớn dần (grow), mờ đi (death).
8. (Tùy chọn) Nếu muốn màu đổi theo cộng đồng **từng tháng**: Appearance → Nodes → Color → Partition → `community` → bấm nút **Auto apply** (cạnh Apply). Giá trị `-1` = hashtag không thuộc cộng đồng được theo dõi.
9. **Quay video mô phỏng**: Gephi không xuất video sẵn. Dùng **Win + Alt + R** (Xbox Game Bar có sẵn trên Windows) hoặc OBS để quay màn hình khi Timeline đang Play → lưu `video4_timeline.mp4`.
10. **Ảnh từng tháng** cho báo cáo: đặt cửa sổ Timeline vào 1 tháng → Preview → Refresh → Export. Nên lấy 3 mốc: `fig4_7a_2026-01.png`, `fig4_7b_2026-06.png`, `fig4_7c_2026-10.png`.

### Phần D — Đồ thị tiến hóa cộng đồng (dạng dòng chảy)

1. `File → Open → 4_community_evolution.gexf` → Graph Type **Directed** → New workspace.
2. **KHÔNG chạy Layout**: vị trí đã được xếp sẵn (trục ngang = tháng 01 → 10, mỗi hàng ngang = 1 cộng đồng; hàng trên cùng = cộng đồng sống lâu nhất). Màu và kích thước cũng đã gán sẵn (kích thước ∝ số hashtag).
3. Preview → Presets: **Default Straight** → ✔ Show Labels (Font Segoe UI, cỡ 10) → Edges: ✔ Rescale weight (độ dày = số hashtag chung giữa 2 tháng), Opacity 60 → Refresh → Export `fig4_8_community_evolution.png`.
4. **Cách đọc hình:**

| Thấy trên hình | Nghĩa |
|---|---|
| Hàng ngang kéo dài từ 01 → 10 | Cộng đồng bền vững (12 cộng đồng như vậy) |
| Node to dần theo chiều ngang | **Grow** — cộng đồng mở rộng (vd. cụm `xuhuong`/`viral` từ 79 lên 1,313 hashtag) |
| Hàng bắt đầu ở giữa | **Birth** — cộng đồng mới hình thành |
| Hàng dừng giữa chừng | **Death** — cộng đồng biến mất |
| Cạnh nối chéo giữa 2 hàng | **Merge / Split** (cột `relation` của cạnh) |

Chú thích màu → tên chủ đề: xem `dynamic_community_legend.csv` (cột `top_hashtags_last`).

---

## 4. Danh sách hình/video nên có trong báo cáo

| # | Tên file | Phần |
|---|---|---|
| 1 | `fig4_1_backbone_community.png` — mạng xương sống tô màu cộng đồng, size PageRank | A6 |
| 2–5 | `fig4_2`…`fig4_5` — so sánh degree / betweenness / eigenvector / k-shell | A7 |
| 6 | `fig4_6_full_network.png` — toàn mạng | B |
| 7 | `fig4_7a/b/c` — mạng động tại 01, 06, 10/2026 | C10 |
| 8 | `fig4_8_community_evolution.png` — tiến hóa cộng đồng | D |
| 9 | `video4_timeline.mp4` — mô phỏng Timeline | C9 |

Gợi ý lưu tất cả vào `doc/figures/stage4/`.

## 5. Lỗi thường gặp

| Vấn đề | Cách xử lý |
|---|---|
| Gephi báo hết bộ nhớ / treo khi mở file 2 | Tăng `-J-Xmx6g` (Bước 0), hoặc chạy `py export_gephi.py --skip-full` và chỉ dùng file 1 |
| Nhãn tiếng Việt/emoji hiện ô vuông | Preview → Node Labels → Font chọn **Segoe UI** hoặc **Arial Unicode MS** |
| Hình rối, toàn đường kẻ | Tăng `--min-weight 3` hoặc giảm `--top-n 500` rồi xuất lại; Preview giảm Edge Opacity |
| ForceAtlas 2 chạy mãi không dừng | Bình thường — tự bấm **Stop** khi hình không thay đổi nhiều |
| Timeline không có nút Play | Phải mở đúng file `3_dynamic_communities.gexf` và bấm **Enable Timeline** |
| File 4 bị xáo trộn vị trí | Đã lỡ chạy Layout → mở lại file, không chạy Layout |

## 6. Tiếp theo

Stage 5 — xây dựng ứng dụng minh họa (vd. web app tra cứu hashtag: xem centrality, cộng đồng, lịch sử tiến hóa) dùng các file kết quả Stage 2–4.
