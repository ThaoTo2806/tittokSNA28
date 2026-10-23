# TikTok Hashtag Co-occurrence SNA — README Stage 3 (Dynamic Community Detection)

## 1. Mục tiêu giai đoạn 3

**Hướng:** Dynamic Network Analysis — phân tích sự tiến hóa và phát hiện cộng đồng trong mạng xã hội động.

**Câu hỏi nghiên cứu:** các cộng đồng hashtag **hình thành, mở rộng, phân tách, hợp nhất hoặc biến mất** như thế nào theo thời gian?

**Phương pháp:**
- Phát hiện cộng đồng **độc lập trên từng thời điểm** bằng Louvain và Leiden (baseline).
- Phát hiện cộng đồng **động có xét tính liên tục theo thời gian**: Leiden khởi tạo từ snapshot trước (warm-start) và Leiden multislice (Mucha et al. 2010).
- Theo dõi cộng đồng giữa các snapshot và gán nhãn sự kiện (Greene et al. 2010).

## 2. Dữ liệu và snapshot

- Đầu vào: `data/processed/temporal/video_hashtag_time.csv` (tạo bằng `prepare_stage3_data.py`) = `video_hashtag_mapping.csv` của Stage 1 (hashtag đã chuẩn hóa giống mạng Stage 1) ghép với `createTime` trong `cleaned_data.csv`. 20,198 video có hashtag, 100% có thời gian đăng.
- Snapshot: **theo tháng, 01/2026 → 10/2026 (10 snapshot)**; mỗi snapshot là mạng đồng xuất hiện hashtag vô hướng, trọng số = số video (cùng định nghĩa Stage 1). Dữ liệu trước 2026 thưa nên không dùng.
- Chia **train = 7 tháng đầu (01–07)**, **test = 3 tháng cuối (08–10)**.

| Snapshot | Video | Node | Cạnh | Tập |
|---|---:|---:|---:|---|
| 2026-01 | 469 | 1,128 | 4,094 | train |
| 2026-02 | 396 | 955 | 3,171 | train |
| 2026-03 | 464 | 1,182 | 4,008 | train |
| 2026-04 | 655 | 1,502 | 4,751 | train |
| 2026-05 | 581 | 1,340 | 4,712 | train |
| 2026-06 | 752 | 1,686 | 6,629 | train |
| 2026-07 | 1,235 | 2,388 | 8,701 | train |
| 2026-08 | 1,357 | 2,545 | 10,070 | test |
| 2026-09 | 2,198 | 4,156 | 29,145 | test |
| 2026-10 | 5,593 | 6,427 | 39,101 | test |

## 3. Các bước thực hiện

1. **Chuẩn bị dữ liệu (local):** `py prepare_stage3_data.py`.
2. **Dựng snapshot** theo tháng từ `createTime`.
3. **Phát hiện cộng đồng** bằng 4 phương pháp (mỗi phương pháp chạy 5 seed, giữ kết quả modularity cao nhất):

   | Phương pháp | Loại | Mô tả |
   |---|---|---|
   | `louvain` | Tĩnh, độc lập | Louvain (Blondel 2008) trên từng snapshot |
   | `leiden` | Tĩnh, độc lập | Leiden (Traag 2019), RB-Configuration (≡ modularity khi γ = 1) |
   | `leiden_warm` | Động, online | Leiden khởi tạo bằng phân hoạch snapshot trước (Aynaud & Guillaume 2010) — chỉ dùng quá khứ |
   | `leiden_multislice` | Động, offline | Tối ưu modularity đa lớp: mỗi tháng là một lớp, cùng hashtag ở 2 tháng liền nhau được nối bằng trọng số ω (Mucha et al. 2010) |

4. **TRAIN — chọn tham số trên 7 snapshot train:** lưới γ ∈ {0.5, 1, 1.5, 2} cho Leiden, sau đó ω ∈ {0.1, 0.5, 1, 2, 5} cho multislice. Tiêu chí: `score = ½·(modularity_t + predictive modularity_{t→t+1})`.
5. **Theo dõi tiến hóa:** chỉ theo dõi cộng đồng ≥ 5 hashtag; so khớp cộng đồng giữa các snapshot bằng Jaccard ≥ 0.3, chỉ tính trên các hashtag có mặt ở cả hai snapshot (loại nhiễu do hashtag xuất hiện/biến mất), cho phép vắng mặt 1 snapshot trước khi kết luận "death". Nhãn sự kiện:

   | Sự kiện | Điều kiện |
   |---|---|
   | birth | cộng đồng mới không khớp cộng đồng nào trước đó |
   | death | cộng đồng không còn khớp sau > 1 snapshot |
   | grow / shrink | tỉ lệ kích thước (\|C\| / số node snapshot) tăng ≥ 25% / giảm ≥ 25% |
   | merge | ≥ 2 cộng đồng cũ cùng khớp vào 1 cộng đồng mới |
   | split | 1 cộng đồng cũ khớp với ≥ 2 cộng đồng mới |

