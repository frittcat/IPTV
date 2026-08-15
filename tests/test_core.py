from backend.app import norm, safe_url, score


def test_norm_removes_quality_and_accents():
    assert norm("France 24 HD") == "france24"
    assert norm("TV São Paulo 1080p") == "tvsaopaulo"


def test_safe_url_rejects_private_and_file_urls():
    assert safe_url("https://example.com/live.m3u8")
    assert not safe_url("file:///etc/passwd")
    assert not safe_url("http://127.0.0.1:8080/admin")


def test_score_prefers_https_high_quality():
    assert score({"url": "https://example.com/a.m3u8", "quality": "1080p"}) > score({"url": "http://example.com/a.m3u8", "quality": "480p", "label": "Geo-blocked"})
