# VietFrame Studio v0.9 — Google Login (OAuth 2.0 / OpenID Connect)

## Trạng thái

Mã nguồn đã có trang **Tiếp tục bằng Google**, luồng Authorization Code + PKCE, `state`, `nonce`, kiểm chứng ID token chữ ký RS256/audience/issuer/hạn và khóa `sub` của tài khoản chủ sở hữu. **Không có Google OAuth Client ID/Secret thì nút được vô hiệu hóa rõ ràng, không giả đăng nhập.** Google OAuth để đăng nhập VietFrame KHÁC Gemini API key để phân tích video.

## 1. Google Cloud Console (bước chủ tài khoản phải thao tác)

1. Mở https://console.cloud.google.com/auth/clients (Google Auth Platform → Clients).
2. Nếu chưa có, tạo dự án và hoàn tất Branding/Audience. Chọn External và thêm email Google của chính bạn vào Test users khi ở trạng thái Testing.
3. Chọn **Create client → Web application**. Nhập tên `VietFrame Studio`.
4. **Authorized JavaScript origins** (nếu Google yêu cầu): `https://vietframe-studio-app.onrender.com`.
5. **Authorized redirect URIs** phải nhập CHÍNH XÁC:
   `https://vietframe-studio-app.onrender.com/api/auth/google/callback`
6. Sao chép **Client ID** và **Client Secret**, không chia sẻ qua chat hoặc commit lên GitHub.
7. Yêu cầu chỉ scope `openid email`; VietFrame không đọc Gmail/Drive và không lưu Google access tokens.

## 2. Render → VietFrame Studio App → Environment

Mở https://dashboard.render.com/web/srv-dc1671t6e07s73cefgb0 → Environment; tạo:

| Key | Giá trị |
| --- | --- |
| `VIETFRAME_GOOGLE_CLIENT_ID` | Client ID của ứng dụng Web từ Google Cloud |
| `VIETFRAME_GOOGLE_CLIENT_SECRET` | Client Secret của ứng dụng Web từ Google Cloud (bí mật) |
| `VIETFRAME_GOOGLE_ALLOWED_EMAIL` | Email Google của chủ sở hữu, đã được chủ tài khoản xác nhận |
| `VIETFRAME_GOOGLE_ORIGIN` | `https://vietframe-studio-app.onrender.com` |

Không thêm `GOOGLE_API_KEY` để đăng nhập. Gemini API key là một loại credential khác, liên kết bên trong **Hệ thống → Gemini**.

Render sẽ cần deploy/restart sau khi cập nhật Environment. Khi cả bốn biến hợp lệ, `/api/auth/config` trả `google_login_available: true`; nút **Tiếp tục bằng Google** được bật ở `/login`.

## 3. Quyền truy cập

- Chỉ email trong `VIETFRAME_GOOGLE_ALLOWED_EMAIL` có thể đăng nhập. Khi tài khoản chủ sở hữu đã tồn tại, email phải trùng email trong SQLite.
- Lần đầu thành công, VietFrame ghi nhận `sub` bất biến do Google cấp; những tài khoản Google khác không thể nhận quyền chỉ bằng email trùng.
- Tài khoản được tạo qua Google không có mật khẩu ngẫu nhiên công khai; có thể đặt mật khẩu dự phòng qua `python -m app.auth reset-owner-password` trên server quản trị.
- Đăng nhập mật khẩu hiện có được giữ lại.

## 4. Lưu ý Render Free

Render Free có hệ thống tệp không bền vững. **SQLite gồm tài khoản, phiên đăng nhập, Google `sub` và API key Gemini/ElevenLabs có thể bị mất khi dịch vụ restart/redeploy.** Không dùng để lưu tài khoản hay API key quan trọng lâu dài; cần PostgreSQL và kho mã hóa bí mật bền vững trước khi triển khai thương mại.

## 5. Nghiệm thu

- Mã nguồn: `pytest -q` (86/86 PASS trên môi trường phát triển).
- Kiểm thử Google thật chỉ hoàn thành sau khi Client ID/Secret hợp lệ do chủ dự án tạo; chạy lại đường dẫn `/login` và đăng nhập đúng Google email.
- Không dùng web login để lấy quyền Gemini hoặc ElevenLabs: đây là 3 hệ thống xác thực riêng biệt.

Nguồn Google: https://developers.google.com/identity/protocols/oauth2/web-server , https://developers.google.com/identity/openid-connect/openid-connect
