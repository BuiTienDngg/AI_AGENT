# Codex Game SEO Office v1.1 — Word EN/VI + Token Usage (không gọi API model)

**Văn phong:** viết bằng hành động, quy luật và kết quả dễ hình dung; bản VI diễn đạt tự nhiên thay vì dịch sát chữ. Giữ vai trò đội phát triển Slope3, nhưng không lặp ý đồ thiết kế ở mọi đoạn. Xem [quy tắc viết và ví dụ trước/sau](WRITING_STYLE.md) và [định hướng nội dung](EDITORIAL_DIRECTION_VI.md).

**Cập nhật 21/10/2026:** caption/alt ảnh theo nội dung minh họa hoặc H3/H2; Analyze lập danh sách đối tượng chi tiết và tự mở form bổ sung khi thiếu/chưa chắc. Xem [cách dùng caption và form đối tượng](CAPTIONS_AND_OBJECT_REVIEW_VI.md).

**Giọng nội dung hiện tại:** bài giới thiệu chính thức từ đội phát triển Slope3, theo xác nhận của chủ dự án. Mạch chính: bối cảnh thực tế có nguồn -> ý tưởng sản phẩm của chúng tôi -> quyết định thiết kế -> trải nghiệm người chơi. Xem [định hướng nội dung](EDITORIAL_DIRECTION_VI.md). Cấu hình vai trò và ủy quyền concept nằm trong `config.json`; mỗi lượt Codex nhận `brand_context.json` riêng.

**Mục tiêu:** chỉ nhập video gameplay MP4, chạy một câu lệnh và nhận **đúng 2 file Word: EN (en-US) và VI (vi-VN)**. Bản VI dịch từ bài EN đã duyệt, dùng chung nghiên cứu, nguồn và ảnh. Không sử dụng n8n, API key của GPT/Gemini/Groq/OpenRouter hoặc Llama local. Codex CLI chạy bằng tài khoản ChatGPT đã đăng nhập; vẫn tính vào hạn mức Codex của tài khoản.

**Đầu ra từ 21/10/2026:** thư mục `output/` chỉ tạo hai `.docx`, không tạo bài HTML/Markdown hoặc sao chép thêm `assets/`. File nội bộ JSON và báo cáo token vẫn được giữ để truy vết nguồn, kiểm tra và chạy tiếp. Bỏ định dạng xuất giúp gọn file; HTML/Markdown vốn do Python tạo nên gần như không tiết kiệm token AI. Muốn xuất lại bài đã có mà không viết lại, dùng `python run.py export --run-dir ".\runs\ten_bai"`; bản dịch có SHA khớp sẽ được dùng lại, không gọi thêm Codex.

## Dùng nhanh cho người không viết code

**Biên tập nội dung:** phần Ý tưởng và cảm hứng dùng giọng mềm mại, giàu liên tưởng nhưng nối ý rõ; Gameplay giải thích mục tiêu, luật thành công/thất bại và hậu quả đã xác nhận; Điểm nổi bật nêu khác biệt cụ thể và lợi ích người chơi. Luật chưa rõ được hỏi chủ game, không tự bịa phần thưởng/hình phạt. Tên, hình dáng và vai trò đối tượng có bản dịch VI cạnh bản gốc; bản dịch chỉ phục vụ hiển thị và không biến suy đoán thành xác nhận.

**Bộ đăng site:** sau khi xuất bài thành công, mở thư mục result trong lượt chạy. Có hai Word EN/VI, ảnh dùng trong bài được đặt tên theo caption, bảng đối chiếu tên ảnh EN/VI và nguồn/giấy phép. Trên admin có nút **Bộ đăng site (.zip)**. Không gọi thêm AI để tạo bộ này.

**Codex Accounts + quota policy:** theo dõi tại /accounts, thiết lập admin tại /admin. Có hàng đợi bền vững và API dự phòng tùy chọn; cần admin chọn hồ sơ chính và bật policy. Xem [cấu hình, API, migration và giới hạn](CODEX_CAPACITY_VI.md).

Nhấp đúp **CAI_DAT.bat** để cài lần đầu, sau đó **CHAY_ADMIN.bat** để chạy và tự mở trang quản trị. Xem [hướng dẫn nhấp đúp và thư mục output](HUONG_DAN_NHANH.md). Lượt admin mới lưu theo tên game + ngày-tháng-năm + giờ-phút-giây.

## Yêu cầu cài đặt (Windows, PowerShell / VS Code)

