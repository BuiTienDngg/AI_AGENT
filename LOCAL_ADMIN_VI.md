# Trang quản trị Game SEO Office

Giao diện dùng màu hồng chủ đạo. Nhấn **Ctrl+F5** để nạp CSS/JavaScript mới sau khi cập nhật.

Mở terminal VS Code **trong thư mục có `local_admin.py`, `run.py` và `.venv`**:

```powershell
powershell -ExecutionPolicy Bypass -File .\start_admin.ps1
```

Mở **http://127.0.0.1:8765**. Giữ terminal mở. Nhấn **Ctrl+C trong terminal** để đóng máy chủ; các lượt đang chạy cũng được dừng. Nếu trang đã chạy, chỉ mở địa chỉ trên. Có thể đổi cổng bằng `-Port 8766`.

Giao diện dùng tông hồng chủ đạo. Sau khi cập nhật mã, khởi động lại máy chủ local để nạp các API mới rồi tải lại trang.

Trong VS Code cũng có thể chọn **Terminal → Run Task → Game SEO: Trang quản trị local**.

Nếu chuyển project sang máy khác, tạo `.venv` và cài `requirements.txt` như README. Trang dùng Flask/Waitress và SQLite; giao diện không cần npm hoặc CDN. FFmpeg/FFprobe và Codex CLI đã đăng nhập ChatGPT vẫn cần có để viết bài. `local_admin.py` đọc thêm PATH User/Machine hiện có trên Windows, không ghi đè PATH hệ thống.

## Nhập và quản lý game

1. Chọn **Thêm game mới**.
2. Điền tên, site chính thức và URL chơi game đầy đủ `https://...`.
3. Kéo thả video hoặc bấm vùng chọn file. Tối đa 4 GB cho request tải lên, tối đa 45 phút theo cấu hình hiện tại. Hệ thống kiểm tra có luồng hình ảnh video trước khi lưu. Định dạng: MP4/MOV/MKV/WEBM/AVI/M4V. Trình duyệt có thể không phát preview một số codec; FFmpeg vẫn xử lý nếu hỗ trợ.
4. Ý tưởng/nguồn gốc, cốt truyện, phong cách là tùy chọn. Điền nội dung thì AI phải bám theo tiền đề đó; để trống thì AI phát triển ý tưởng sáng tạo dựa trên gameplay và nguồn thực tế. Nếu game không có cốt truyện, ghi rõ để AI không tạo thêm.
5. Điều khiển PC và điện thoại đều bắt buộc. Ghi thao tác cụ thể; nếu không hỗ trợ nền tảng đó, ghi **Không hỗ trợ**.
6. **Lưu game**, sau đó **Chạy viết bài**.

Sửa game tạo phiên bản đầu vào mới. Lượt đang chạy/chạy tiếp dùng bản đã chốt lúc bắt đầu; muốn áp dụng thay đổi của form game, bấm **Chạy viết bài** để tạo lượt mới. Thay video giữ lại video cũ phục vụ các phiên bản trước.

Xóa game gỡ nó khỏi thư viện; dữ liệu cũ, video và Word vẫn ở máy để giữ lịch sử. Có thể tìm/tải kết quả trong **Lịch sử & kết quả**.

## Khi AI hỏi thêm

Các câu hỏi của AI được giữ trong từng lượt chạy và đồng thời ghi vào thư viện của game. Trong thẻ game, bấm biểu tượng **? Câu hỏi đã lưu** để xem và sửa quyết định/câu trả lời cho các lượt chạy mới. Lịch sử từng lần sửa vẫn được lưu trong SQLite. Khi chạy lại cùng game, hệ thống tự dùng lại câu trả lời **đã xác nhận** hoặc **đã chọn bỏ khỏi bài** nếu câu hỏi khớp nội dung; câu hỏi mới, câu hỏi chưa chốt và mục AI chỉ quan sát từ video vẫn cần được kiểm tra. Chỉnh thư viện không tự sửa bản Word cũ; muốn sửa lượt hiện tại, dùng tab **Câu hỏi & đối tượng** của lượt đó.

Các xác nhận đã lưu cũng được gửi làm ngữ cảnh cho AI ở lượt mới để tránh hỏi lại cùng một thông tin bằng cách diễn đạt khác. Mỗi lượt chốt riêng bản thư viện lúc bắt đầu; sửa thư viện sau đó chỉ áp dụng cho lượt mới. Trong cửa sổ câu hỏi đã lưu, lưu một câu không làm mất bản nháp đang sửa ở câu khác.

