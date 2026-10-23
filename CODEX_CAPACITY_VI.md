# Codex Accounts, quota policy và hàng đợi trên Windows

## Bắt đầu sử dụng

1. Chạy **CHAY_ADMIN.bat**, mở http://127.0.0.1:8765/admin. Lần đầu tự đặt mật khẩu administrator riêng, tối thiểu 12 ký tự. Đây không phải mật khẩu ChatGPT. Mật khẩu lưu dưới dạng hash; session hết hạn sau một giờ.
2. Thêm hồ sơ Codex đã đăng nhập. Để trống CODEX_HOME để dùng hồ sơ hiện tại. Không nhập mật khẩu ChatGPT, OAuth token hoặc API key vào form hồ sơ Plus.
3. Trong **Quota Policy**, chọn đúng một hồ sơ Plus chính, kiểm tra số đo, rồi bật **policy và hàng đợi**. Policy mặc định tắt để không làm gián đoạn cách chạy cũ trước khi admin cấu hình.
4. Tab **Codex Accounts** tại /accounts cho phép người dùng local theo dõi. Thêm/sửa/xóa, policy, provider và audit log chỉ thực hiện sau khi đăng nhập tại /admin, có kiểm tra quyền ở backend.
5. Ctrl+F5 sau khi cập nhật. Không cần thư viện Python mới. Giám sát chạy trong thread Python của local_admin.py, không cần khởi chạy một service khác.

## Kiến trúc và tích hợp

Giữ Flask + Waitress, HTML/CSS/JavaScript thuần, sqlite3, CSRF token và kiểm tra host/origin hiện có. Project không có ORM hoặc framework migration trước đó; bổ sung migration SQL có version, chạy trong transaction và ghi schema_migrations.

Giữ workflow analyze → nghiên cứu → notes → hỏi chủ game → draft → QA/repair → dịch VI → xuất đúng 2 Word. Jobs vẫn dùng ProcessTree/Windows JobObject để quản lý toàn bộ cây subprocess. Admission được chèn trước khi khởi chạy worker; không đổi provider giữa một lời gọi model đang chạy.

Job mới chụp đầu vào vào thư mục runs theo tên game và thời gian. Khi policy bật, nếu worker đang bận thì job vào QUEUED; nếu tài nguyên thiếu thì WAITING_FOR_CAPACITY. Monitor đánh giá lại sau mỗi chu kỳ, có thời điểm next_retry lưu trong DB. Mỗi lần chỉ chạy một worker. Có thể hủy bài đang chờ từ cửa sổ chi tiết bài.

Job chờ tồn tại sau restart. Job RUNNING khi backend bị đóng chuyển INTERRUPTED, cần người dùng bấm Chạy tiếp. Không tự gửi lại một lời gọi model dang dở vì không biết phía provider đã tính phí hoặc xử lý đến đâu. Tiếp tục từ checkpoint đã ghi; checkpoint không bảo đảm chính xác-một-lần cho lời gọi model chưa hoàn tất.

API tạo bài nhận Idempotency-Key hoặc idempotency_key trong JSON. Gửi lại cùng key trả cùng job, không tạo bài mới. UI giữ key khi thử lại sau lỗi mạng. Key gắn với game; không dùng lại cho game khác.

## Policy và ước lượng

