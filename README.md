# VietFrame Studio (v0.9) — Free-first local video workspace

Một ứng dụng biên tập video **thật** (không giả lập kết quả), thiết kế giao diện gọn, giống phần mềm biên tập hơn là các trang AI tạo hàng loạt.

> Đã bổ sung kiểm soát tác vụ, khôi phục khi gián đoạn, chống phụ đề lỗi và xem trước gốc/bản xuất. Trạng thái hiện tại: **MVP đang phát triển**, chưa phải website thương mại hoàn chỉnh. Đã có trang đăng nhập, tài khoản chủ sở hữu duy nhất và bảo vệ API bằng cookie phiên + CSRF. Chưa có quản lý nhiều người dùng, hóa đơn, tự gán font gốc 1:1 hay xóa chữ bằng AI theo chuyển động. Bản này có xóa phụ đề sát nét chữ trắng/vàng theo thời điểm bằng OpenCV và chế độ FFmpeg delogo cho logo nhỏ, cùng kết nối ElevenLabs bằng API key được mã hóa. Không bảo đảm xóa không dấu vết trên mọi hậu cảnh.

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

## Xóa đúng nét chữ thay vì làm mờ cả dải (v0.6)

- Tối đa 80 vùng theo thời gian với vị trí `% x/y/w/h`, `start`, `end`, `method` (`glyph` hoặc `edge`).
- Giới hạn cứng mỗi vùng: **không quá 9% tổng diện tích hoặc 12% chiều cao**. Bộ preset che 88% chiều ngang và 17% chiều cao của bản cũ bị loại bỏ.
- `glyph`: OpenCV chỉ tìm cụm pixel sáng trắng/vàng trong khu vực nhỏ, lấy thêm viền đậm lân cận rồi inpaint bằng Telea. Những pixel bên ngoài vùng chọn và ngoài thời gian chọn không bị sửa trong bước làm sạch. Nếu toàn clip không phát hiện chữ cần xóa, **render trả lỗi thay vì giả thành công**.
- `edge`: FFmpeg delogo nhỏ, có thời điểm bắt đầu/kết thúc, chỉ dùng trên nền đơn giản/đối tượng nhỏ.
- Video đã có **vệt mờ do công cụ khác tạo sẵn** không thể bảo đảm phục hồi toàn bộ hậu cảnh. Xử lý tóc, mặt và nền chuyển động nhanh có thể để lại dấu vết; đây chưa phải tracking/inpainting thời gian bằng model AI cao cấp.
- Hệ chữ ASS hỗ trợ tô từ nhấn vàng bằng `[[từ cần nhấn]]` trong câu, và có preset chữ trắng đậm viền đen theo phong cách hình mẫu; vẫn cần video gốc để kiểm tra font thật sự.
- Video QA `demo/original_reference_v06.mp4` và `demo/precision_clean_subtitle_v06.mp4` được dựng giả lập để kiểm thử, **không phải video TikTok gốc**. File này không đưa vào git để tránh làm repository phình to.

## Font giống video gốc

Mục tiêu sản phẩm là chuyển phụ đề gốc → phụ đề tiếng Việt cùng phong cách, nhưng **v0.6 chưa có nhận diện font tự động 1:1, OCR tracking, temporal inpainting**. Giao diện cho phép điều chỉnh font, màu, viền và xem bản render. Gợi ý màu có thể sai nếu hậu cảnh nhiều màu. Font phải được cài trên máy và hỗ trợ tiếng Việt.

## Quyền sử dụng và an toàn

Chỉ nhập video mà bạn có quyền tải/chỉnh sửa hoặc được chủ sở hữu cho phép. Không sử dụng để xóa watermark nhằm mạo nhận quyền tác giả. Không gửi mật khẩu, cookie Facebook hoặc key API qua giao diện.

**Chưa đủ điều kiện triển khai Internet công khai.** Bản v0.6 đã có xác thực một chủ sở hữu, băm PBKDF2, cookie HttpOnly/SameSite Strict, CSRF, khóa đăng ký sau tài khoản đầu tiên và chống brute force cơ bản. Khi đưa lên Internet cần HTTPS với `VIETFRAME_COOKIE_SECURE=true`, kiểm tra URL/redirect sâu hơn, chống SSRF toàn pipeline, giới hạn tác vụ/tải lên theo IP, backup database và file, giám sát chống lạm dụng, snapshot/restore và audit độc lập. Không chia sẻ tài khoản với nhiều người; dự án chưa tách biệt theo user. Docker expose local-only.

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

## Gemini viết phụ đề và thoại ElevenLabs (v0.8)

