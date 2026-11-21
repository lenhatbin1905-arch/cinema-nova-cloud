import pytest
from app.url_guard import classify_url

@pytest.mark.parametrize('url,expected',[
 ('https://www.youtube.com/watch?v=abc','YouTube'),
 ('https://youtu.be/abc','YouTube'),
 ('https://m.facebook.com/watch/?v=12','Facebook'),
 ('https://fb.watch/test','Facebook'),
 ('https://www.tiktok.com/@x/video/123','TikTok'),
 ('https://v.douyin.com/xyz','Douyin'),
 ('https://www.bilibili.com/video/BV123','Bilibili'),
 ('https://b23.tv/abc','Bilibili'),
 ('https://www.instagram.com/reel/abc/','Instagram'),
])
def test_supported_platforms(url,expected):
    assert classify_url(url)==expected

@pytest.mark.parametrize('url',[
 'http://youtube.com/watch?v=hi','https://youtube.com.evil.com/x',
 'https://127.0.0.1/a','https://localhost/a','https://evil.org/',
 'https://username:pw@youtube.com/x','https://youtube.com:9999/x',
 'file:///etc/passwd','ftp://youtube.com/test',
 'https://youtube.com@evil.org/private',
])
def test_reject_unsafe_url(url):
    with pytest.raises(ValueError):classify_url(url)
