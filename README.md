# VietFrame Studio (v0.5) — Free-first local video workspace

Một ứng dụng biên tập video **thật** (không giả lập kết quả), thiết kế giao diện gọn, giống phần mềm biên tập hơn là các trang AI tạo hàng loạt.

> Đã bổ sung kiểm soát tác vụ, khôi phục khi gián đoạn, chống phụ đề lỗi và xem trước gốc/bản xuất. Trạng thái hiện tại: **MVP đang phát triển**, chưa phải website thương mại hoàn chỉnh. Đã có trang đăng nhập, tài khoản chủ sở hữu duy nhất và bảo vệ API bằng cookie phiên + CSRF. Chưa có quản lý nhiều người dùng, hóa đơn, tự gán font gốc 1:1 hay xóa chữ bằng AI theo chuyển động. Bản này có FFmpeg delogo theo vùng cố định và kết nối ElevenLabs bằng API key được mã hóa.

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

Mục tiêu sản phẩm là chuyển phụ đề gốc → phụ đề tiếng Việt cùng phong cách, nhưng **v0.5 chưa có nhận diện font tự động 1:1, OCR tracking, temporal inpainting**. Giao diện cho phép điều chỉnh font, màu, viền và xem bản render. Gợi ý màu có thể sai nếu hậu cảnh nhiều màu. Font phải được cài trên máy và hỗ trợ tiếng Việt.

## Quyền sử dụng và an toàn

Chỉ nhập video mà bạn có quyền tải/chỉnh sửa hoặc được chủ sở hữu cho phép. Không sử dụng để xóa watermark nhằm mạo nhận quyền tác giả. Không gửi mật khẩu, cookie Facebook hoặc key API qua giao diện.

**Chưa đủ điều kiện triển khai Internet công khai.** Bản v0.5 đã có xác thực một chủ sở hữu, băm PBKDF2, cookie HttpOnly/SameSite Strict, CSRF, khóa đăng ký sau tài khoản đầu tiên và chống brute force cơ bản. Khi đưa lên Internet cần HTTPS với `VIETFRAME_COOKIE_SECURE=true`, kiểm tra URL/redirect sâu hơn, chống SSRF toàn pipeline, giới hạn tác vụ/tải lên theo IP, backup database và file, giám sát chống lạm dụng, snapshot/restore và audit độc lập. Không chia sẻ tài khoản với nhiều người; dự án chưa tách biệt theo user. Docker expose local-only.

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
7. **Production**: đăng nhập chủ sở hữu đã có ở v0.5; tiếp theo HTTPS, phân quyền nhiều người dùng, queues, object storage, CI, snapshots, restore, metrics và đánh giá bảo mật chuyên sâu.

Xem [docs/ACCEPTANCE.md](docs/ACCEPTANCE.md) để biết chuẩn nghiệm thu tránh tự chấm điểm quá lạc quan.

## Tài khoản và khôi phục

- Không có mật khẩu mặc định hoặc tài khoản cài sẵn. Tài khoản đầu tiên do chính chủ sở hữu tạo tại `/login`.
- Không mở đăng ký tự do; bản này chỉ hỗ trợ một người sử dụng vì các dự án chưa có trường user_id.
- Đổi mật khẩu trong **Hệ thống → Đổi mật khẩu**; thao tác này kết thúc toàn bộ phiên đăng nhập.
- Mất mật khẩu: quản trị viên có quyền máy chủ chạy `python -m app.auth reset-owner-password` (hoặc `docker compose exec vietframe python -m app.auth reset-owner-password`). Hệ thống yêu cầu mật khẩu mới trong terminal rồi thu hồi mọi phiên đăng nhập. Không có mật khẩu mặc định hoặc cửa hậu.
- Trên HTTPS, bắt buộc đặt `VIETFRAME_COOKIE_SECURE=true` và cấu hình reverse proxy chuyển scheme tin cậy.


## Mới v0.5: Che chữ/logo rồi chèn phụ đề tiếng Việt