1. Python 3.10+, [FFmpeg](https://ffmpeg.org/download.html) (cả `ffmpeg` và `ffprobe` nằm trong PATH), Codex CLI. Để cài Codex CLI từ npm (cần Node.js):

   ```powershell
   npm install -g @openai/codex
   codex
   ```

   Chọn **Sign in with ChatGPT** rồi đăng nhập theo hướng dẫn. KHÔNG cần tạo hoặc nạp OpenAI API key. Codex CLI phải dùng được từ terminal PowerShell; chỉ cài Codex extension trong VS Code chưa bảo đảm lệnh `codex` khả dụng trên PATH.

2. Giải nén ZIP, mở thư mục `Codex_Game_SEO_Office_v1` trong VS Code. Trong Terminal:

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install -r requirements.txt
   python run.py doctor
   ```

   Nếu PowerShell chặn Activate.ps1, có thể gọi trực tiếp `.venv\Scripts\python.exe` thay `python`.

3. Đặt video MP4 ở một đường dẫn bất kỳ, ví dụ `D:\Videos\subway.mp4`.

4. Chạy:

   ```powershell
   python run.py run --video "D:\Videos\subway.mp4"
   ```

   Hoặc chỉ định thư mục đầu ra để có thể chạy tiếp khi cần:

   ```powershell
   python run.py run --video "D:\Videos\subway.mp4" --out ".\runs\subway"
   ```

Bạn cũng có thể chạy nhanh bằng PowerShell: `./start_windows.ps1 -Video "D:\Videos\subway.mp4" -Out ".\runs\subway"`.

## Các bước tự động

```text
MP4
  └─ FFprobe + FFmpeg: lấy 16 khung hình trải đều, tạo 2 contact sheets
        └─ Codex Vision: game, cơ chế quan sát được, nội dung chưa xác nhận
              └─ Python Internet Research: Wikipedia, OpenAlex
              └─ Python Wikimedia Commons: 2 ảnh, kiểm tra license + lưu tác giả/link
                    └─ Codex Evidence Notes: claim/source_id/đoạn chứng minh
                          └─ Codex Writer: 6 mục en-US, chỉ dùng source_id
                                └─ Codex Critic + Python QA
                                      ├─ PASS → Codex TRANSLATE EN → VI
                                      │              ├─ Kiểm tra 6 Heading VI, source_id, ảnh và thứ tự đoạn
                                      │              └─ Xuất 2 Word: DOCX EN + DOCX VI
                                      └─ FAIL → Codex sửa *chỉ những đoạn lỗi*, tối đa 2 vòng
                                                   └─ FAIL → dừng, giữ qa_report.json

Mỗi lần gọi Codex đều ghi usage input/output vào `token_usage.json`; cuối bài in tổng và tạo `token_usage.md`.
```

**Chỉ dùng Codex CLI để gọi model.** Python gọi các API web công khai không yêu cầu khóa (Wikipedia/MediaWiki, OpenAlex và Wikimedia Commons); các dịch vụ này cần Internet và có thể áp dụng rate limit, bảo vệ bot hoặc thay đổi API. Không có bảo đảm luôn thành công trên mọi video hoặc mọi ngày.

## Kiến trúc file

| File/thư mục | Chức năng |
|---|---|
| `run.py` | CLI điều phối toàn bộ |
| `config.json` | Cấu hình số frame, ảnh, QA, model Codex |
| `AGENTS.md` | Luật cố định: en-US, giọng publisher Slope3, chống bịa nguồn |
| `prompts/` | Prompt phân tích, lập Evidence Notes, Writer, Critic, Repair |
| `schemas/` | JSON Schema bảo đảm kết quả Codex có cấu trúc |
| `game_seo/video.py` | FFprobe/FFmpeg + contact sheets |
| `game_seo/research.py` | Search OpenAlex/Wikipedia, Commons license, tải ảnh |
| `game_seo/runner.py` | `codex exec --json`, đối chiếu nguồn, sửa đoạn và dịch EN→VI |
| `game_seo/translation.py` | Đối chiếu cấu trúc bản dịch, không cho mất citation/ảnh |
| `game_seo/usage.py` | Thống kê input, cached input và output token từ Codex CLI |
| `game_seo/qa.py` | Gate heading, citation/source_id, ảnh, source coverage |
| `game_seo/export.py` | Hai DOCX EN/VI có ảnh nhúng, trích dẫn và nguồn ảnh |
| `runs/<game>/` | Phân tích, registry, bài viết, QA, logs và output |

## File kết quả

- `output/<game>_slope3_en_US.docx` — Word có tiêu đề và Heading thật, citation đậm-nghiêng **8 pt**, chú thích ảnh, References và Image Credits.
- `output/<game>_slope3_vi_VN.docx` — Word tiếng Việt dịch từ bài EN đã duyệt, có chú thích ảnh, Tài liệu tham khảo và Nguồn ảnh; **không chạy lại Research**.
- Ảnh được nhúng trong hai file Word; không cần thư mục ảnh đi kèm khi gửi bài. Các file xuất từ lượt cũ được giữ nguyên, không tự xóa.
- `sources.json`, `images.json`, `research_notes.json`, `analysis.json` — dữ liệu nội bộ để truy vết nguồn; `sources.json` còn ghi HTTP status để kiểm tra link (403/bot-block không đồng nghĩa DOI bịa).
- `qa_report.json` — báo cáo pass/fail và đường dẫn từng đoạn lỗi.
- `rejected_notes.json` — claims có source_id/đoạn dẫn chứng không khớp bản ghi được bác bỏ.
- `translation_vi.json`, `translation_qa.json`, `translation_provenance.json` — bản dịch, kiểm tra tính nhất quán và dấu vân tay bản EN.
- `token_usage.json` — số token theo từng lần gọi / Agent, tổng input/output/cache; `token_usage.md` — báo cáo dễ đọc.
- `logs/codex_<stage>_NNN.jsonl` và `.stderr.log` — nhật ký Codex theo từng lượt, không ghi đè log Critic hoặc Repair.

**Không có Google Docs API** trong bản local đầu tiên. Bạn có thể import `.docx` lên Google Drive/Google Docs thủ công. Không tự đăng lên website hay Google Drive.

## Quy tắc nguồn & nguồn cảm hứng

- **Ý tưởng văn hóa:** AI tự nghiên cứu và tự phát triển góc viết, không hỏi bạn nhập ý tưởng. Nhưng không nhận những suy luận đó là sự kiện lịch sử có thật trong quá trình phát triển trò chơi.
- **Gameplay:** chỉ mô tả điều thấy rõ qua khung hình; không tự bịa tên nhân vật, chức năng power-up, mobile support, PC mappings hoặc công nghệ backend.
- **Trích dẫn văn bản:** tối thiểu 4 URL văn bản khác nhau và 6 lượt trích dẫn. Để tránh source bịa, mô hình chỉ đưa `[[SRC001]]`; Python chuyển thành `[1]` và điền URL duy nhất từ `sources.json`.
- **Research claim:** câu "research shows..." phải kèm trích dẫn học thuật có abstract/excerpt, không dẫn nguồn từ ảnh tư liệu.
- **Ảnh:** phải có 2 ảnh Wikimedia Commons trong Concept and Inspiration và 4 frame gameplay ở các mục phù hợp. Ảnh được ghi công riêng; ảnh chỉ dùng khi metadata license rõ ràng (CC BY, CC BY-SA, CC0/Public Domain). Bạn cần kiểm tra nghĩa vụ attribution và ShareAlike tương ứng trước khi xuất bản thương mại.
- **QA:** Validator kiểm tra ID nguồn, đủ trích dẫn, cấu trúc và ảnh; Codex critic kiểm tra ngữ nghĩa. Bộ kiểm tra tự động **không thể bảo đảm 100% rằng tài liệu thật sự ủng hộ mọi nhận định**. Bạn nên duyệt bài trước khi đăng lên website.

Nếu video không có logo và Codex đoán sai tên game, có thể thêm tùy chọn **không bắt buộc** `--game-title "Subway Surfers"`.

## Chạy tiếp sau lỗi

Nếu Codex thất bại do mạng/hạn mức, sau khi khắc phục chạy:

```powershell
python run.py run --video "D:\Videos\subway.mp4" --out ".\runs\subway" --resume
```

`--resume` sử dụng lại ảnh, nguồn, bản thảo đã tồn tại; chạy lại review/QA. Nếu muốn AI viết lại toàn bộ từ đầu, dùng thư mục output mới hoặc xóa `article.json` trong run folder.

Để chạy QA độc lập sau khi chỉnh `article.json`:

```powershell
python run.py qa --run-dir ".\runs\subway"
```

Xuất lại từ bản thảo đã đạt QA và đã được Codex Critic duyệt (nếu bản EN thay đổi, bản dịch VI sẽ được cập nhật):

```powershell
python run.py export --run-dir ".\runs\subway"
```

## Điều chỉnh

`config.json` gồm:
- `frames_per_video`: 16 khung hình (tăng 24–32 nếu gameplay đổi cảnh nhanh; chi phí Codex tăng).
- `frames_in_article`: 4, `commons_images`: 2.
- `min_text_sources`: 4, `min_citation_mentions`: 6.
- `max_repair_rounds`: 2 (sửa từng đoạn EN chưa đạt).
- `max_translation_attempts`: 2 (dịch lại nếu bản VI sai cấu trúc/trích dẫn/ảnh).
- `codex_model`: để rỗng để CLI dùng model được cài đặt; hoặc điền model có hỗ trợ ảnh và xuất JSON.
- `network_timeout_seconds`: 20.

Các mô hình Codex/hạn mức tùy thuộc tài khoản và cấu hình của bạn. Mỗi giai đoạn (`analyze`, `notes`, `draft`, `critique`, `repair`, `translate`) là một lần `codex exec --json`; một bài thường có ít nhất **5 lần** gọi và thêm các vòng review/repair, dịch lại nếu cần. Token sẽ được **đo từ sự kiện usage của Codex CLI**, không ước lượng toàn bộ bằng độ dài bài viết.

## Kiểm thử project

```powershell
python -m unittest discover -s tests -v
```

Các test mô phỏng (không dùng Internet hay Codex quota) kiểm tra ảnh/nguồn, hình thức đánh số citation, patch chỉ một đoạn, lỗi nguồn giả, hai Word EN/VI và tái sử dụng bản dịch khi xuất lại. Để kiểm tra bằng một video thật, cần cài Codex CLI, có quota và cho phép kết nối Internet.

## Giới hạn cần biết

1. Với video dài hoặc các cơ chế xuất hiện rất ngắn, lấy 16 ảnh tĩnh có thể bỏ sót chi tiết; nên tăng frames hoặc bổ sung bước phân tích cảnh chuyên biệt ở phiên bản sau.
2. Bản hiện tại tìm nguồn văn bản từ Wikipedia và OpenAlex; **chưa có một web crawler đa nguồn hỗ trợ đầy đủ các báo, forum, website game và công cụ tìm kiếm thương mại**. Vì vậy có thể không đạt 4 nguồn chất lượng cho một số game — chương trình sẽ dừng thay vì bịa nguồn.
3. Các bài mẫu trong `runs/` đã được chạy bằng tài khoản Codex CLI trên máy này. Video hoặc nguồn web khác vẫn có thể gặp giới hạn dịch vụ; kiểm tra QA và logs của từng lượt.
4. Codex dùng tài khoản ChatGPT không cần OpenAI API key nhưng **vẫn phụ thuộc dịch vụ Codex, hạn mức và kết nối mạng**; không phải local offline AI.

## Quy trình hai Word và báo cáo token

### Quy trình EN → VI

1. Chỉ bài **en-US** vượt qua cả Python QA lẫn Codex Critic mới được đưa đi dịch.
2. Codex dịch bản EN hoàn chỉnh sang VI; không tự tìm nguồn, thêm tính năng, thay đổi nội dung hay trích dẫn.
3. Python kiểm tra chính xác **6 Heading**, số mục/phân mục/đoạn, thứ tự `[[SRC001]]` và danh sách `IMG###`/`FRAME###` của từng đoạn. Nếu dịch sai, thử lại tối đa `max_translation_attempts`. Không đạt thì **không xuất Word**.
4. Hai file Word dùng cùng registry nguồn gốc; ảnh được nhúng trực tiếp. Citation hiển thị `[1]`, `[2]` bằng chữ đậm nghiêng 8 pt. Bản tiếng Việt dùng nhãn **Hình**, **Tài liệu tham khảo**, **Nguồn ảnh** và mã ngôn ngữ `vi-VN`.
5. Xuất lại dùng bản dịch đã xác thực nếu EN chưa đổi; không cần chạy lại phân tích, nghiên cứu, viết bài hoặc dịch. Không tự xóa đầu ra cũ.

### Token sau mỗi bài

Mỗi lượt Codex CLI chạy với `--json` để thu `turn.completed.usage` (nếu phiên bản CLI hỗ trợ). Sau mỗi lần gọi, hệ thống ghi vào `token_usage.json` và khi hoàn thành (hoặc dừng vì lỗi) in tổng:

```text
Codex usage (complete): 6/6 calls measured; input 63,000, output 14,000, total 77,000 tokens (cached input 9,000 included in input).
  analyze: ...
  notes: ...
  draft: ...
  critique: ...
  translate: ...
Reports: token_usage.json, token_usage.md
```

**Con số trên chỉ minh họa, không phải kết quả đã chạy thực tế.** Input đã bao gồm cached input; không cộng cache thêm lần nữa. Nếu CLI không trả usage, báo cáo ghi `partial` hoặc `unavailable`, cho biết số lượt thiếu thay vì bịa tổng token. Lượt gọi Python tới Wikimedia/OpenAlex **không tiêu tốn model token**. Token đã dùng không quy đổi trực tiếp thành phần trăm hạn mức gói ChatGPT hay chi phí đô la.

Xem lại sau bằng:

```powershell
python run.py usage --run-dir ".\runs\subway"
```

`--resume` giữ dữ liệu usage đã đo trước đó và cộng thêm những lượt Codex phát sinh sau khi chạy tiếp. Nếu sửa bản EN đã duyệt, bước dịch sẽ kiểm tra SHA-256 của `article.json`, không tái sử dụng bản dịch cũ.

**Lệnh run** .\start_windows.ps1 -Video "C:\Users\green\Downloads\Video Project 8.mp4" -Out ".\runs\video_project_8_optimized"
