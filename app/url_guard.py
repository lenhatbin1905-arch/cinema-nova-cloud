"""Guard import links: only approved public video hosts, never generic HTTP fetches."""
import ipaddress
from urllib.parse import urlsplit

DOMAINS = {
    'YouTube': ('youtube.com', 'youtu.be', 'youtube-nocookie.com'),
    'Facebook': ('facebook.com', 'fb.watch'),
    'TikTok': ('tiktok.com',),
    'Douyin': ('douyin.com', 'iesdouyin.com', 'v.douyin.com'),
    'Bilibili': ('bilibili.com', 'b23.tv'),
    'Instagram': ('instagram.com',),
}


def classify_url(url: str) -> str:
    if not isinstance(url, str) or len(url) > 2048:
        raise ValueError('Đường dẫn không hợp lệ hoặc quá dài.')
    try:
        u = urlsplit(url.strip())
        host = (u.hostname or '').encode('idna').decode('ascii').lower().rstrip('.')
        port = u.port
    except (ValueError, UnicodeError) as exc:
        raise ValueError('Không đọc được đường dẫn.') from exc
    if u.scheme != 'https' or not host or u.username or u.password or port not in (None, 443):
        raise ValueError('Chỉ chấp nhận link HTTPS công khai từ 6 nền tảng được hỗ trợ.')
    try:
        ipaddress.ip_address(host)
        raise ValueError('Không cho phép link chứa địa chỉ IP.')
    except ValueError as exc:
        if str(exc).startswith('Không cho phép'):
            raise
    for platform, domains in DOMAINS.items():
        if any(host == domain or host.endswith('.' + domain) for domain in domains):
            return platform
    raise ValueError('Chỉ nhận link YouTube, Facebook, TikTok, Douyin, Bilibili, Instagram.')
