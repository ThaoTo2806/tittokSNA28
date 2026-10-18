# TikTok Hashtag Co-occurrence SNA — README

## 1. Mục tiêu giai đoạn 1

Giai đoạn 1 xây dựng và kiểm định mạng đồng xuất hiện hashtag từ dữ liệu TikTok đã được làm sạch. Mạng được biểu diễn dưới dạng **undirected weighted co-occurrence network**:

- **Node:** một hashtag đã chuẩn hóa.
- **Edge:** một cặp hashtag khác nhau cùng xuất hiện trong một video.
- **Weight:** số video chứa đồng thời cặp hashtag đó.
- Một video có `k` hashtag phân biệt đóng góp tối đa `k × (k − 1) / 2` cặp đồng xuất hiện.

## 2. Quy trình đã thực hiện

1. **Audit dữ liệu đầu vào** bằng `audit_tiktok_data.py` để kiểm tra dữ liệu TikTok và xác định các vấn đề cần xử lý.
2. **Làm sạch dữ liệu** bằng `clean_tiktok_data.py`:
   - Chuẩn hóa/làm sạch hashtag từ các cột hashtag và caption theo logic của script.
   - Tạo cột `hashtags_clean` chứa hashtag phân tách bằng dấu `|`.
   - Tạo/chuẩn hóa `hashtag_count`.
   - Loại video trùng lặp.
3. **Dựng mạng hashtag** bằng phiên bản đã sửa `build_hashtag_network.py`:
   - Chuẩn hóa Unicode NFC và chữ thường.
   - Giữ lại hashtag có chữ/số Unicode, emoji và ký hiệu hợp lệ; loại giá trị rỗng, có khoảng trắng, chứa `#` bên trong, ký tự điều khiển/ surrogate, hoặc dài hơn 100 ký tự.
   - Đếm tần suất hashtag theo video.
   - Tạo cạnh vô hướng theo các cặp hashtag cùng xuất hiện trong một video và tính trọng số cạnh.
4. **Kiểm định và hoàn tất Stage 1** bằng `finalize_stage1_diagnostic_fixed.py`:
   - Dùng cùng quy tắc chuẩn hóa với bộ dựng mạng.
   - Đối chiếu hashtag duy nhất với node trong `nodes.csv`.
   - Kiểm tra node ID trùng, cạnh vô hướng trùng, self-loop, trọng số cạnh, endpoint không tồn tại.
   - Tạo ma trận kề sparse CSR, chỉ số node và báo cáo kiểm định.
5. **Chạy lại kiểm định sau khi sửa chuẩn hóa**. Kết quả cuối cùng hiện tại: `PASS (PASS=17, WARN=0, FAIL=0)`.

## 3. Kết quả cuối cùng Stage 1

| Chỉ số | Kết quả |
|---|---:|
| Số video trong `cleaned_data.csv` | 21,102 |
| Video có ít nhất một hashtag | 20,198 |
| Video không có hashtag | 904 |
| Hashtag duy nhất / số node | 24,869 |
| Số cạnh vô hướng | 213,266 |
| Số phần tử khác 0 trong ma trận kề đối xứng | 426,532 |
| Kích thước ma trận kề | 24,869 × 24,869 |
| Ma trận kề đối xứng | Có |
| Đường chéo ma trận bằng 0 | Có |
| Kiểm tra video lệch trạng thái có/không hashtag | 0 |
| Trạng thái kiểm định cuối | **PASS (17 PASS, 0 WARN, 0 FAIL)** |

`nnz = 426,532` bằng hai lần số cạnh vô hướng (`2 × 213,266`) vì mỗi cạnh được lưu ở cả vị trí `(i, j)` và `(j, i)` trong ma trận kề đối xứng.

## 4. File đầu vào chính

- `data/processed/cleaned_data.csv` — dữ liệu đã làm sạch, được sử dụng để xây dựng mạng.

## 5. File script liên quan

