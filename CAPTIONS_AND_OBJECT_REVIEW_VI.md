# Chú thích ảnh và danh sách đối tượng trong game

## Chú thích và alt ảnh

Hai Word EN/VI dùng mô tả nội dung minh họa của từng ảnh. Nếu bản thảo cũ chưa có mô tả riêng, chương trình dùng tiêu đề H3 chứa ảnh, rồi đến H2. Ví dụ ảnh trong mục `Coins and Scoring` sẽ mang chú thích đó, thay cho `Gameplay frame FRAME010` hoặc thời gian video. Bản VI dùng chú thích đã dịch và nhãn `Hình`.

Bản thảo mới có `image_captions` cho từng đoạn: `[{"image_id": "FRAME010", "caption": "Coin routes between the trains"}]`. Danh sách phải khớp `image_ids`; bản VI dịch phần caption và giữ ID/thứ tự. Tác giả, giấy phép và nguồn ảnh Wikimedia vẫn được ghi riêng.

Không thêm các thẻ H2/H3 trùng lặp chỉ để đặt tên ảnh: caption hiển thị trong `figcaption`, alt nằm trên thẻ ảnh; cấu trúc heading của bài được giữ nguyên.

## Nhận diện nhiều đối tượng hơn

Node Analyze xuất `game_objects`, kiểm tra các nhóm: nhân vật, kẻ địch/NPC, từng loại vật cản, vật phẩm thu thập, power-up, địa hình/đường đi, cảnh vật, đối tượng tương tác và UI/HUD. Mỗi đối tượng có tên, ngoại hình, hành vi quan sát được, frame minh họa, độ tin cậy và câu hỏi còn thiếu.

Không ép mọi game phải có cùng số lượng đối tượng. AI chỉ liệt kê những gì có bằng chứng và không tự đoán chức năng từ biểu tượng. Bài viết dùng danh sách đối tượng đã xác minh để giải thích Game Elements trong các mục H3 thuộc Gameplay.

## Form bổ sung

Sau Analyze và trước Research/Writer, chế độ `auto` mở form nếu danh sách dưới 8 đối tượng hoặc có mục chưa chắc/còn câu hỏi. Ngưỡng 8 chỉ là gợi ý kiểm tra, không bắt bạn tạo thêm đối tượng không tồn tại.

Trong form có thể:

- Thêm, sửa hoặc xóa đối tượng; chọn nhóm, nhập tên, ngoại hình, chức năng/cơ chế và frame minh họa.
- Điền tiếng Việt; Writer sẽ diễn đạt lại bằng en-US rồi dịch bài hoàn chỉnh sang VI.
- Chọn mục nào được đưa vào bài và mở thư mục contact sheet để đối chiếu.
- Chọn **Xác nhận danh sách và tiếp tục** để ghi nhận các chi tiết là thông tin do đội phát triển cung cấp.
- Chọn **Lưu nháp và tạm dừng** hoặc đóng cửa sổ để dừng an toàn; lần chạy `--resume` tiếp theo sẽ mở lại.
- Chọn **Bỏ qua bổ sung** để tiếp tục với bằng chứng AI đủ chắc; chức năng chưa xác nhận không trở thành dữ kiện đã biết.

Dữ liệu lưu ở `game_objects.json` trong từng run. Những lần chỉnh sửa được lưu lịch sử trong `object_reviews/`. Khi danh sách thay đổi, lần chạy `--resume` sẽ giữ bản thảo cũ trong `article_history/`, viết lại bài theo dữ liệu mới rồi dịch lại. File `article_provenance.json` giúp ngăn xuất một bài chưa cập nhật danh sách.

Form dùng Tkinter có sẵn trong Python trên máy này. Việc mở và điền form không gọi Codex. Số frame mặc định vẫn là 16; phân tích danh sách đối tượng nằm trong chính lượt Analyze.

## Chạy trong PowerShell của thư mục dự án

Chạy như trước, form tự hiện khi cần:

```powershell
.\start_windows.ps1 -Video "D:\My_WorkSpace\Chief_of_Agent\Test1_surway\gameplay.mp4"
```

Muốn luôn hiện form và có thư mục cố định để chạy tiếp:

```powershell
.\start_windows.ps1 -Video "D:\My_WorkSpace\Chief_of_Agent\Test1_surway\gameplay.mp4" -Out ".\runs\gameplay_review" -ObjectReview always
```

Chạy tiếp sau khi lưu nháp:

```powershell
.\start_windows.ps1 -Video "D:\My_WorkSpace\Chief_of_Agent\Test1_surway\gameplay.mp4" -Out ".\runs\gameplay_review" -Resume
```

Mở riêng form của một run đã có:

```powershell
.\.venv\Scripts\python.exe run.py objects --run-dir ".\runs\gameplay_review"
```

Phiên không có giao diện có thể nhập JSON thủ công:

```powershell
.\.venv\Scripts\python.exe run.py objects --run-dir ".\runs\gameplay_review" --from-json ".\objects_manual.json"
```

File nhập có dạng `{"objects": [{"name": "Tên vật phẩm", "category": "power_up", "appearance": "Mô tả", "observed_behavior": "Chức năng do bạn xác nhận", "frame_ids": []}]}`. Lệnh nhập này ghi nhận xác nhận của người dùng. Sau khi chỉnh, chạy lại pipeline với `-Resume` để cập nhật bài; không chỉ xuất lại bản thảo cũ.

`-ObjectReview never` bỏ form khi cần chạy không tương tác. Cấu hình mặc định nằm ở `object_review_mode` và `min_detected_objects` trong `config.json`.

Run cũ có thể chưa có `game_objects` trong analysis. Khi chạy tiếp, form cho phép nhập bổ sung; muốn AI nhận diện lại theo cấu trúc mới, chạy video vào một thư mục run mới. Chương trình không tự gọi lại AI chỉ vì bạn mở form.
