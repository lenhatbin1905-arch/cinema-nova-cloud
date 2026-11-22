# VietFrame v0.8 — triển khai thử trên Render Free

**Chưa triển khai backend.** Link https://vietframe-studio-eghb.onrender.com hiện chỉ là preview tĩnh, không có xử lý video hoặc Gemini/ElevenLabs thật.

1. Mở https://dashboard.render.com/blueprints, chọn **New Blueprint Instance** rồi chọn repository `lenhatbin1905-arch/cinema-nova-cloud`, nhánh `feature/vietframe-studio-free-first-v02`, file `render.yaml`.
2. Điền biến bí mật `VIETFRAME_SETUP_TOKEN` trong giao diện Render. Sinh giá trị dài bằng `python -c "import secrets;print(secrets.token_urlsafe(32))"`; **không gửi khóa vào chat, không ghi vào Git**.
3. Xác nhận gói **Free**, Docker, Singapore và `autoDeployTrigger: off` trước khi áp dụng. Chỉ nhấn **Apply** khi đã kiểm tra; không bật thanh toán.
4. Khi Render thực sự báo trạng thái **Live**, vào URL mới rồi truy cập `/login` để tạo tài khoản chủ sở hữu. Nhập token tại màn hình khởi tạo. Giữ kín mật khẩu.
5. Khi có lưu trữ bền vững, vào Cài đặt và liên kết API key Gemini/ElevenLabs; yêu cầu xác nhận gửi video tới Google khi cần Gemini phân tích. Chọn giọng `spk1`, `spk2`, sửa `voice_text`, rồi bấm **TẠO VIDEO HOÀN CHỈNH**.

**Cảnh báo quan trọng:** Render Free dùng hệ thống file tạm. Dữ liệu SQLite, tài khoản, video và API key liên kết có thể bị mất khi ứng dụng ngủ/khởi động lại/tái triển khai. Không sử dụng cho dự án thực hoặc lưu API key lâu dài. Cần PostgreSQL + object storage bền vững trước khi công khai rộng rãi. Dịch vụ Free không có GPU để tạo phim từ prompt; chỉ có thể chạy FFmpeg CPU và API bên ngoài nếu quota cho phép. Gemini không bảo đảm timecode đúng từng âm tiết và chưa có kiểm thử với tài khoản thật; tính năng này chỉ ở mức mã nguồn đã qua kiểm thử mock. Không bảo đảm xóa chữ/logo chuyển động không dấu vết.

Tham khảo: https://render.com/docs/free ; https://render.com/docs/blueprint-spec
