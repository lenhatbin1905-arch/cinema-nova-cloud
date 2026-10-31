# CINEMA NOVA — Studio MVP

Ứng dụng tiếng Việt để phác thảo kịch bản, chỉnh sửa và duyệt cảnh, lưu bản nháp, xuất JSON/prompt và kiểm tra các provider chạy trên máy Windows.

## Trạng thái hiện tại

- Phác thảo offline là **mẫu**, không phải nội dung do mô hình AI tạo.
- Kịch bản mẫu dùng clip 4, 6, 8 hoặc 10 giây. Nếu mục tiêu là 15 giây, trình biên tập chấp nhận phần clip dư và ghi rõ cần cắt khi dựng.
- Flow Agent và FlowKit chỉ được kiểm tra endpoint. Không có yêu cầu tạo ảnh/video nào được gửi, và nút sản xuất đang khóa.
- Google Flow thật, quản lý job, ghép clip và xuất MP4 chưa được tích hợp/kiểm chứng.
- Bản nháp trên trang web được lưu trong localStorage. Connector cũng cung cấp API lưu SQLite cục bộ, ngoài thư mục Git.

## Mở trên Windows

1. Cần Python 3.11 trở lên (connector chỉ dùng thư viện chuẩn).
2. Mở `START_CINEMA_NOVA.bat`.
3. Trình duyệt mở giao diện tại `http://127.0.0.1:8765`. Dùng nút **Kiểm tra kết nối máy tính** để xác nhận Flow Agent/FlowKit đang phản hồi.
4. Nếu dùng website Render thay vì giao diện local, sao chép mã ghép nối từ cửa sổ connector vào mục **Mã ghép nối**. Mã chỉ được lưu trong sessionStorage của tab. Không gửi mã cho ai.
5. Tạo/điều chỉnh phác thảo, duyệt, lưu bản nháp hoặc xuất JSON/prompt. Nút tạo video sẽ bị khóa cho đến khi tích hợp và xác thực adapter thật.

Connector chỉ bind `127.0.0.1`, không yêu cầu quyền Administrator và không mở cổng Internet. Có thể nhấn `Ctrl+C` để dừng. Trạng thái connector không chứng minh tài khoản Google đã đăng nhập; trang chỉ báo chính xác endpoint provider có trả lời hay không.

## Dùng web local thủ công

```powershell
py -3 connector.py
```

Mở `http://127.0.0.1:8765`. Dữ liệu SQLite và mã ghép nối nằm trong `%LOCALAPPDATA%\CinemaNova`.

## Kiểm thử

```powershell
py -3 -m unittest discover -s tests -v
node --check cloud-connector.js
```

Kiểm tra cú pháp JavaScript (Node.js):

```powershell
@'
from pathlib import Path
import re, subprocess, tempfile
html=Path('index.html').read_text(encoding='utf-8')
scripts=re.findall(r'<script>(.*?)</script>', html, flags=re.S)
for i, script in enumerate(scripts):
    with tempfile.NamedTemporaryFile('w', suffix='.js', encoding='utf-8', delete=False) as f:
        f.write(script); name=f.name
    subprocess.run(['node', '--check', name], check=True)
print(f'{len(scripts)} inline script(s): syntax OK')
'@ | py -
```

## Render Static Site

`render.yaml` builds and publishes `index.html` together with `cloud-connector.js`; the page's external script is included in the published output. The connector is a separate Windows process and is not deployed to Render. A static site cannot host the local connector or store local media.

## Provider research

- Flow Agent upstream documents `GET /health`, `POST /api/v1/video`, and default port 8001: <https://github.com/kodelyx/flow-agent/blob/main/docs/API_REFERENCE.md>.
- FlowKit upstream documents provider status at `GET /api/providers/status`, default port 8100, and post-production endpoints. Different FlowKit builds can vary: <https://github.com/crisng95/flowkit>.
- `useapi/google-flow-api` examples require a third-party token and call a commercial service. It is not used or contacted by CINEMA NOVA: <https://github.com/useapi/google-flow-api>.

## Phát triển

Đọc [AGENTS.md](AGENTS.md) và [ARCHITECTURE.md](ARCHITECTURE.md) trước khi thay đổi provider, connector hoặc cơ chế triển khai.