VietFrame Studio v0.8 bổ sung `app/gemini_bridge.py`, dùng REST API Gemini Files API + `generateContent` thay vì phải cài SDK Google. **Không cần key khi chỉ chạy phần phụ đề thường.** Người dùng liên kết Gemini trong **Cài đặt** bằng khóa Google AI Studio, liên kết ElevenLabs riêng bằng khóa ElevenLabs. Cả hai được mã hóa trong database cục bộ, không đưa vào mã nguồn/Git và không hiển thị lại qua API.

Luồng đầy đủ: mở dự án video → chọn nút **Gemini xem video → Viết sub & lời thoại Việt** → xác nhận truyền video cho Gemini → đọc kết quả phụ đề/thoại cho từng nhân vật → chọn ElevenLabs, giọng mặc định và giọng riêng `spk1`, `spk2`... nếu cần → **Tạo video hoàn chỉnh**. Gemini đưa ra `source_text`, `text` (để hiển thị), `voice_text` (để ElevenLabs đọc), `speaker`, `start`/`end` và cờ `needs_review` nếu thiếu chắc chắn. Có thể chỉnh riêng `voice_text` để lời nói vừa thời lượng cảnh mà không làm đổi phụ đề hiển thị.

Trong luồng tạo giọng, VietFrame đo WAV/MP3 thật bằng FFprobe, đặt vào mốc bắt đầu của câu, tăng tốc tối đa 1.35 lần, thêm khoảng lặng ngắn nếu cần. Nếu câu quá dài, tác vụ **dừng và báo lỗi**, không cắt cụt nội dung/âm thầm xuất video sai. Kết quả có `/api/projects/{id}/voice-timing-report` mô tả từng câu. **Đây là khớp timeline âm thanh, không phải lip-sync chuyển động miệng.**

Gemini phân tích video có âm thanh nguồn, tối đa **180 giây/60 MB** mỗi lượt. Các timecode Gemini vẫn là suy đoán cần người dùng xem lại, nhất là cảnh nhiều người nói/nhạc lớn. Khi chưa có lời nói nghe rõ, hệ thống không bịa phụ đề. File upload gửi Google được yêu cầu xóa ở khối `finally`. Chỉ dùng API key Free-tier của dự án *không bật billing*, vì API key tự nó không chứng minh rằng billing đã tắt; người dùng chịu trách nhiệm kiểm tra gói trong Google AI Studio. ElevenLabs vẫn được giới hạn bởi quota API Free, không được hứa miễn phí vô hạn.

Trạng thái hiện tại: **mã nguồn + kiểm thử cục bộ**, chưa xác minh request API Gemini hoặc chất lượng giọng ElevenLabs thật vì chưa có khóa của chủ sở hữu; bản xem trước *tĩnh* trên `vietframe-studio-eghb.onrender.com` không chạy backend này. Trước khi dùng trực tuyến cần dịch vụ backend có bảo mật và lưu trữ dữ liệu bền vững.

## Đăng nhập bằng Google (v0.9)

VietFrame hỗ trợ nút **Tiếp tục bằng Google** bằng OAuth 2.0 / OpenID Connect. **Nút chỉ bật sau khi đã cấu hình OAuth Client ID và Client Secret** ở Render Environment, không phụ thuộc Gemini API key. Người đăng nhập phải thuộc email chủ sở hữu được phép; tài khoản Google được khóa bằng `sub` bất biến và kiểm chứng ID token trên máy chủ. Đăng nhập mật khẩu hiện tại vẫn hoạt động.

Xem **[hướng dẫn đăng nhập Google](docs/GOOGLE_LOGIN_SETUP.md)** để cấu hình Web OAuth, đúng redirect URI và lưu ý SQLite trên Render Free có thể mất khi restart/redeploy.


## Khôi phục khi nhập YouTube Shorts thất bại (bản thử v0.10)

YouTube có thể từ chối trả luồng phát cho IP của Render, kể cả khi link Shorts được nhận diện đúng và yt-dlp có JS runtime. VietFrame không tuyên bố mọi video YouTube đều có thể tải được. Trong dự án trạng thái *Có lỗi*, có nút tải lên tệp MP4/MOV/WEBM/MKV mà chủ sở hữu có quyền sử dụng. Tệp được xác thực bằng ffprobe, thay video nguồn của chính dự án lỗi này, rồi tiếp tục Gemini/ElevenLabs như bình thường. API yêu cầu phiên đăng nhập chủ sở hữu, CSRF, xác nhận quyền sử dụng và giới hạn dung lượng/thời lượng cấu hình tại Render. Tệp không hợp lệ vẫn giữ trạng thái lỗi để người dùng thử lại. Giới hạn thực của dịch vụ được hiện trong giao diện, thay vì ghi cố định 350 MB.


## v0.12 — Giữ kết nối API lâu dài trên Render Free

