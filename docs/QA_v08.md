# VietFrame Studio v0.8 — Gemini Video-to-Vietnamese Voice Director

## Đã kiểm thử

- 77/77 bài unit/integration/HTTP/local-FFmpeg test đạt, `node --check` đạt.
- Full media render (`ffmpeg`) có âm thanh, phụ đề Việt và nhận mốc thời gian; lồng tiếng từng câu được kiểm tra bằng WAV mẫu sinh bằng FFmpeg, **không phải** giọng thật từ ElevenLabs.
- Gemini File API upload → polling → JSON response → xóa file nguồn trên Google: dùng `httpx.MockTransport`, xác nhận chỉ gọi một lần generateContent.
- Đường liên kết API key Gemini: kiểm thử xác minh model bằng HTTP mock, mã hóa Fernet trong SQLite, không trả API key qua endpoint trạng thái.
- Tự chặn video dài hơn 180 giây / 60 MB trong chế độ Free-first; ngăn tên file URI và URL upload giả mạo.
- Dữ liệu 1 đoạn: `start`, `end`, `source_text`, `text`, `voice_text`, `speaker`, `needs_review`; không âm thầm sửa sai timestamps.
- Hai nhân vật: `spk1` giọng mặc định, `spk2` giọng riêng, từng câu được tạo một lần và căn theo mốc thời gian.
- Xuất báo cáo voice-timing-report: thời lượng lời đọc, thời lượng slot, hệ số tăng tốc, tiếng nói người nào.

## Chưa có bằng chứng nghiệm thu

- Chưa có API key Gemini Free-tier/ElevenLabs thật của chủ tài khoản để test end-to-end chất lượng giọng.
- Không bảo đảm Gemini nghe đúng từng từ hoặc trả timecode chuẩn miligiây; cần kiểm tra bằng tai và sửa đoạn `needs_review`.
- Không có forced alignment/voice separation/lip-sync/mô hình khớp font OCR hay xóa logo không dấu vết.
- Free Render không có ổ đĩa bền vững: SQLite, file video và API key kết nối trên dịch vụ Free có thể mất khi restart/redeploy. Không sử dụng như môi trường production trước khi có bộ lưu trữ bền vững.
- Chưa chứng minh tất cả nguồn Facebook/YT/TikTok/Douyin/Bilibili/Instagram tải được mọi link.

## Tư duy Free-first

- Gemini API key chỉ do chủ sở hữu dán ở trang Cài đặt của ứng dụng, gửi đến API Google qua máy chủ sau khi người dùng bấm cho phép phân tích.
- ElevenLabs API key được liên kết riêng; chỉ tổng hợp khi API xác nhận quota gói Free; tài khoản trả phí bị từ chối trong chế độ an toàn.
- Gemini API không cung cấp cơ chế chứng thực *khóa đang ở Free Tier, không billing* từ token; chủ tài khoản phải tạo key dưới dự án không bật billing, kiểm tra hạn mức trên AI Studio. Không tự chuyển model hoặc thanh toán.
- Không có API keys nào lưu trong Git hoặc gói ZIP.