6. **EVALUATE — chạy 4 phương pháp trên toàn bộ 10 snapshot** và đánh giá riêng train/test.
7. **Kiểm tra độ nhạy:** chạy lại với tối đa 450 video/tháng (cân bằng cỡ mẫu) để loại trừ ảnh hưởng của việc dữ liệu crawl dồn về các tháng gần đây.

### Độ đo đánh giá

| Độ đo | Ý nghĩa |
|---|---|
| Modularity Q | Chất lượng phân hoạch trong từng snapshot |
| Coverage, Conductance | Tỉ lệ trọng số nằm trong cộng đồng / mức "rò rỉ" ra ngoài của cộng đồng |
| NMI_prev, ARI_prev | Độ ổn định: so phân hoạch tháng t với t−1 trên các hashtag chung |
| Predictive modularity (Q_next) | **Kiểm tra trên tương lai:** áp phân hoạch tháng t lên mạng tháng t+1 |
| Seed stability | NMI trung bình giữa các lần chạy với seed khác nhau |
| Lifetime | Số snapshot mà một cộng đồng động tồn tại |

## 4. Kết quả

### 4.1. TRAIN — chọn tham số

| Phương pháp | γ | ω | Q | Q_next | NMI_prev | score |
|---|---:|---:|---:|---:|---:|---:|
| leiden | 0.5 | – | 0.7205 | 0.4049 | 0.4993 | 0.5627 |
| **leiden** | **1.0** | – | **0.7433** | 0.4128 | 0.5826 | **0.5781** |
| leiden | 1.5 | – | 0.7399 | 0.3996 | 0.6309 | 0.5697 |
| leiden | 2.0 | – | 0.7341 | 0.3950 | 0.6629 | 0.5645 |
| multislice | 1.0 | 0.1 | 0.7428 | 0.4042 | 0.5873 | 0.5735 |
| multislice | 1.0 | 0.5 | 0.7418 | 0.4245 | 0.6312 | 0.5831 |
| multislice | 1.0 | 1.0 | 0.7383 | 0.4291 | 0.6718 | 0.5837 |
| multislice | 1.0 | 2.0 | 0.7304 | 0.4414 | 0.7656 | 0.5859 |
| **multislice** | 1.0 | **5.0** | 0.7065 | **0.4729** | **0.9327** | **0.5897** |

→ Chọn **γ = 1.0, ω = 5.0**. Khi ω tăng, Q giảm nhẹ nhưng độ ổn định (NMI) và khả năng dự báo tháng sau (Q_next) tăng mạnh.

### 4.2. EVALUATE — so sánh 4 phương pháp (toàn bộ 10 snapshot, γ = 1, ω = 5)

| Độ đo | louvain | leiden | leiden_warm | leiden_multislice |
|---|---:|---:|---:|---:|
| Modularity Q | 0.734 | **0.736** | 0.735 | 0.700 |
| Coverage | 0.831 | 0.832 | **0.835** | 0.808 |
| Conductance (↓) | 0.068 | **0.065** | 0.065 | 0.103 |
| Số cộng đồng (≥ 5 node)/snapshot | 59.6 | 59.4 | 60.0 | 49.3 |
| NMI_prev | 0.547 | 0.557 | 0.566 | **0.917** |
| ARI_prev | 0.240 | 0.250 | 0.270 | **0.870** |
| Q_next | 0.414 | 0.422 | 0.416 | **0.477** |
| Seed stability (NMI) | 0.888 | 0.907 | **0.932** | 0.833 |
| Số cộng đồng động | 486 | 486 | 484 | 281 |
| Lifetime trung bình (snapshot) | 1.23 | 1.22 | 1.24 | **1.75** |
| % sống ≥ 3 snapshot | 4.9% | 4.5% | 5.6% | **11.4%** |
| birth / death | 441 / 305 | 442 / 305 | 439 / 301 | 242 / 145 |
| merge / split | 7 / 0 | 6 / 1 | 7 / 2 | 3 / 0 |
| grow / shrink | 38 / 31 | 27 / 33 | 33 / 27 | 59 / 53 |
| Thời gian chạy (Kaggle CPU) | 0.6 s | 29 s | 34 s | 409 s |

