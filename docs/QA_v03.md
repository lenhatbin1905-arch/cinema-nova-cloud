# Báo cáo nghiệm thu kỹ thuật — VietFrame Studio v0.3

Ngày tổng hợp: 22/11/2026 (Asia/Ho_Chi_Minh).

## Những gì đã được kiểm tra

- **100/100 vòng kiểm thử hồi quy PASS**, mỗi vòng **40 bài**, tổng cộng 4.000 lần thực thi bài test. Vòng 1–36 chạy tuần tự, vòng 37–100 chạy bằng ba tiến trình song song trên cùng mã nguồn v0.3. Kết quả thô ở `qa/100_rounds.csv`.
- Sau sửa hai lỗi nhỏ ở UI (mobile navigation, preview state và parser phản hồi HTTP), chạy lại một vòng 40/40 bài PASS và kiểm tra cú pháp JavaScript bằng `node --check`.
- Kiểm tra bố cục HTML/CSS trên Chromium tại 1440×900, 768×1024, 390×844 và 360×740: không phát hiện tràn ngang.
- Kiểm tra giao diện editor trên Chromium với dữ liệu API mô phỏng, 1440px và 390px: hiển thị lớp phụ đề tiếng Việt, không có lỗi pageerror.
- Kiểm tra HTTP thực với máy chủ Uvicorn trên 127.0.0.1:18010: upload video 4 giây, lưu phụ đề có dấu, render MP4 bằng FFmpeg, tải file thành phẩm, xác nhận video và kiểm tra tác vụ render trùng bị HTTP 409.
- Kiểm tra trực quan một khung hình của video xuất: chữ tiếng Việt có viền màu và hiển thị dấu.

## Những lỗi/điểm yếu đã sửa

1. Không xóa bản lồng tiếng nếu người dùng lưu lại phụ đề nhưng nội dung không thay đổi.
2. Xóa tham chiếu bản xuất và giọng đọc cũ nếu phụ đề thực sự thay đổi.
3. Khóa tác vụ theo dự án bằng thao tác DB nguyên tử: tránh chạy render/dub nhiều lần khi bấm nhanh.
4. Khi máy chủ khởi động lại, tác vụ treo được ghi là lỗi; có thao tác khôi phục khi còn video nguồn.
5. Render ghi vào tệp tạm, kiểm tra metadata, sau đó thay thế tệp xuất đã hoàn chỉnh.
6. Tạo file ASS đúng kích thước video nguồn thay vì luôn giả định video 1080×1920.
7. Kiểm tra thời gian NaN/vô hạn và loại ký tự điều khiển trong phụ đề.
8. Bổ sung header bảo vệ cơ bản, không cache API, kiểm soát trạng thái preview và hiển thị đủ 4 điều hướng trên điện thoại.

## Giới hạn chưa được xác minh — KHÔNG đánh dấu đã đạt

- Chưa kiểm thử tải thật trên đủ sáu nền tảng Facebook, YouTube, TikTok, Douyin, Bilibili, Instagram; chỉ kiểm tra kiểm soát tên miền, pipeline yt-dlp và xử lý lỗi. Môi trường kiểm thử hiện không cài yt-dlp.
- Chưa có mô hình Whisper, Argos và KokoroTTS chạy thực; chất lượng giọng Việt và dịch tự nhiên chưa được thẩm định.
- Không có GPU/model tại môi trường QA: chưa xuất video AI từ prompt.
- Chưa có công nghệ nhận diện font gốc 1:1 hoặc xóa chữ nền bằng temporal inpainting.
- Chưa có chức năng xác thực/đăng nhập, phân quyền, chống lạm dụng, giới hạn tài nguyên theo người dùng. **Không an toàn để đưa thẳng lên Internet.**
- Trình duyệt Chromium từ môi trường kiểm thử bị chặn truy cập trực tiếp localhost theo chính sách môi trường. Bài thử Chromium với API là mô phỏng; bài thử HTTP trực tiếp được chạy bằng Python. Không gộp hai điều này thành bằng chứng E2E browser→backend.
- 100 lần PASS không chứng minh không còn lỗi và cũng không tương đương điểm Very Good 90/100.

## Tiêu chí phát hành

Bản v0.3 đạt **mốc MVP chạy cục bộ**. Chưa đạt phát hành public/Very Good. Trước khi phát hành phải bổ sung auth, chống CSRF/SSRF sâu cho downloader, quota, quản lý secrets, E2E browser→backend, đánh giá thật chất lượng font/giọng/AI.

Đánh giá kỹ thuật: **PASS phạm vi MVP đã kiểm thử, HOLD phát hành public.**
