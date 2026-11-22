# VietFrame Studio (v0.4) — Free-first local video workspace

Một ứng dụng biên tập video **thật** (không giả lập kết quả), thiết kế giao diện gọn, giống phần mềm biên tập hơn là các trang AI tạo hàng loạt.

> Đã bổ sung kiểm soát tác vụ, khôi phục khi gián đoạn, chống phụ đề lỗi và xem trước gốc/bản xuất. Trạng thái hiện tại: **MVP đang phát triển**, chưa phải website thương mại hoàn chỉnh. Đã có trang đăng nhập, tài khoản chủ sở hữu duy nhất và bảo vệ API bằng cookie phiên + CSRF. Chưa có quản lý nhiều người dùng, hóa đơn, tự gán font gốc 1:1 hay xóa chữ bằng AI.

## Có thể dùng ngay khi cài đủ thành phần

- Nhập URL công khai từ 6 nền tảng: Facebook, YouTube, TikTok, Douyin, Bilibili, Instagram qua **yt-dlp**. Tính khả dụng từng link có thể thay đổi theo nền tảng; không bypass nội dung riêng tư/DRM.
- Upload MP4/MOV/WEBM/MKV; xác minh nội dung video với `ffprobe`, giới hạn tối đa 350 MB và 30 phút.
- Quản lý dự án SQLite, tác vụ độc quyền theo dự án (chống bấm đúp/tranh chấp), khôi phục sau lỗi/khởi động lại, biên tập từng câu với timestamp, xuất `.srt`.
- Tùy chỉnh font, cỡ, màu, viền, đậm, vị trí; xuất video MP4 gắn phụ đề bằng FFmpeg+ASS. Unicode tiếng Việt được giữ nguyên.
- Gợi ý màu chữ từ vùng dưới của 1 khung video: **chỉ là gợi ý màu, KHÔNG nhận dạng font chính xác**.
- API tích hợp Whisper và Argos Translate offline: **chỉ hoạt động sau khi cài model / gói ngôn ngữ**.
- Nhánh tạo video AI chạy GPU với CogVideoX/Diffusers: chỉ chạy khi đã cài model/GPU; mặc định tắt, không giả kết quả.
- Dashboard báo công cụ nào thật sự có sẵn; không bật billing hay API trả phí.

## Chạy trên máy

Cần Python 3.11-3.13 và `ffmpeg` + `ffprobe` trong PATH.

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 8010
```

Mở **http://127.0.0.1:8010/login**. Lần đầu, điền email và tự đặt mật khẩu **tối thiểu 12 ký tự**; hệ thống tự khóa đăng ký tiếp theo. Những lần sau đăng nhập bằng tài khoản này. Không cần dịch vụ Google hay API trả phí.

Nếu muốn chạy Docker:

```bash
docker compose up --build
```

Mặc định chỉ mở cổng 8010 trên `127.0.0.1`; project/video và database tài khoản lưu ở `./workspace` và không commit vào Git. Khi chạy trong Docker, địa chỉ client có thể là gateway Docker thay vì `127.0.0.1`. Cách đơn giản, an toàn để tạo tài khoản đầu tiên trên Docker:

```bash
docker compose exec vietframe python -m app.auth create-owner
```

Lệnh hỏi email/mật khẩu trực tiếp trong terminal, **không gửi qua chat và không hiện mật khẩu ra màn hình**. Sau đó mở `/login` để đăng nhập. Nếu dùng giao diện tạo tài khoản đầu tiên từ mạng Docker/VM, đặt mã bí mật `VIETFRAME_SETUP_TOKEN` trong file `.env` (cùng thư mục `docker-compose.yml`) và nhập mã khi được yêu cầu. `docker-compose.yml` đã truyền biến môi trường này vào container; không công khai mã. Mẫu cấu hình: `.env.example`.

## Bật AI miễn phí (không dùng API trả phí)

```bash
pip install -r requirements-ai.txt
```

**Whisper:** khi sử dụng lần đầu, cần tải model `small` từ kho model công khai (tốn mạng/dung lượng), những lần sau chạy CPU offline.

**Argos Translate:** thư viện *không tự đi kèm mọi cặp ngôn ngữ*. Cần cài package ngôn ngữ (ví dụ `en → vi` hoặc `zh → en → vi` nếu model hỗ trợ); nếu không có gói phù hợp, backend trả lỗi rõ ràng.

**AI text-to-video local:** cần máy có CUDA GPU, `torch`, `diffusers`, model CogVideoX phù hợp, thiết lập `ENABLE_LOCAL_VIDEO_GEN=true`, VRAM và dung lượng tải model. Model và hiệu năng phụ thuộc phần cứng, có thể không dùng được trên GPU nhỏ. Mặc định tắt, tính năng không hề chạy ngầm.

**TTS giọng Việt:** có pipeline thực tế cho KokoroTTS OpenAI-compatible local server (POST `/v1/audio/speech`): tổng hợp từng câu, căn thời gian, ghép thành `dub.wav`, và thay âm thanh video khi xuất MP4. Chưa kiểm thử chất lượng giọng trên model được cài thực tế, chưa có lip-sync, chưa tách nhạc và thoại gốc, chưa phân biệt nhiều người nói. Cần bật KokoroTTS riêng, đặt `KOKORO_TTS_URL=http://127.0.0.1:7860` (trong Docker Compose dùng địa chỉ dịch vụ nội bộ); nguồn hướng dẫn: https://hangry-labs.github.io/kokoroTTS/docs/dockerhub.html. Giọng Việt thuộc pack riêng; chọn voice id từ `/tts/voices`. Không khai báo ElevenLabs miễn phí vĩnh viễn.

