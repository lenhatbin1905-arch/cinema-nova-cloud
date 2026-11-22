"""Localise the MIT Gemini/Veo video editor vendored from @pilio.
This runs during the Docker build only; video bytes never hit our backend.
"""
from pathlib import Path

PAGE = Path('/app/static/gwr/video-preview.html')
LICENSE = Path('/app/static/gwr/LICENSE')

if not PAGE.is_file() or not LICENSE.is_file():
    raise SystemExit('Gemini/Veo vendor bundle or license is missing')

source = PAGE.read_text(encoding='utf-8')
translations = {
    'lang="zh-CN"': 'lang="vi"',
    'Gemini 视频水印本地处理 MVP': 'VietFrame • Xóa watermark Gemini/Veo',
    'WebCodecs + Mediabunny，文件只在浏览器内解码、逐帧处理、重新封装 MP4。':
        'WebCodecs + AI xử lý trực tiếp trên trình duyệt. Video không tải lên máy chủ VietFrame.',
    '当前范围：右下角 72px Gemini/Veo 风格水印；视频轨重编码，兼容音频轨自动透传。':
        'Phù hợp watermark Gemini/Veo nằm ở góc video. Chỉ sử dụng với video bạn có quyền chỉnh sửa.',
    '视频对比': 'So sánh video',
    '处理设置': 'Cài đặt xử lý',
    'Before / After 对比': 'So sánh trước / sau',
    '等待视频': 'Đang chờ video',
    '选择或拖入图片 / 视频': 'Chọn hoặc kéo thả video',
    '导出完成后显示右侧对比': 'Video đã xử lý sẽ hiển thị tại đây',
    '播放进度': 'Tiến độ phát',
    '播放': 'Phát',
    '选择文件': 'Chọn video Gemini / Veo',
    '视频会在本页处理，图片会回到单图对比页。10 秒 1080p MP4 样例最适合当前 MVP。':
        'Video được xử lý ngay trên thiết bị. Ưu tiên video ngắn MP4/WebM/MOV, dưới 100 MB.',
    '批量队列': 'Danh sách video',
    '自动处理': 'Xử lý tự động',
    'AI 自动处理': 'AI tìm và làm sạch watermark',
    '选择视频后自动检测水印，导出时使用本地 AI 模型清理。':
        'Chọn clip, phát hiện vùng watermark, xuất MP4 và so sánh kết quả.',
    '处理进度': 'Tiến độ xử lý',
    '检测水印': 'Phát hiện watermark',
    '重置': 'Đặt lại',
    '停止处理': 'Dừng',
    '自动导出无水印视频': 'Xử lý và xuất video MP4',
    '下载结果': 'Tải MP4 đã xử lý',
    '关闭': 'Tắt',
    'Canvas 边缘去噪': 'Canvas làm sạch viền',
    'AI FDnCNN ONNX': 'AI FDnCNN ONNX',
    '迁移锚点复核预设': 'Kiểm tra điểm neo',
    '导出会重新编码视频轨，并在 MP4 支持原音频编码时透传音频轨。':
        'Video sẽ được mã hóa lại. Âm thanh gốc được giữ khi định dạng tương thích. Xem lại chất lượng trước khi dùng.',
    '视频信息': 'Thông tin video',
    '检测结果': 'Kết quả nhận diện',
}
for original, replacement in translations.items():
    source = source.replace(original, replacement)
# Add prominent navigation and credit without touching the upstream algorithm.
header = '''<div class="vf-header" style="display:flex;flex-wrap:wrap;gap:12px;justify-content:space-between;align-items:center;background:#edf5ef;padding:14px 24px;font-family:system-ui,sans-serif">
  <a href="/" style="color:#20523f;font-weight:700">← Trở lại VietFrame Studio</a>
  <span style="color:#41655a">Xử lý cục bộ trên máy · Không dùng RAM Render · Chỉ video có quyền chỉnh sửa</span>
</div>'''
footer = '''<footer style="padding:20px 28px;font:12px system-ui,sans-serif;color:#64748b">
  Công nghệ mã nguồn mở MIT © Jad / AllenK · <a href="https://github.com/GargantuaX/gemini-watermark-remover" target="_blank" rel="noopener">Dự án gốc</a> ·
  <a href="/static/gwr/LICENSE">Giấy phép MIT</a>.
  Kết quả phụ thuộc loại watermark và trình duyệt. Việc xử lý dấu hiển thị không đồng nghĩa xóa SynthID ẩn.
</footer>'''
if '<body>' not in source or '</body>' not in source:
    raise SystemExit('Upstream video preview HTML structure has changed')
source = source.replace('<body>', '<body>\n'+header, 1)
source = source.replace('</body>', footer + '\n</body>', 1)
PAGE.write_text(source, encoding='utf-8')