**Trên tập test (08–10/2026):**

| | louvain | leiden | leiden_warm | leiden_multislice |
|---|---:|---:|---:|---:|
| Q | 0.716 | **0.719** | 0.718 | 0.697 |
| NMI_prev | 0.487 | 0.507 | 0.515 | **0.911** |
| Q_next | 0.451 | 0.464 | 0.449 | **0.511** |

### 4.3. Kiểm tra độ nhạy — cân bằng 450 video/tháng

| Độ đo | louvain | leiden | leiden_warm | leiden_multislice |
|---|---:|---:|---:|---:|
| Q | 0.727 | **0.728** | 0.727 | 0.690 |
| NMI_prev | 0.581 | 0.581 | 0.576 | **0.925** |
| Q_next | 0.382 | 0.380 | 0.381 | **0.450** |
| Lifetime trung bình | 1.36 | 1.33 | 1.30 | **2.13** |

→ Xếp hạng các phương pháp **không đổi** khi cân bằng cỡ mẫu, nên kết luận không do việc tháng 10 có nhiều video hơn.

### 4.4. Nhận xét so sánh phương pháp

- **Louvain ≈ Leiden** về Q (0.73–0.74). Leiden ổn định giữa các seed hơn (0.907 so với 0.888).
- **Phương pháp tĩnh không phù hợp để theo dõi tiến hóa:** phân hoạch giữa 2 tháng liền nhau chỉ giống nhau ở mức NMI ≈ 0.55, ARI ≈ 0.25. Hệ quả là khoảng 440 lần "birth" và 305 lần "death", lifetime trung bình chỉ 1.2 tháng. Phần lớn các sự kiện này là nhiễu do thuật toán, không phải thay đổi thật.
- **Warm-start gần như không cải thiện** (NMI 0.566 so với 0.557): Leiden nhanh chóng rời khỏi phân hoạch khởi tạo khi tối ưu modularity.
- **Multislice tốt nhất cho câu hỏi nghiên cứu:**
  - Hy sinh khoảng 0.036 modularity nhưng NMI_prev ≈ 0.92 và ARI ≈ 0.87.
  - Q_next cao nhất cả trên train lẫn test: phân hoạch tháng t giải thích mạng tháng t+1 tốt nhất.
  - Lifetime dài gấp khoảng 1.4 lần.
  - Nhược điểm: chạy offline (dùng cả dữ liệu tương lai), chậm hơn, kém ổn định giữa các seed (0.83).

### 4.5. Tiến hóa cộng đồng (leiden_multislice)

**12 cộng đồng tồn tại suốt 10 tháng** (lõi chủ đề ổn định). Số hashtag mỗi tháng từ 01 → 10:

| dyn_id | Chủ đề (hashtag đặc trưng) | Kích thước 01 → 10 | Diễn biến |
|---|---|---|---|
| 3 | Xu hướng chung + âm nhạc: `xuhuong`, `viral`, `capcut`, `qdndvn`, `nhachaymoingay` | 79 → 1,313 | Mở rộng liên tục, thành cộng đồng lớn nhất ("hub" xu hướng) |
| 5 | Giáo dục → lịch sử: `hoccungtiktok`, `lichsuvietnam` → `anhhunglietsi`, `congvienlethirieng` | 66 → 568 | Mở rộng, trọng tâm chuyển từ học tập sang lịch sử/anh hùng liệt sĩ |
| 6 | Ẩm thực/mukbang: `mukbang`, `asmr`, `ancungtiktok` (+ `beautyqueen`, `glowup` cuối kỳ) | 53 → 426 | Mở rộng, cuối kỳ gắn thêm nhóm làm đẹp |
| 17 | Thương hiệu Mixue: `mixuevietnam`, `mixue` (+ `lienquanmobile`) | 10 → 155 | Mở rộng mạnh, cuối kỳ nối với game Liên Quân |
| 4 | Du lịch: `vietnam`, `saigon`, `dalat`, `travel` → `dulichdalat`, `reviewdalat` | 77 → 160 | Ổn định, chuyên biệt dần về Đà Lạt |
| 7 | Tài chính – doanh nghiệp: `fpt`, `chungkhoan`, `cophieu`, `vingroup`, `vinfast` | 53 → 103 | Ổn định |
| 2 | `tiktoknews`, `learnontiktok` → `games`, `gaming`, `roblox` | 89 → 159 | Trôi chủ đề (topic drift) — cần thận trọng khi diễn giải |
| 0 | `xuhuong`, `runningman` → `reviewphim`, `phimhay` | 143 → 243 | Thu hẹp giữa kỳ rồi mở rộng lại với chủ đề review phim |

