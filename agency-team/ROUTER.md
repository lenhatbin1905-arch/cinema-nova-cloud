# CINEMA NOVA AGENCY TEAM V4 — Codex
Bộ vai trò hướng dẫn chuyên môn (không phải nhiều AI chạy độc lập). Codex chọn một vai trò chính và tối đa hai vai trò phản biện.

## Chọn vai trò
- Lỗi Chrome extension / Manifest V3: roles/frontend.md + roles/qa-security.md
- Lỗi connector, SQLite, REST API: roles/backend.md + roles/qa-security.md
- AI viết kịch bản / Flow Agent / FFmpeg: roles/ai-video.md + roles/backend.md
- Thiết kế giao diện tiếng Việt: roles/ux-design.md + roles/frontend.md
- Thay đổi kiến trúc lớn: roles/orchestrator.md + roles/qa-security.md

## Quy trình
1. Kiểm tra Git status và mã local trên Windows. Bản V3.2 local có thể mới hơn GitHub: KHÔNG reset, ghi đè, hoặc làm mất thay đổi.
2. Đọc mã nguồn và tái hiện lỗi; nêu kế hoạch ngắn.
3. Viết mã, kiểm thử, yêu cầu QA kiểm tra, sửa lỗi phát hiện.
4. Kiểm tra Manifest ở source, thư mục build và ZIP. Nếu chưa mở GUI Chrome thì phải nói rõ.
5. Báo kết quả bằng tiếng Việt, phân biệt DEMO, sản xuất thật và chưa kết nối.

## Bảo vệ
Không tự tiêu Google Flow credits, sử dụng API trả phí (useapi.net), ghi cookie/token lên GitHub, vượt bảo mật Chrome/Google, hoặc merge main. Google Flow Tool V2.3 khác với Chrome Extension; không được nhận đã sửa Tool khi chỉ sửa tiện ích. Nếu bị chặn iframe khác origin, chọn xuất/nhập JSON an toàn.

Nguồn vai trò: https://github.com/msitarzewski/agency-agents (MIT).