- Mở Bàn biên tập → **Che chữ/logo** → chọn sẵn **Vùng phụ đề dưới** hoặc **Logo góc trên**, điều chỉnh X/Y/rộng/cao theo % khung hình. Bấm **Thêm vùng che**, tối đa 3 vùng, rồi **Lưu vùng che và xuất lại**; cuối cùng bấm **Xuất MP4**.
- Hệ thống chạy FFmpeg `delogo` trên video nguồn **trước** khi ghi phụ đề ASS tiếng Việt; không để dải màu mờ phủ lên chữ mới. Có xem trước vị trí vùng lựa chọn bằng khung nét đứt.
- `delogo` chỉ nội suy điểm ảnh xung quanh, không phải xóa chữ hoàn hảo bằng generative AI. Vùng quá lớn, chồng lên người/vật thể hoặc chữ chuyển động có thể méo, cần chỉnh vùng theo cảnh. Phiên bản này không nhận diện font gốc bằng AI hay tracking tự động.
- Tạo/giữ phong cách font (màu, viền, cỡ, đậm và vị trí); font 1:1 phụ thuộc font gốc có sẵn và hỗ trợ dấu tiếng Việt.

## Mới v0.5: Liên kết ElevenLabs 1 lần

ElevenLabs REST API sử dụng **API key** chứ không cho VietFrame tái sử dụng tự động cookie đăng nhập ChatGPT/Google hay mật khẩu ElevenLabs. Trong trang **Cài đặt** → **Liên kết ElevenLabs**:

1. Vào https://elevenlabs.io/app/settings/api-keys đăng nhập ElevenLabs và tạo API key với quyền Voices, Text to Speech, User/Subscription theo chính sách ElevenLabs.
2. Dán key **trực tiếp vào trang VietFrame của bạn** và bấm **Liên kết tài khoản**. Không đưa key vào chat, GitHub, URL, frontend build hoặc log.
3. Từ lần đăng nhập VietFrame tiếp theo, server tự dùng key mã hóa đã lưu, bạn có thể chọn **ElevenLabs đã liên kết**, chọn giọng khả dụng và bấm **Lồng tiếng**. Mỗi dự án vẫn chọn giọng theo ý thích; có nút **Ngắt kết nối** trong Cài đặt.

Bảo mật: lưu key Fernet mã hóa trong SQLite; key mã hóa đặt trên volume local (`workspace/.credential-encryption-key`, permission 0600). Trên hosting, đặt `VIETFRAME_CREDENTIAL_ENCRYPTION_KEY` qua secret manager để mã hóa không phụ thuộc đường dẫn volume. Các API ElevenLabs gọi từ server, không trả secret cho trình duyệt.

**Free-First cứng:** trước mỗi lượt tạo âm thanh, server đọc gói và quota từ ElevenLabs. Chỉ chấp nhận tier `free` khi xác minh đủ số ký tự còn lại; không tự tiêu tiền từ tài khoản trả phí. Gói Free có hạn chế giọng qua API, đôi lúc không có voice tương thích: lúc đó báo lỗi, không sinh file giả. Nhiều đoạn chạy nối tiếp vẫn có rủi ro quota bị dùng bởi một thiết bị khác giữa lúc kiểm tra; lỗi được báo. Đây là TTS dựng từ nội dung dịch, **không phải voice cloning/lip sync** của người nói gốc.

Endpoints mới: `PUT /api/projects/{id}/cleanup`, `GET /api/integrations/elevenlabs`, `POST /api/integrations/elevenlabs/link`, `DELETE /api/integrations/elevenlabs`, `GET /api/integrations/elevenlabs/voices`. `POST /api/projects/{id}/dub` nhận thêm `provider: kokoro | elevenlabs`.

Vẫn chạy local-only. Trước khi mở website trên Internet cần kiểm tra HTTPS, reverse proxy và cấu hình session/secret theo môi trường triển khai.