**Sự kiện nổi bật:**

| Sự kiện | Tháng | Cộng đồng |
|---|---|---|
| grow | 10/2026 | Xu hướng chung (`xuhuong`, `viral`, `capcut`) → 1,313 hashtag |
| grow | 10/2026 | Show giải trí: `2ngay1dem`, `datvietvac`, `hieuthuhai`, `toiyeutoquoctoi` → 343 |
| shrink | 10/2026 | Game/anime (`game`, `anime`, `freefire`) và game quốc tế (`gaming`, `roblox`) |
| merge | 04/2026 | Viettel 5G/gói cước hợp nhất (`viettel`, `5gviettel`, `simviettel`) |
| birth | 03/2026 | Tôn Hoa Sen (`tonhoasen`, `maiamgiadinhviet`); Viettel 4G/5G khuyến mãi |
| birth | 06/2026 | Quân sự – thời sự quốc tế (`quansu`, `camphuchia`, `chientranh`) |
| birth | 08/2026 | Cụm nước ngoài: tin giải trí Pakistan, gaming quốc tế |
| death | 02/2026 | 2 Days 1 Night Hàn Quốc / K-pop (`2d1n`, `kpop`) |
| death | 06/2026 | Thể thao – bóng đá (`thethao`, `bongda`, `u17vietnam`) |

Với `leiden_warm`, tháng 09–10 có nhiều "birth"/"death" của cộng đồng lớn (vd. `anhhunglietsi` 571 node, `2ngay1dem` 326 node xuất hiện tháng 10; cụm `xuhuong` + `tintuc` 274 node "chết" tháng 09). Đây là dấu hiệu phân hoạch tĩnh bị tổ chức lại khi mạng lớn lên, không hẳn là sự kiện thật — multislice ghi nhận các cụm này là **cộng đồng cũ mở rộng**.

### 4.6. Trả lời câu hỏi nghiên cứu

1. **Hình thành:** cộng đồng mới xuất hiện liên tục (242 lần birth với multislice) nhưng **phần lớn nhỏ và ngắn hạn**: 241/281 cộng đồng động chỉ sống 1 tháng. Đó thường là cụm hashtag của một chiến dịch/video lan truyền (khuyến mãi Viettel, Tôn Hoa Sen, tin nước ngoài).
2. **Mở rộng:** tập trung ở **lõi khoảng 12 cộng đồng chủ đề bền vững** (xu hướng chung, lịch sử – giáo dục, ẩm thực, du lịch, tài chính, giải trí). Chúng tồn tại suốt 10 tháng và lớn mạnh nhất ở 08–10/2026. Cộng đồng xu hướng chung `xuhuong`/`viral` đóng vai trò hub, khớp với kết quả centrality Stage 2.
3. **Phân tách / hợp nhất:** **hiếm** (multislice: 3 merge, 0 split; các phương pháp khác ≤ 7 merge, ≤ 2 split). Tiến hóa chủ yếu diễn ra qua **birth/death của cụm nhỏ và grow/shrink của cụm lõi**, không phải tách/gộp.
4. **Biến mất:** chủ yếu là cụm sự kiện ngắn hạn (show Hàn Quốc, thể thao theo giải đấu).
5. **Trôi chủ đề:** một số cộng đồng sống lâu thay đổi hashtag đặc trưng theo thời gian (giáo dục → lịch sử, tin tức → game). Đây là dạng tiến hóa mà các nhãn sự kiện cổ điển không thể hiện.

## 5. Cách chạy lại

```powershell
# Local: tạo file đầu vào
py prepare_stage3_data.py
```