- Warning: 20%; minimum: 13%; safety margin: 20%; interval: 60 giây.
- Độ mới mặc định tối đa: 180 giây. Thiếu hoặc sai schema: UNKNOWN. Cũ, timestamp bất thường hoặc reset đã qua mà chưa có quan sát mới: STALE.
- Kiểm tra cả 5 giờ và tuần. Không tự cộng lại quota thành 100% sau giờ reset.
- Ưu tiên account/rateLimits/read của Codex App Server. Khi không đọc được, adapter quota_jsonl.py thử tối đa 30 session log gần nhất, đọc tối đa 2 MB cuối mỗi file. Timestamp của quan sát log được giữ nguyên; không dùng giờ quét làm giờ số đo.
- Thống kê lưu input, cached input, output, total, thời gian các lời gọi AI, kết quả và chênh lệch quota đo được. Cached input là tập con của input, không cộng hai lần.
- Dùng tối đa 20 bài hoàn thành gần nhất cùng provider/model và có số đo phù hợp. Khi có ít nhất 3 mẫu, dùng mức lớn nhất đã quan sát theo từng cửa sổ rồi nhân safety margin. Không suy % quota từ token.
- Khi chưa đủ mẫu: dự phòng 20 điểm phần trăm; với margin mặc định cần 24 điểm ở cả hai cửa sổ, đồng thời không thấp hơn minimum. Đây là policy thận trọng của ứng dụng, không phải cam kết đủ cho một bài.
- Các bài cũ chưa có assignment không tự gán cho một tài khoản để tránh thống kê sai. Các bài đã đổi provider hoặc model không dùng để huấn luyện ước lượng quota Plus. Số đo toàn tài khoản có thể gồm hoạt động Codex khác, nên ước lượng có sai số.

## API dự phòng được phép

Trong /admin, thêm **API provider**: tên, model ID API thực sự hỗ trợ, API key, priority, ngân sách token/job và trạng thái enabled. Cần bật riêng **Cho phép API dự phòng có tính phí** trong policy. Provider ưu tiên số nhỏ được kiểm tra trước. Không cấu hình API vẫn có thể dùng hoàn toàn bằng Plus; thiếu quota thì chờ.

Hiện hỗ trợ **OpenAI Responses API qua custom provider của Codex CLI**, endpoint cố định https://api.openai.com/v1, không qua 9Router. Model API có thể khác model Plus; admin phải nhập ID phù hợp, bao gồm khả năng xem ảnh và structured outputs mà workflow cần. Không yêu cầu key để dùng Plus. Chưa có adapter Local hoặc provider bên thứ ba.

API key được Windows DPAPI mã hóa theo Windows user và lưu ciphertext trong secure_values. Không trả lại key qua API/UI; khi sửa, để trống để giữ key cũ. Key chỉ được giải mã trong bộ nhớ và truyền qua biến môi trường của worker. Có lọc secret khỏi log và loại biến GAME_SEO_API_KEY khỏi môi trường shell của agent. Session signing key cũng được DPAPI bảo vệ; không sao chép DB sang tài khoản Windows khác rồi mong giải mã được secret cũ.

Nút **Kiểm tra** chỉ gọi metadata model, không tạo bài hoặc gọi model sinh nội dung. Metadata thành công chưa chứng minh tài khoản có đủ billing balance. Nếu probe lỗi, giữ job chờ và đánh giá lại sau chu kỳ. Nếu lời gọi model thật lỗi, job FAILED, provider ERROR; người dùng kiểm tra và bấm Chạy tiếp từ checkpoint. Không retry vô hạn một lời gọi có thể đã tính phí.

Ngân sách token API được kiểm tra **giữa các stage** theo usage đã đo. Không phải hard cap hóa đơn: một stage có thể vượt phần ngân sách còn lại; usage thiếu làm việc đo không đầy đủ. Nên đặt giới hạn chi tiêu phía tài khoản API nếu cần trần chi phí cứng.

## Migration và dữ liệu

migrations/001_capacity.sql chạy tự động, không đổi/xóa các bảng game, revision hoặc bài cũ.

| Bảng/view | Vai trò |
|---|---|
| schema_migrations | Version migration |
| codex_accounts, quota_snapshots | View tương thích trên codex_profiles và codex_profile_samples hiện có |
| provider_configs | API provider và trạng thái kết nối |
| capacity_settings | Policy và một hồ sơ Plus chính |
| workflow_usage | Token, thời gian, quota delta, kết quả |
| job_assignments | Phân công provider, trạng thái, lần thử, thời điểm đánh giá lại |
| job_request_keys | Idempotency của yêu cầu tạo bài |
| account_audit_logs | Admin setup/login/logout, CRUD tài khoản/provider, thay đổi policy |
| admin_auth, secure_values | Password hash và dữ liệu mã hóa DPAPI |