Câu hỏi hiển thị **hai cột: Câu hỏi gốc | Tiếng Việt** (trên điện thoại xếp dọc). Các lượt mới tạo hai ngôn ngữ trong cùng lượt Analyze/Notes, không gọi riêng model chỉ để dịch. Câu hỏi cũ chưa có bản VI có nút **Dịch câu hỏi sang VI**: dịch theo lô qua Codex CLI của lượt đó và lưu lại, không viết lại bài hoặc sửa câu trả lời đã chốt. Có thể dừng dịch, sửa bản dịch thủ công và lưu; sửa câu hỏi gốc làm bản dịch cũ mất hiệu lực. Dịch qua Codex vẫn dùng hạn mức tài khoản.

Sau phân tích video, workflow chờ bạn duyệt danh sách đối tượng và các cơ chế chưa chắc. Sau nghiên cứu, có thể xuất hiện câu hỏi bổ sung. Vào **AI đang hỏi** hoặc mở chi tiết lượt chạy:

- **Giữ điều thấy rõ trong video:** giữ thông tin quan sát rõ, không biến nó thành xác nhận của chủ game.
- **Tôi xác nhận nội dung này:** nhập mô tả/câu trả lời cuối cùng chính xác. Các thông tin này được đưa vào các bước viết, kiểm tra và sửa bài.
- **Bỏ chi tiết khỏi bài:** AI không dùng chi tiết chưa biết làm sự thật. Nút **Bỏ các mục chưa rõ** chỉ chọn cách này cho các mục chưa chốt; cần bấm lưu để áp dụng.
- **Chỉnh câu hỏi:** sửa cách đặt câu hỏi; phiên bản trước vẫn được lưu.
- **Bổ sung đối tượng hoặc luật chơi:** thêm những gì AI chưa liệt kê.

**Lưu trả lời** giữ bản nháp và lịch sử, chưa chạy AI. **Lưu, duyệt & chạy tiếp** chỉ chạy khi không còn mục chưa chốt. Thông tin gameplay do chủ game xác nhận không thay cho bằng chứng học thuật; các gate nguồn, trích dẫn và license ảnh vẫn giữ nguyên.

Tab **Lịch sử trả lời** giữ các phiên bản đã lưu. Có thể sửa câu trả lời khi lượt đang chờ/đã dừng/đã hoàn tất. Sửa khi đang chạy bị chặn để tránh đọc dữ liệu dở dang. Khi câu trả lời đổi, bản thảo phải được cập nhật; Word đã xuất được lưu thêm trong `output_history/` trước khi chạy tiếp sửa bài.

## Chạy, dừng và kết quả

Trong khung **Model cho lượt chạy mới**, chọn **Model GPT** và **Mức suy luận** trước khi bấm Chạy viết bài. Danh sách đọc từ catalog Codex trên máy, chỉ liệt kê các model GPT có đầu vào ảnh; có ô nhập ID model khác. Cấu hình mặc định hiện tại vẫn được giữ. Lựa chọn được ghi riêng vào dữ liệu job và `admin_config.json`, truyền cho CLI bằng `--model` và `--config model_reasoning_effort=...`; không sửa cấu hình Codex toàn máy. Mở chi tiết hoặc lịch sử để xem model đã dùng. **Chạy tiếp** giữ model của lượt cũ; để so sánh model khác, tạo lượt chạy mới.

