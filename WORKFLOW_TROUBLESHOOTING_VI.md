# Sửa lượt chạy dừng ở QA

Ngày 21/10/2026, hai lượt `video_project_8_optimized` và `video_project_8_v2` dừng sau các bước Repair/Critic. CLI không báo lỗi xác thực hay thiếu thư viện. Những vấn đề xác nhận trong log:

- Query nghiên cứu là cả câu dài, làm tìm kiếm trả về nhiều nguồn lệch chủ đề. Query ảnh có nhánh dự phòng cố định về nhà ga, kể cả khi video là game xếp khối.
- Bản nháp/sửa chưa đáp ứng đồng thời số nguồn khác nhau và tổng số lần trích dẫn. Chèn thêm một nguồn chưa đủ nếu bài vẫn thiếu số lần trích dẫn.
- Critic đôi lúc trả `pass_editorial=false` nhưng chỉ ghi các `warning`; Repair không được phép sửa cảnh báo nên không có lỗi hợp lệ để xử lý tiếp.
- Một lỗi được ghi tại `sections[0]` thay vì một đoạn cụ thể, khiến bộ chọn đoạn sửa bỏ sót.

## Cách xử lý hiện tại

Analyze yêu cầu query ngắn theo tên khái niệm; Wikipedia ưu tiên trang có tên khớp trước khi dùng tìm kiếm toàn văn. Commons chỉ tìm theo chủ đề của game, bỏ nhánh nhà ga cố định. Nếu vẫn thiếu ảnh phù hợp, chương trình dừng với hướng dẫn rõ thay vì gán ảnh không liên quan. Số nguồn thu thập không vượt `max_web_sources`.

Giữ nguyên cách gom ngữ cảnh `stage_context_*.json` và lọc cảnh báo khỏi bundle Repair. Bundle Writer/Critic/Repair thêm `publishing_requirements.json`; ngữ cảnh sửa ghi riêng số trích dẫn hiện có, mức tối thiểu, nguồn đã dùng và nguồn chưa dùng. Các lời bình về giới hạn bằng chứng phải nằm ở phân tích nội bộ, không đưa vào bài công khai.

Chỉ danh sách cảnh báo rõ ràng được xem là không chặn xuất bản; `critique.json` và cờ gốc vẫn được giữ để kiểm tra. Lỗi thực sự, severity không hợp lệ, hoặc từ chối mà không giải thích vẫn chặn. Python QA tiếp tục bắt buộc. Lỗi tại một section được ánh xạ sang các đoạn đang tồn tại trong chính section đó, không mở quyền sửa cảnh báo ở phần khác.

## Chạy tiếp

Từ terminal tại thư mục project:

```powershell
.\start_windows.ps1 -Video "D:\Videos\your_game.mp4" -Out ".\runs\your_run" -Resume
```

Phải dùng đúng `-Out` cũ để tận dụng frames và danh sách đối tượng đã xác nhận. Dữ liệu/log các lượt trước vẫn giữ nguyên. Khi chỉ cần xuất lại bài đã duyệt và bản dịch còn khớp:

```powershell
.\.venv\Scripts\python.exe run.py export --run-dir ".\runs\your_run"
```

Đầu ra bài viết chỉ gồm hai Word EN/VI. Báo cáo token và JSON nội bộ vẫn được giữ để chạy tiếp.

## Sửa riêng kế hoạch nghiên cứu

Nếu cần sửa query cho một lượt đang khôi phục, có thể đặt `research_plan.json` trong thư mục lượt đó:

```json
{
  "text_queries": ["Mosaic", "Tessellation", "Polyomino", "Tiling puzzle"],
  "image_queries": ["geometric mosaic tiles", "geometric patchwork quilt"],
  "academic_queries": []
}
```

Ví dụ này chỉ phù hợp cho game xếp khối. Mảng học thuật rỗng có nghĩa là không tìm thêm nghiên cứu tâm lý; không được viết các khẳng định học thuật thiếu nguồn. Kế hoạch được dùng khi bước Research thực sự chạy, không tự thay thế registry đã lưu khi `--resume`. Nếu thay registry nguồn/ảnh, phải tạo lại notes và bản thảo tương ứng, không xuất ngay bài còn dùng ID cũ.

Lượt `video_project_8_v2` được khôi phục bằng kế hoạch phù hợp; nguồn và bản thảo lỗi đã lưu trong `recovery_history/`. Phân tích video, 16 đối tượng do chủ dự án xác nhận, model Luna, log và token đã dùng đều được giữ. Bản mã/cấu hình trước khi sửa được lưu tại `maintenance_history/`.
