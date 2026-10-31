# Kiến trúc CINEMA NOVA (MVP)

## Hiện trạng đã kiểm chứng

- Website cloud là một `index.html` độc lập; CSS và JavaScript đang nhúng trong trang.
- Render build/publish config không có trong repository. Vì vậy không có bằng chứng build hiện tại đang copy resource hoặc deployment đang lấy đúng thư mục.
- Bản đầu có `cloud-connector.js` gọi các route `/bridge/*`, bật nút tạo khi extension báo kết nối, và xóa `jobId` khi đọc tiến độ lỗi. Repo không chứa connector server thực thi các route đó.
- Môi trường này không có process đang lắng nghe cổng 8001, 8100 hoặc 8765.

## MVP hiện tại

- `index.html`: website tĩnh, phác thảo mẫu, biên tập cảnh, duyệt, localStorage, xuất JSON/prompt và kiểm tra connector.
- `connector.py`: server Python chuẩn, bind duy nhất `127.0.0.1:8765`, phục vụ trang local, kiểm tra provider, lưu dự án SQLite tại `%LOCALAPPDATA%/CinemaNova`.
- Provider check: Flow Agent `GET /health`; FlowKit `GET /api/providers/status`. Đây chỉ là kiểm tra endpoint, chưa tạo job.
- Mã ghép nối: sinh ngẫu nhiên và lưu ngoài repository. Connector kiểm tra Host, Origin, header `X-CinemaNova-Token`, giới hạn body và chỉ cho phép website Render đã khai báo cùng localhost.
- Mock/offline: bản phác thảo là mẫu văn bản. Không mô phỏng job hoàn tất, không tạo video giả và không tiêu credits.
- Ghép MP4: chưa triển khai. FFmpeg không được phát hiện trong môi trường; chưa có clip đầu vào thực để xác nhận pipeline.

## Giới hạn có chủ ý

Endpoint Flow Agent hỗ trợ tạo video, nhưng gọi endpoint đó có thể tiêu credits. FlowKit API cũng khác biệt theo phiên bản và README của app đang chỉ về bridge V1.6 không có trong repo. Vì thế MVP chỉ probe provider, không gửi request tạo media. Muốn bật production cần xác thực payload FlowKit trên đúng phiên bản cài tại máy và thêm màn xác nhận chi phí cho từng lệnh thật.

Trang Render là public static site, nên token ghép nối phải được nhập tại phiên browser; nó chỉ lưu trong `sessionStorage`, không gửi lên Render. Chạy giao diện qua connector local thì token được cấp bởi endpoint cùng origin.

## Sơ đồ

```text
Render static page ── Origin allowlist + pairing token ──> 127.0.0.1:8765 connector
                                                         ├─> Flow Agent health :8001
                                                         ├─> FlowKit provider status :8100
                                                         └─> SQLite local project drafts
```
