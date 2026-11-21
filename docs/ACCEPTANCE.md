# Quality gates — VietFrame Studio

## Các điều kiện chặn phát hành

- [ ] Giao diện máy tính (>=1280px), điện thoại (360px) không tràn, không che nút.
- [ ] Bảo mật: đăng nhập, phân quyền theo dự án, upload rate limit, CSRF/SSRF review, HTTPS, secrets hygiene.
- [ ] Nút UI nào cũng có hành động backend thật hoặc disabled kèm giải thích.
- [ ] Download công khai: mỗi nền tảng một URL được phép sử dụng, trả lỗi nếu private/expired.
- [ ] Không xuất MP4 lỗi, sai FPS, sai kích thước, không có âm thanh, phụ đề vượt màn hình.
- [ ] Font tiếng Việt đúng dấu, không rơi dấu, giãn dòng chuẩn, không lỗi chữ.
- [ ] Font Match gốc: so sánh bằng ảnh test chính chủ, đo độ tương đồng, nhận xét thủ công.
- [ ] Dubbing: 5 mẫu giọng Việt nam/nữ và 3 cảnh cảm xúc, có người đánh giá mù.
- [ ] Inpainting: 10 sample có vật thể chuyển động, kiểm tra temporal flicker.
- [ ] AI video: chạy text-to-video bằng GPU thật, có media metadata và log lỗi.
- [ ] Tích hợp model miễn phí không kèm billing ẩn, báo thiếu tài nguyên trung thực.

## Các kiểm thử hiện có

- URL parse whitelist, HTTPS, cấm credential/IP/port.
- `ffprobe` kiểm tra video thật và metadata.
- Sinh phụ đề SRT/ASS và text Unicode (tiếng Việt).
- Xử lý một clip tổng hợp bằng FFmpeg để xác minh xuất file thật.
- API tải lên, nhập link, đồng bộ dự án, bảo vệ file path.

## Chấm điểm Very Good (chỉ khi có đo thực tế)

Ngưỡng mục tiêu >=90/100 (không suy ra từ số test PASS): UI 15, font 20, dịch/lồng tiếng 20, sửa nền 15, AI video 10, hiệu năng 10, bảo mật 10.

**Bản MVP hiện tại không thể được chấm 90/100**: chưa có font match 1:1, voice dubbing, inpainting video và bảo mật public. Không được phát hành rộng rãi chỉ vì unit tests đã PASS.