## Font giống video gốc

Mục tiêu sản phẩm là chuyển phụ đề gốc → phụ đề tiếng Việt cùng phong cách, nhưng **v0.4 chưa có nhận diện font tự động 1:1, OCR tracking, temporal inpainting**. Giao diện cho phép điều chỉnh font, màu, viền và xem bản render. Gợi ý màu có thể sai nếu hậu cảnh nhiều màu. Font phải được cài trên máy và hỗ trợ tiếng Việt.

## Quyền sử dụng và an toàn

Chỉ nhập video mà bạn có quyền tải/chỉnh sửa hoặc được chủ sở hữu cho phép. Không sử dụng để xóa watermark nhằm mạo nhận quyền tác giả. Không gửi mật khẩu, cookie Facebook hoặc key API qua giao diện.

**Chưa đủ điều kiện triển khai Internet công khai.** Bản v0.4 đã có xác thực một chủ sở hữu, băm PBKDF2, cookie HttpOnly/SameSite Strict, CSRF, khóa đăng ký sau tài khoản đầu tiên và chống brute force cơ bản. Khi đưa lên Internet cần HTTPS với `VIETFRAME_COOKIE_SECURE=true`, kiểm tra URL/redirect sâu hơn, chống SSRF toàn pipeline, giới hạn tác vụ/tải lên theo IP, backup database và file, giám sát chống lạm dụng, snapshot/restore và audit độc lập. Không chia sẻ tài khoản với nhiều người; dự án chưa tách biệt theo user. Docker expose local-only.

## API chính

`GET /api/health`, `GET /api/auth/config`, `POST /api/auth/setup`, `POST /api/auth/login`, `GET /api/auth/me`, `POST /api/auth/logout`, `POST /api/auth/change-password`, `GET /api/capabilities`, `GET /api/projects`, `POST /api/projects/upload`, `POST /api/projects/from-url`, `PUT /api/projects/{id}/segments`, `POST /api/projects/{id}/transcribe`, `POST /api/projects/{id}/translate`, `POST /api/projects/{id}/render`, `POST /api/projects/{id}/dub`, `GET /api/voices`, `GET /api/projects/{id}/file/{source|export}`, `GET /api/projects/{id}/subtitles.srt`, `GET /api/projects/{id}/reference-style`, `POST /api/ai/create-video`.

API docs (cần đăng nhập): http://127.0.0.1:8010/api/docs. Mọi API video đều đòi cookie phiên; các lệnh thay đổi yêu cầu header `X-CSRF-Token`, lấy từ `/api/auth/me`.

## Kiểm thử

```bash
pip install pytest httpx
pytest -q
```

Kiểm thử bao gồm xác thực/đăng xuất/đổi mật khẩu/khóa brute force/CSRF/quyền truy cập video, validate link, quyền sử dụng, upload thật, phụ đề Unicode, render FFmpeg và lỗi rõ ràng khi thiếu model. Chưa kiểm thử tải video từ 6 dịch vụ thật vì cần URL công khai hợp lệ và mạng. Đó là một phần nghiệm thu tích hợp, không được tuyên bố PASS khi chưa chạy.

## Roadmap có thứ tự

1. **MVP**: nhập nguồn → biên tập → gắn phụ đề → xuất MP4 (có code).
2. **Offline AI**: cài Whisper/Argos + giao diện sửa câu sau dịch, có job persistence.
3. **Original Style Match**: OCR kiểu chữ, tham chiếu font, bố cục, tracking, hỗ trợ dấu Việt.
4. **Vietnamese dubbing**: pipeline Kokoro local đã có, còn cần trộn riêng thoại/nhạc, hỗ trợ multi-speaker, đánh giá giọng thực tế và lip-sync.
5. **Frame inpainting**: xóa chữ gốc có kiểm soát và phép đo flicker/ghosting.
6. **Cinema**: image-to-video, storyboard, nhiều cảnh, nhất quán nhân vật, GPU worker.
7. **Production**: đăng nhập chủ sở hữu đã có ở v0.4; tiếp theo HTTPS, phân quyền nhiều người dùng, queues, object storage, CI, snapshots, restore, metrics và đánh giá bảo mật chuyên sâu.

Xem [docs/ACCEPTANCE.md](docs/ACCEPTANCE.md) để biết chuẩn nghiệm thu tránh tự chấm điểm quá lạc quan.

## Tài khoản và khôi phục

- Không có mật khẩu mặc định hoặc tài khoản cài sẵn. Tài khoản đầu tiên do chính chủ sở hữu tạo tại `/login`.
- Không mở đăng ký tự do; bản này chỉ hỗ trợ một người sử dụng vì các dự án chưa có trường user_id.
- Đổi mật khẩu trong **Hệ thống → Đổi mật khẩu**; thao tác này kết thúc toàn bộ phiên đăng nhập.
- Mất mật khẩu: quản trị viên có quyền máy chủ chạy `python -m app.auth reset-owner-password` (hoặc `docker compose exec vietframe python -m app.auth reset-owner-password`). Hệ thống yêu cầu mật khẩu mới trong terminal rồi thu hồi mọi phiên đăng nhập. Không có mật khẩu mặc định hoặc cửa hậu.
- Trên HTTPS, bắt buộc đặt `VIETFRAME_COOKIE_SECURE=true` và cấu hình reverse proxy chuyển scheme tin cậy.