Tham khảo cách truyền tham số trong [OpenAI Docs về Codex CLI](https://learn.chatgpt.com/docs/developer-commands?surface=cli).

- Một lượt chạy tại một thời điểm để dễ theo dõi và kiểm soát hạn mức.
- **Dừng viết bài** dừng cả worker, Codex và FFmpeg của lượt đó. Các bước đã lưu được giữ lại.
- **Chạy tiếp** dùng lại khung hình/phân tích/nguồn đã có. Không cần gửi lại video hoặc phân tích lại chỉ để trả lời câu hỏi. Một số bước đang làm dở phải chạy lại.
- Đóng cửa sổ chi tiết/trình duyệt không dừng job nếu máy chủ còn chạy. Nếu máy chủ đóng đột ngột, lần mở sau đánh dấu gián đoạn; dùng **Chạy tiếp**.
- Nhật ký, lỗi QA và số token CLI đã ghi nhận hiện trong chi tiết. Token không quy đổi thành phần trăm hạn mức tuần.
- Tab **Tiến độ & kết quả** hiển thị snapshot phần trăm hạn mức Codex đã dùng trong cửa sổ **5 giờ** và **tuần**, lấy từ `account/rateLimits/read` trước/sau mỗi lượt gọi Codex. Dữ liệu được lưu trong `runs/admin_<id>/quota_usage.json`. Đây là mức dùng của **toàn tài khoản** tại các mốc đo; phần tăng có thể gồm các hoạt động Codex khác và không được tính khi cửa sổ reset. Nếu dịch vụ không trả dữ liệu, giao diện báo chưa lấy được thay vì suy từ token.
- Chỉ bài EN vượt QA mới được dịch VI và xuất **2 file Word EN/VI**. Tải trong chi tiết hoặc lịch sử. Không thêm đầu ra HTML/Markdown.

Các lượt terminal cũ cũng được liệt kê trong lịch sử. **Nhập thành game** mở form từ bài cũ; nếu video gốc còn tồn tại, có thể dùng lại. Điền URL chơi game và điều khiển còn thiếu trước khi lưu. Thao tác này không sửa bài cũ.

## Dữ liệu và kiểm tra

- `local_admin_data/office.sqlite3`: game, các phiên bản đầu vào và trạng thái job.
- `local_admin_data/videos/`: video đã tải/nhập.
- `runs/admin_<id>/`: đầu vào cố định, câu hỏi, lịch sử trả lời, log, nghiên cứu, QA và hai Word.
- Máy chủ chỉ lắng nghe `127.0.0.1`; không tự đưa lên Internet. Không cần tài khoản quản trị riêng cho bản local một người dùng.
- AI vẫn dùng Codex CLI, đăng nhập ChatGPT hiện tại và hạn mức của bạn. Không yêu cầu API key.

Kiểm tra phần mềm:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
.\.venv\Scripts\python.exe -m pip check
```

Kiểm tra UI tự động tùy chọn: cài `playwright` vào venv rồi chạy `tools/check_admin_ui.py` (cần Microsoft Edge và máy chủ chính ở cổng 8765 để kiểm tra lịch sử). Bài kiểm tra dùng dữ liệu tạm và worker giả lập, **không gọi Codex**. Ảnh và báo cáo nằm trong `maintenance_history/admin_ui_validation/`.
# Tài khoản Codex tại /admin

**Cập nhật:** module đã bổ sung đăng nhập administrator, dashboard /accounts, policy/hàng đợi và API dự phòng tùy chọn. Mô tả bên dưới là bản ban đầu; dùng [hướng dẫn mới](CODEX_CAPACITY_VI.md) cho cấu hình và quyền truy cập hiện tại. Chu kỳ mặc định hiện là 60 giây.

Từ menu **Tài khoản Codex**, mở http://127.0.0.1:8765/admin. Các thao tác thêm, sửa, xóa hồ sơ và API quản lý nằm dưới /admin. Đây là trang local của cùng ứng dụng, không phải lớp đăng nhập quản trị riêng.

- Thêm tên hiển thị, thư mục CODEX_HOME đã đăng nhập, ghi chú và ngưỡng cảnh báo. Để trống thư mục khi thêm để dùng hồ sơ Codex hiện tại.
- Đây là danh sách hồ sơ đăng nhập đã có; không tạo tài khoản ChatGPT mới và không nhập mật khẩu, API key hay token vào form.
- Xem quota **còn lại** cho 5 giờ/tuần, thời điểm reset, lần kiểm tra và lần lấy số đo thành công gần nhất. Số đo quota thuộc toàn tài khoản; tên hồ sơ là nhãn tự đặt.
- Python chạy nền trong tiến trình local admin, kiểm tra mỗi 5 phút; nút kiểm tra ngay có giới hạn tối thiểu 30 giây. Đóng server thì dừng theo dõi. Không gọi model tạo nội dung để kiểm tra.
- Khi kiểm tra lỗi, số đo thành công trước đó được giữ lại kèm cảnh báo; không xem số đo cũ là quota hiện tại.
- Bật/tắt theo dõi theo hồ sơ. Đổi thư mục sẽ xóa số đo cũ của hồ sơ để tránh gán nhầm. Xóa hồ sơ chỉ xóa bản ghi theo dõi và lịch sử số đo, giữ nguyên thư mục đăng nhập và các bài viết.
- Hồ sơ, số đo gần nhất và tối đa 100 lần kiểm tra mỗi hồ sơ lưu trong SQLite local_admin_data/office.sqlite3. Thông tin đăng nhập tiếp tục do Codex quản lý.

Quota thấp chỉ cảnh báo: không thể bảo đảm đủ quota để hoàn thành một bài. Trang này không tự chuyển tài khoản hoặc thay đổi đăng nhập của workflow khi chạm hạn mức; các bài viết vẫn dùng đăng nhập Codex hiện tại.

Kỹ thuật đọc quota dùng [Codex App Server: account/rateLimits/read](https://learn.chatgpt.com/docs/app-server); thư mục hồ sơ dùng [CODEX_HOME](https://learn.chatgpt.com/docs/config-file/config-advanced). Không cần API key.