Trên Kaggle (Internet = On, CPU là đủ — igraph/leidenalg không dùng GPU): upload `video_hashtag_time.csv` + `stage3_dynamic_communities.py` thành Dataset, chạy notebook `kaggle/stage3_kaggle.ipynb` (bản đã chạy: `kaggle/notebookd3f05351fa.ipynb`):

```bash
pip install igraph leidenalg
python stage3_dynamic_communities.py tune --input video_hashtag_time.csv --output stage3_output
python stage3_dynamic_communities.py run  --input video_hashtag_time.csv --output stage3_output
python stage3_dynamic_communities.py run  --input video_hashtag_time.csv --output stage3_output_balanced --max-videos 450 --gamma 1.0 --omega 5.0
```

Tham số chính: `--freq M|W|Q`, `--start 2026-01-01`, `--train-frac 0.7`, `--seeds 5`, `--gammas`, `--omegas`, `--min-size 5`, `--theta 0.3`, `--patience 1`, `--match persistent|all`, `--weighting count|newman`, `--max-videos`. Chế độ `synthetic` (benchmark tổng hợp có ground truth) có trong script nhưng không chạy ở lần này.

## 6. File đầu ra

Kết quả chính: `kaggle/stage3_results/stage3_output/`; bản cân bằng: `kaggle/stage3_results_balanced/stage3_output_balanced/`.

| File | Nội dung |
|---|---|
| `tuning.csv`, `tuning_result.json` | Lưới tham số và γ, ω được chọn |
| `snapshots.csv` | Số video/node/cạnh mỗi snapshot, train/test |
| `snapshot_metrics.csv` | Độ đo theo (phương pháp × snapshot) |
| `method_comparison.csv` | Tổng hợp theo phương pháp × (all/train/test) |
| `events.csv` | Sự kiện birth/death/grow/shrink/merge/split kèm top hashtag |
| `community_timeline.csv` | Mỗi cộng đồng tại mỗi snapshot: `dyn_id`, kích thước, sự kiện, Jaccard, top hashtag |
| `partitions.csv` | Hashtag → cộng đồng → `dyn_id` theo snapshot (dùng cho trực quan hóa Stage 4) |
| `fig_metrics_over_time.png`, `fig_events.png` | Biểu đồ độ đo theo thời gian và số sự kiện |
| `run_config.json` | Tham số và phiên bản thư viện (igraph 1.0.0, leidenalg 0.12.0) |

## 7. Hạn chế

- **Lệch do crawl:** số video tăng mạnh về cuối kỳ (tháng 10 gấp khoảng 12 lần tháng 1), nên grow/birth ở 09–10 một phần do cỡ mẫu. Kiểm tra cân bằng cho cùng xếp hạng phương pháp, nhưng số liệu sự kiện tuyệt đối vẫn nên diễn giải thận trọng.
- **ω = 5 nằm ở biên lưới tìm kiếm:** score vẫn tăng theo ω, nên có thể mở rộng lưới (vd. `--omegas 5 10 20`) để xác nhận.
- **Multislice là offline:** phân hoạch tháng t có dùng thông tin tháng sau, nên không áp dụng được theo thời gian thực. Nếu cần online, phải dùng warm-start, chấp nhận kém ổn định.
- **Trôi chủ đề** trong các cộng đồng sống lâu: một phần do ω lớn "kéo" nhãn cộng đồng qua thời gian.
- Ngưỡng theo dõi (`theta`, `min-size`, `delta`) ảnh hưởng đến số sự kiện. Kết quả hiện dùng mặc định Greene et al. (θ = 0.3).
- Video nhồi rất nhiều hashtag (tối đa 149) tạo clique lớn. Có thể thử `--weighting newman` để giảm ảnh hưởng.

## 8. Trạng thái và việc tiếp theo

Stage 3 **hoàn tất**: đã áp dụng 4 thuật toán (2 tĩnh, 2 động), chọn tham số trên train, đánh giá trên test, kiểm tra độ nhạy, và trả lời câu hỏi nghiên cứu. **Modularity** (yêu cầu mục 2) được báo cáo theo từng snapshot: 0.70–0.74.

Tiếp theo: Stage 4 — trực quan hóa (alluvial/Sankey cho `community_timeline.csv`, Gephi cho `partitions.csv`), Stage 5 — ứng dụng minh họa.
