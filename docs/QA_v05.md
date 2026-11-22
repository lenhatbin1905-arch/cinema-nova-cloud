# VietFrame Studio v0.5 — QA

- Test suite: 57/57 PASS (trên môi trường phát triển), gồm 5 bài test bổ sung trong `tests/test_v05_cleanup_elevenlabs.py`.
- `node --check static/app.js`, `node --check static/login.js`: PASS.
- FFmpeg: đã xuất MP4 thực bằng filter `delogo` rồi ghi phụ đề ASS có dấu Unicode; kiểm tra lại bằng ffprobe.
- ElevenLabs: kiểm thử bằng **API mock** (khóa mã hóa, kết nối/ngắt kết nối, khóa CSRF, kiểm tra quota Free, ghép WAV bằng FFmpeg). Chưa gọi tài khoản ElevenLabs thật vì chưa liên kết API key.
- Chưa tự nhận diện font gốc 1:1, tự tracking chữ, inpainting temporal. UI preset là vùng cố định.
- Không dùng lại thông tin đăng nhập ElevenLabs đã liên kết trong ChatGPT; yêu cầu liên kết API một lần theo hướng dẫn trong README.
- Không triển khai public hoặc khẳng định bảo mật production. Chạy local với single-owner.
