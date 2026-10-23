# Chạy bằng nhấp đúp trên Windows

1. Nhấp đúp **CAI_DAT.bat** khi cài lần đầu hoặc sau khi cập nhật thư viện. Cần Internet; nếu Windows hỏi quyền cài phần mềm, làm theo hộp thoại. Bộ cài tự kiểm tra Python, tạo .venv, cài requirements.txt, bổ sung FFmpeg/FFprobe và Codex CLI nếu thiếu. Các công cụ đang có được giữ lại.
2. Nếu chưa đăng nhập Codex, chọn **Sign in with ChatGPT** trong trình duyệt và hoàn tất đăng nhập. Không cần API key.
3. Nhấp đúp **CHAY_ADMIN.bat**. Trình duyệt tự mở trang quản trị tại http://127.0.0.1:8765. Giữ cửa sổ chạy mở; đóng cửa sổ hoặc Ctrl+C sẽ dừng server và các lượt đang chạy. Nếu admin đã chạy, file mở lại trang đó.
4. Nhập game, tải video và bấm chạy như bình thường.

Nếu máy chưa có winget, cài **App Installer** từ Microsoft Store rồi chạy lại CAI_DAT.bat. Không cần mở VS Code hay gõ lệnh để sử dụng hằng ngày.

## Thư mục bài viết

Mỗi lượt mới từ admin lưu vào:

```text
runs/block-blast-3d_23-10-2026_14-30-05/
  result/
    ..._en_US.docx
    ..._vi_VN.docx
    images/             ← tất cả ảnh dùng trong bài
    image_names.csv     ← tên file, caption và mục EN/VI tương ứng
    IMAGE_CREDITS.txt    ← tác giả, nguồn và giấy phép ảnh
    result_manifest.json
```

Thời gian theo giờ máy Windows, theo thứ tự ngày-tháng-năm_giờ-phút-giây. Nếu trùng tên trong cùng giây, thêm _2, _3… để không ghi đè. Chạy tiếp vẫn dùng cùng thư mục. Các lượt cũ giữ nguyên tên và vẫn tải/chạy tiếp được.

Khi đăng site, dùng **result** hoặc bấm **Bộ đăng site (.zip)** trong kết quả bài. Ảnh đặt tên theo caption (nếu thiếu caption thì lấy H3/H2 gần nhất), có số thứ tự để tránh trùng. CSV mở được bằng Excel, chứa caption tiếng Anh/Việt và nguồn. Một ảnh dùng nhiều lần chỉ lưu một file; CSV ghi đầy đủ các vị trí sử dụng. Giữ attribution và link giấy phép Commons khi đăng ảnh.

Thư mục output vẫn được giữ để tương thích nút tải Word hiện có. result là bản sao của hai Word đã duyệt và ảnh gốc, không viết lại bài hay gọi thêm AI. Khi cần thay bộ result đã có, bản cũ được giữ trong result_history.

Bộ cài giữ nguyên config.json, dữ liệu game, câu trả lời, bài viết và thiết lập VS Code đã có. Nếu chưa có settings.json, tự cấu hình Python từ .venv theo đường dẫn tương đối. Trên VS Code đã có thiết lập riêng, dùng Python: Select Interpreter để chọn .venv khi cần.