Khi `VIETFRAME_CREDENTIALS_DATABASE_URL` chỉ tới Neon Postgres gói Free, khóa Gemini và ElevenLabs được Fernet mã hóa bằng `VIETFRAME_CREDENTIAL_ENCRYPTION_KEY` lưu trên Render trước khi cất trong bảng `vietframe_provider_credentials`. Liên kết giữ nguyên khi deploy/restart; không đưa API key hay DB URL vào GitHub. `VIETFRAME_REQUIRE_PERSISTENT_KEYS=true` ngăn fallback về SQLite tạm nếu cấu hình Neon bị mất. Chỉ chuyển khóa mới sau khi đăng nhập và liên kết lại một lần; không có cách an toàn để tự lấy khóa của container cũ. SQLite của dự án video vẫn là tạm và video sẽ mất sau redeploy; lưu trữ video bền vững cần object storage riêng.

Gemini v0.12 thử đường gửi dữ liệu video trực tiếp vào `generateContent` thay cho Files API (đã có lỗi HTTP 404 sau khi tệp ACTIVE). Video lớn được nén thành MP4 nhỏ để nằm trong ngưỡng inline. Không tự gọi API trả phí hoặc giả vờ hoàn tất phụ đề; trả lỗi rõ theo bước nếu Google vẫn từ chối model. 


## Khắc phục Gemini 404 khi generateContent (2026-11-22)

Model Gemini 2.5 Flash có thể trả metadata HTTP 200 nhưng generation HTTP 404 cho API key mới, do quyền truy cập model thay đổi. Mặc định chuyển sang `gemini-3.5-flash-lite` (Free Tier); tùy chọn `gemini-3.8-flash` (Free Tier nhưng hạn mức riêng). Xác thực API key bằng model đã chọn và kiểm tra `supportedGenerationMethods` khi Google trả trường này. Phân tích video gửi trực tiếp `inlineData` thay vì tham chiếu Google Files API; nén giữ âm thanh nếu input lớn. Đây là hai cơ chế độc lập để giảm lỗi 404; không thể bảo đảm mọi tài khoản Google đều có quyền/quota. Không tự bật billing.


## 2026-11-22 — Ghi nhớ đăng nhập Google

Trên Render, email Google được liên kết với một chủ sở hữu trong Neon; phiên HttpOnly, Secure và CSRF được giữ dưới dạng mã băm và tự gia hạn tối đa một lần/ngày khi sử dụng. Cookie có thời hạn 180 ngày, có đăng xuất thủ công, và đổi mật khẩu thu hồi các phiên. Xóa cookie, mở trình duyệt ẩn danh, thu hồi phiên, hoặc sự cố an ninh vẫn yêu cầu đăng nhập lại. Sau lần chuyển từ SQLite tạm sang Neon, người dùng đăng nhập Google lại **một lần** để tạo tài khoản trong kho bền vững, còn API key Gemini và ElevenLabs trong Neon vẫn được giữ nguyên.


## ElevenLabs lỗi 402 khi tạo video (2026-11-22)

Bản vá đọc JSON lỗi thật từ HTTP streaming của ElevenLabs, phân biệt giọng thư viện không được phép trên Free, hết credit, thiếu tính năng hoặc mất quyền TTS. API key đã lưu trong Neon, không bắt nhập lại. Không tự đổi giọng hoặc trả tiền. Khi xuất bị 402 và dự án còn video gốc, nút **Xuất MP4 với âm thanh gốc** chủ động khôi phục và xuất lại mà không gọi ElevenLabs; phụ đề/đồ họa đã lưu được giữ nguyên. Giọng từ thư viện có thể được liệt kê qua Voices API nhưng bị từ chối trong TTS Free; việc hiện danh sách giọng không bảo đảm được phép tạo tiếng.


## Kiểm thử trong Docker từ v0.13

Render build chạy `compileall`, `node --check static/app.js` và `pytest -q tests` trước khi triển khai, bao gồm test phân loại lỗi ElevenLabs 402, bảo mật session và điều kiện xuất MP4 thay thế. Nếu test lỗi, bản cũ tiếp tục phục vụ cho đến khi sửa. `VIETFRAME_CREDENTIALS_DATABASE_URL` chỉ được cấp ở runtime Render, không nằm trong hình Docker build hoặc GitHub.


## v0.14 Gemini transient overload / sticky failed project

Google có thể trả 503 cho Gemini Free Tier ngay cả khi API key hợp lệ. Tự thử lại tối đa 2 lần (chờ 2 giây rồi 4 giây) chỉ với 502/503/504, không thử lại 429 hoặc tự chuyển model trả phí. Sau lỗi, video và phụ đề đã lưu không bị xóa; nút **Thử lại Gemini** có thể nhận tác vụ trực tiếp từ trạng thái lỗi. Máy chủ chuyển trạng thái theo phép cập nhật nguyên tử để tránh hai lượt Gemini chạy trùng nhau. UI cập nhật trạng thái nút qua polling, không reset nội dung phụ đề chưa lưu. Đây là khôi phục lỗi tạm thời, không phải cam kết Google không còn 503.