Index theo profile/thời gian, provider/kết quả và trạng thái/lần đánh giá lại. Mỗi hồ sơ giữ tối đa 100 số đo gần nhất. Xóa hồ sơ không xóa thư mục đăng nhập hay output bài; không xóa được hồ sơ chính khi policy còn bật hoặc provider đang chạy job.

## API

Các API dưới đây chỉ phục vụ loopback, dùng host/origin/CSRF hiện có. Endpoint sửa đổi còn yêu cầu session administrator.

| Method | Endpoint | Quyền |
|---|---|---|
| GET | /api/codex/accounts | Local viewer, không trả CODEX_HOME |
| GET | /api/codex/accounts/{id} và /quota | Local viewer |
| GET | /api/codex/accounts/{id}/history | Quota và lịch sử workflow |
| GET | /api/codex/monitor/status | Trạng thái monitor và policy |
| GET | /api/codex/jobs | Assignments và usage |
| POST | /admin/auth/setup, /login | Bootstrap một lần / đăng nhập; cần CSRF |
| POST | /admin/auth/logout | Admin |
| GET, POST | /admin/api/accounts | Admin |
| PUT, PATCH, DELETE | /admin/api/accounts/{id} | Admin |
| POST | /admin/api/accounts/refresh | Admin |
| PUT | /admin/api/policy | Admin |
| POST | /admin/api/providers | Admin |
| PATCH, DELETE | /admin/api/providers/{id} | Admin |
| POST | /admin/api/providers/{id}/check | Admin |
| GET | /admin/api/audit | Admin |

Route quản trị theo convention hiện tại /admin/api thay vì tạo thêm /api/admin trùng chức năng. Có thể xem log bài trong cửa sổ chi tiết workflow của thư viện game; assignments và lịch sử quota hiển thị ở dashboard.

## File và kiểm thử

Tạo: migrations/001_capacity.sql; game_seo/capacity_db.py, admin_auth.py, secret_store.py, quota_policy.py, quota_jsonl.py, capacity_service.py; admin_ui/admin_login.html, static/admin_login.js; tests/test_capacity.py; tài liệu này.

Sửa: account_monitor.py, account_web.py, admin_jobs.py, admin_web.py, runner.py, admin_worker.py; index.html, accounts.html, static/accounts.js, static/accounts.css, static/app.js; tests/test_account_monitor.py; tools/check_accounts_ui.py; README_VI.md và LOCAL_ADMIN_VI.md.

Chạy kiểm thử:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
.\.venv\Scripts\python.exe tools\check_accounts_ui.py
.\.venv\Scripts\python.exe tools\check_admin_ui.py
```

Test API dùng credential mô phỏng, mock mạng và subprocess; không tạo nội dung có tính phí. Báo cáo/screenshot tại maintenance_history/accounts_validation và admin_ui_validation. Kiểm thử thật từ đầu đến cuối với API trả phí cần admin tự cấu hình key/model và bật dự phòng; chưa thực hiện trong lần triển khai này.

Tài liệu chính thức đã đối chiếu: [Codex App Server](https://learn.chatgpt.com/docs/app-server), [provider và env_key](https://learn.chatgpt.com/docs/config-file/config-reference), [CODEX_HOME](https://learn.chatgpt.com/docs/config-file/config-advanced).

Kết quả triển khai 23/10/2026: bộ kiểm thử Python và hai bộ browser QA đạt; pip check và compileall đạt. Số lượng bản ghi game, job, revision và câu trả lời trước/sau migration không đổi. Báo cáo chi tiết tại maintenance_history/capacity_validation.json; có bản backup SQLite trước migration trong maintenance_history/capacity_deploy_20261023_091914/.
