# CINEMA NOVA — Quy tắc phát triển

- Giải thích, giao diện và thông báo cho người dùng bằng tiếng Việt.
- Giữ website tương thích Render Static Site; mọi tài nguyên mới phải được đưa vào quy trình xuất bản.
- Không đưa mật khẩu, cookie, API key, token, ảnh riêng tư hoặc video sinh ra vào Git.
- Không gọi dịch vụ trả phí/useapi.net và không tự gửi yêu cầu tạo ảnh/video thật. Chỉ cho phép tác vụ tiêu credits sau một xác nhận rõ ràng trong giao diện.
- Không tuyên bố mock là kết quả Google Flow thật. Báo riêng trạng thái đã kiểm chứng, mô phỏng và chưa kết nối.
- Connector chỉ bind loopback, xác thực Origin/Host và token; không mở cổng ra Internet.
- Không tự cập nhật `main` hoặc triển khai Render. Làm trên nhánh phát triển và kiểm tra trước khi bàn giao.
- Ưu tiên Python chuẩn và JavaScript không cần build tool; kiểm thử bằng `python -m unittest` và `node --check` khi phù hợp.
- Không xóa hoặc ghi đè tệp người dùng có sẵn. Hạn chế thay đổi API/cấu trúc hiện có nếu chưa cần.

<!-- CINEMA_NOVA_AGENCY_TEAM_V4_BEGIN -->
## CINEMA NOVA AGENCY TEAM V4
Trước khi sửa mã nguồn, hãy đọc [agency-team/ROUTER.md](agency-team/ROUTER.md). Chọn 1 vai trò chính và tối đa 2 vai trò phản biện trong agency-team/roles/ theo tác vụ. Đây là hồ sơ hướng dẫn cho Codex, không phải agent tự chạy độc lập. Bảo toàn code Windows V3.2 chưa push. Không tự tiêu credits, không gọi API trả phí, không tự merge main hoặc phát hành mà chưa được duyệt.
<!-- CINEMA_NOVA_AGENCY_TEAM_V4_END -->
