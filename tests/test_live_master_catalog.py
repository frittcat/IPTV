from backend.live_master_catalog import (
    categories,
    decorate_channel,
    master_channels,
    match_channel,
    match_channel_flexible,
)


def test_br_master_has_required_navigation_categories():
    assert categories() == [
        "Esportes",
        "Filmes & Séries",
        "Documentários",
        "Notícias",
        "Infantil",
        "Abertos",
        "Variedades",
    ]


def test_br_master_contains_premiere_one_through_eight_as_p0_targets():
    targets = {item["name"]: item for item in master_channels()}
    for number in range(1, 9):
        item = targets[f"Premiere {number}"]
        assert item["category"] == "Esportes"
        assert item["priority"] == "P0"
        assert item["premium"] is True


def test_matching_is_accent_and_punctuation_tolerant():
    assert match_channel("sportv 2")["name"] == "SporTV 2"
    assert match_channel("HBO +")["name"] == "HBO Plus"
    assert match_channel("SportyNet+")["name"] == "SportyNet+"
    assert match_channel("TV Ra Tim Bum")["name"] == "TV Rá Tim Bum"


def test_flexible_matching_accepts_provider_quality_and_country_decorations():
    assert match_channel_flexible("BR | PREMIERE 1 FHD")["name"] == "Premiere 1"
    assert match_channel_flexible("BR - SPORTV 2 HD")["name"] == "SporTV 2"
    assert match_channel_flexible("BR | HBO FAMILY 1080P")["name"] == "HBO Family"
    assert match_channel_flexible("BR ESPN 6 UHD")["name"] == "ESPN 6"


def test_decorate_adds_stable_br_section_without_stream_data():
    item = decorate_channel({
        "id": "example",
        "name": "Telecine Action",
        "country": "BR",
        "categories": '["movies"]',
        "logo": None,
        "has_epg": False,
    })
    assert item["section"] == "Filmes & Séries"
    assert item["master_target"] is True
    assert item["priority"] == "P0"
    assert item["premium"] is True
    assert "url" not in item