| File | Vai trò |
|---|---|
| `audit_tiktok_data.py` | Audit dữ liệu đầu vào |
| `clean_tiktok_data.py` | Làm sạch dữ liệu và hashtag |
| `build_hashtag_network.py` | Dựng node, edge, mapping, GraphML và summary |
| `finalize_stage1_diagnostic_fixed.py` | Kiểm định nhất quán và tạo ma trận kề/báo cáo |
| `finalize_stage1.py` | Phiên bản hoàn tất/kiểm định trước đó; giữ lại để tham khảo, cần ưu tiên bản diagnostic đã sửa khi chạy lại kiểm định |

## 6. File đầu ra Stage 1

Các file được lưu trong `data/processed/network/`.

| File | Nội dung / mục đích |
|---|---|
| `nodes.csv` | Danh sách node; gồm ID hashtag và tần suất xuất hiện theo video |
| `edges.csv` | Danh sách cặp hashtag và trọng số đồng xuất hiện |
| `video_hashtag_mapping.csv` | Mapping video với danh sách hashtag đã chuẩn hóa và số hashtag |
| `hashtag_network.graphml` | Mạng dạng GraphML, có thể nhập vào Gephi |
| `network_summary.json` | Thống kê tổng quan và định nghĩa mạng |
| `adjacency_matrix.npz` | Ma trận kề sparse định dạng CSR |
| `node_index.csv` | Ánh xạ node sang chỉ số hàng/cột của ma trận |
| `stage1_validation_report.csv` | Chi tiết từng phép kiểm tra và trạng thái PASS/WARN/FAIL |
| `stage1_final_report.json` | Báo cáo kiểm định tổng hợp dạng JSON |
| `hashtags_missing_from_nodes.csv` | Chẩn đoán hashtag có trong dữ liệu nhưng chưa khớp node; sau lần kiểm định PASS hiện không còn chênh lệch theo quy tắc dùng chung |
| `nodes_extra_not_in_cleaned_data.csv` | Chẩn đoán node không khớp với tập hashtag trong dữ liệu |
| `video_hashtag_count_discrepancies.csv` | Chẩn đoán video có khác biệt khi đếm hashtag; lần chạy cuối có 0 video lệch trạng thái có/không hashtag |

## 7. Cách chạy lại

Chạy các lệnh từ thư mục gốc dự án, nơi có thư mục `data/`:

```powershell
py audit_tiktok_data.py
py clean_tiktok_data.py
py build_hashtag_network.py
py finalize_stage1_diagnostic_fixed.py
```

**Lưu ý:** Chỉ chạy lại audit/clean nếu cần tái tạo dữ liệu sạch. Nếu `cleaned_data.csv` không thay đổi và chỉ cần dựng lại mạng, chạy từ bước `build_hashtag_network.py`. Sau khi thay đổi quy tắc chuẩn hóa hoặc dữ liệu, luôn chạy lại cả bước dựng mạng và kiểm định để các file đầu ra đồng bộ.

## 8. Tiêu chí hoàn tất Stage 1

Stage 1 được đánh dấu hoàn tất theo lần chạy hiện tại vì:

- Bộ dựng mạng và bộ kiểm định dùng cùng quy tắc chuẩn hóa hashtag.
- Tập hashtag duy nhất khớp với số node: 24,869.
- Không còn chênh lệch trạng thái video có/không hashtag.
- Các kiểm tra cấu trúc cạnh và ma trận kề đều PASS.
- Báo cáo tổng hợp cuối cùng là `PASS (17 PASS, 0 WARN, 0 FAIL)`.

Nếu dữ liệu hoặc quy tắc chuẩn hóa thay đổi, cần chạy lại pipeline và xác nhận báo cáo kiểm định mới trước khi dùng kết quả cho các phân tích tiếp theo.

## 9. Phạm vi và việc tiếp theo

README này ghi nhận **Stage 1: chuẩn bị dữ liệu, xây dựng mạng và kiểm định cấu trúc**. Nó không khẳng định các phân tích mạng ở giai đoạn sau (ví dụ centrality, community detection, robustness hoặc diễn giải nội dung) đã được thực hiện. Các bước đó cần được thực hiện và báo cáo riêng.
