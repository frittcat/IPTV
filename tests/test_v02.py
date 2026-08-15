import xml.etree.ElementTree as ET
from pathlib import Path
import pytest
from providers.base import VODItem, rights_status
from providers.m3u_vod import parse_m3u, classify
from providers.service import item_key, generate_strm
from backend.app import norm, safe_url, score


@pytest.mark.parametrize("value,expected", [("France 24 HD","france24"),("FRANCE24","france24"),("TV São Paulo 1080p","tvsaopaulo"),("BBC One FHD","bbcone"),("RTP 1 720p","rtp1"),("News & Culture","newsculture")])
def test_normalization(value, expected): assert norm(value) == expected

@pytest.mark.parametrize("url", ["http://127.0.0.1/x","http://10.0.0.1/x","http://172.16.0.1/x","http://192.168.1.1/x","http://169.254.169.254/latest","http://[::1]/x","file:///tmp/x"])
def test_ssrf_private_ranges(url): assert not safe_url(url)

def test_m3u_movies_and_series():
    text = '#EXTM3U\n#EXTINF:-1 tvg-id="m1" group-title="Movies",Movie One\nhttps://example.org/movie.mp4\n#EXTINF:-1 group-title="Series",Show S01E01\nhttps://example.org/e.mp4\n'
    items = list(parse_m3u(text, authorized=True)); assert len(items) == 2; assert items[0].item_type == "movie"; assert items[1].item_type == "series"

def test_m3u_rejects_live():
    assert list(parse_m3u('#EXTINF:-1 group-title="News",Live\nhttps://x/a.m3u8\n')) == []

@pytest.mark.parametrize("group,kind", [("Movies","movie"),("Filmes","movie"),("Kids","movie"),("Documentaries","movie"),("Series","series"),("Séries","series"),("Live","live"),("Unknown","unknown")])
def test_classify(group, kind): assert classify(group, "Sample") == kind

@pytest.mark.parametrize("license_name,expected", [("Public Domain","approved"),("CC0","approved"),("CC BY 4.0","approved"),("copyright unknown","review_required"),("","review_required")])
def test_rights(license_name, expected): assert rights_status(license_name, "", "") == expected

def test_item_key_stable():
    a=VODItem("archive_org","x","movie","X"); assert item_key(a)==item_key(a)

def test_item_key_changes_provider():
    assert item_key(VODItem("a","x","movie","X")) != item_key(VODItem("b","x","movie","X"))

def test_strm_generation(tmp_path):
    item=VODItem("p","x","movie","Movie",year=2020); p=generate_strm(item,"abc123",tmp_path,"http://fs:8080"); assert p.exists(); assert p.read_text().strip()=="http://fs:8080/vod/stream/abc123"

def test_series_strm_generation(tmp_path):
    item=VODItem("p","x","series","Show"); p=generate_strm(item,"abc123",tmp_path,"http://fs:8080"); assert "Season 01" in str(p); assert p.exists()

@pytest.mark.parametrize("quality,url,expected", [("1080p","https://x/a",True),("720p","https://x/a",True),("480p","http://x/a",True),("SD","http://x/a",True)])
def test_score_is_bounded(quality,url,expected): assert 0 <= score({"quality":quality,"url":url}) <= 100

def test_xml_library_roundtrip(tmp_path):
    root=ET.Element("tv"); c=ET.SubElement(root,"channel",{"id":"x&bad"}); ET.SubElement(c,"display-name").text="A & B"; p=tmp_path/"x.xml"; ET.ElementTree(root).write(p,encoding="utf-8",xml_declaration=True); parsed=ET.parse(p); assert parsed.find("channel/display-name").text=="A & B"

def test_item_metadata_defaults():
    item=VODItem("p","id","movie","title"); assert item.rights_status=="review_required" and item.genres==[]

def test_headers_not_in_strm(tmp_path):
    item=VODItem("p","x","movie","Movie",stream_url="https://secret.example/x",metadata={"Authorization":"secret"}); p=generate_strm(item,"id",tmp_path); assert "Authorization" not in p.read_text()

def test_live_detection_case_insensitive(): assert classify("NEWS", "Channel") == "live"

def test_unknown_m3u_is_not_vod(): assert not list(parse_m3u('#EXTINF:-1 group-title="Other",Thing\nhttps://x/a.mp4\n'))

def test_public_rights_is_publishable(): assert rights_status("Public Domain", "", "") == "approved"

def test_review_rights_not_publishable(): assert rights_status("All rights reserved", "", "") == "review_required"

def test_quality_label_penalty(): assert score({"quality":"1080p","url":"https://x/a","label":"Geo-blocked"}) < score({"quality":"1080p","url":"https://x/a"})

def test_referrer_penalty(): assert score({"quality":"720p","url":"https://x/a","referrer":"https://ref"}) < score({"quality":"720p","url":"https://x/a"})

def test_http_only_is_allowed_public(): assert safe_url("http://example.com/stream")

def test_https_public_is_allowed(): assert safe_url("https://example.com/stream")

def test_vod_item_types():
    assert {VODItem("p","1",t,t).item_type for t in ("movie","series")} == {"movie","series"}

def test_m3u_logo_field():
    item=list(parse_m3u('#EXTINF:-1 tvg-logo="https://x/logo.jpg" group-title="Movies",X\nhttps://x/m\n'))[0]; assert item.poster=="https://x/logo.jpg"

def test_m3u_authorized_status():
    assert list(parse_m3u('#EXTINF:-1 group-title="Movies",X\nhttps://x/m\n',authorized=True))[0].rights_status=="approved"

def test_m3u_unauthorized_review():
    assert list(parse_m3u('#EXTINF:-1 group-title="Movies",X\nhttps://x/m\n',authorized=False))[0].rights_status=="review_required"
