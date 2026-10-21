# Hướng viết chính thức của đội phát triển Slope3

Chủ dự án đã xác nhận: đội Slope3 trực tiếp phát triển các game đưa vào quy trình này. Ý tưởng sản phẩm được triển khai từ phần bối cảnh thực tế mở đầu bài viết. Đây là định hướng sáng tạo do chủ dự án cho phép; không phải yêu cầu AI khôi phục một lịch sử phát triển không được cung cấp.

## Mạch nội dung

**Hiện tượng thực tế có nguồn -> ý tưởng của chúng tôi -> quyết định thiết kế -> trải nghiệm của người chơi.**

| Phần | Nội dung cần thể hiện |
|---|---|
| Concept and Inspiration | Mở bằng bối cảnh thực tế phù hợp, rồi nói rõ vì sao chúng tôi phát triển ý tưởng game từ đó. |
| Story | Đưa ý tưởng ấy vào một câu chuyện hoặc tiền đề sáng tạo có chủ đích; không chèn lời bình về quy trình biên tập. |
| Gameplay | Nói rõ người chơi làm gì, quy luật nào được kích hoạt và kết quả ra sao. Giải thích vòng chơi chính trước, mẹo và ý đồ thiết kế sau. |
| Visual Style | Mô tả màu sắc, hình khối, bàn chơi và giao diện bằng từ dễ hình dung; nói chúng giúp người chơi nhìn rõ điều gì. |
| Standout Features | Nêu các lựa chọn thiết kế cụ thể và giá trị trải nghiệm của chúng. |
| Controls | Hướng dẫn thao tác đã xác minh; không suy đoán nút bấm từ hình ảnh. |

## Giọng viết

Bài là tiếng nói chính thức của Slope3: `we`, `our game`, `we developed`, `we designed`, `we chose`. Dùng tự nhiên, không lặp tên thương hiệu hoặc đại từ trong mọi câu. Bản VI giữ đúng vai trò: `chúng tôi`, `trò chơi của chúng tôi`, `chúng tôi phát triển/thiết kế`.

Giọng nhà phát triển không đồng nghĩa với việc đoạn nào cũng phải giải thích triết lý thiết kế. Sau khi giới thiệu sản phẩm của chúng tôi, hãy nói trực tiếp với người chơi. Đọc xong một đoạn, họ cần hình dung được hành động hoặc hình ảnh cụ thể. Câu ngắn, từ quen thuộc, nhịp kể thoải mái; không cố kéo dài một game đơn giản thành bài phân tích học thuật. Quy tắc đầy đủ và ví dụ trước/sau nằm trong [WRITING_STYLE.md](WRITING_STYLE.md), được gửi tới Writer, Critic, Repair và Translate.

Ví dụ cho Block Blast, với thao tác và quy luật đã được chủ dự án xác nhận:

> Chọn một khối hình, kéo vào chỗ trống trên bàn chơi rồi thả tay. Lấp kín một hàng ngang hoặc một cột dọc là bùm! Hàng hoặc cột đó biến mất, nhường chỗ cho những khối tiếp theo.

Không dùng các cách nói như “hình chữ nhật gọn”, “yêu cầu về không gian”, “định hướng việc đặt” thay cho mô tả hình dáng hoặc thao tác. “Bùm!” chỉ là một nhịp kể vui, không được biến thành khẳng định game có âm thanh hay hiệu ứng nổ. Cách viết áp dụng cho mọi game; cơ chế của Block Blast chỉ áp dụng khi chính game đó đã được xác nhận.

Các câu mô tả cụ thể chỉ dùng khi hình ảnh/cơ chế của video phù hợp. Trích dẫn dùng cho dữ kiện thế giới thực và kết quả nghiên cứu; không dùng bài báo học thuật làm bằng chứng rằng đội Slope3 viết mã hoặc có một ý định sáng tạo nhất định.

## Cấu hình và kiểm tra

`config.json` ghi website, vai trò developer, xác nhận tác giả và cho phép xây dựng concept. Mỗi lượt Codex nhận một bản `brand_context.json` trong thư mục run; dữ liệu web không được tự mở rộng các xác nhận này.

QA cho phép câu về vai trò phát triển khi có xác nhận rõ ràng. Critic kiểm tra mạch concept, giọng nhà phát triển, cơ chế và tính phù hợp của nguồn. Lối chơi không hiểu được hoặc phần điều khiển thay thao tác đã biết bằng lời bình chung chung là lỗi phải sửa trước khi xuất bài. Python chặn một số cụm tối nghĩa đã gặp; phần đánh giá ý nghĩa vẫn do Critic đảm nhiệm. Các chuyến đi, ngày tháng, số liệu người dùng, kết quả playtest, chi tiết code và tính năng chưa xác minh vẫn không được tự tạo thành sự kiện. Không suy ra tên hoặc quyền tác giả của một IP khác chỉ vì video có hình ảnh tương tự.

Bản viết cũ trong `runs/test1_surway` được giữ lại để đối chiếu. Thay prompt không tự viết lại một `article.json` cũ khi dùng `--resume`; cần tạo run mới để nhận giọng viết mới.
