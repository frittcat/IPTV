from backend.app_v03 import app
from backend.gateway_runtime import GatewaySessionStore


def test_v03_replaces_legacy_media_routes_once():
    paths = [getattr(route, "path", None) for route in app.router.routes]
    assert paths.count("/live/stream/{channel_id}") == 1
    assert paths.count("/vod/stream/{vod_id}") == 1
    assert paths.count("/api/v1/play/live/{channel_id}") == 1
    assert paths.count("/api/v1/play/vod/{vod_id}") == 1
    assert paths.count("/api/v1/gateway/hls/{session_id}/{resource_id}") == 1
    assert paths.count("/api/v1/playback/profiles") == 1
    assert paths.count("/api/v1/playback/diagnostics/{kind}/{item_id}") == 1


def test_hls_registry_keeps_provider_url_and_headers_server_side():
    store = GatewaySessionStore(ttl_seconds=60)
    session = store.create({
        "Authorization": "Bearer provider-secret",
        "Cookie": "provider=session-secret",
    }, profile_id="android-tv-modern")
    upstream = "https://media.example/live/master.m3u8?token=private-token"
    resource_id = store.register(session.id, upstream)

    # Client-facing identifiers are opaque random values. Neither credentials nor
    # tokenized provider URLs have to be embedded in rewritten HLS manifests.
    assert "private-token" not in session.id
    assert "private-token" not in resource_id
    assert "provider-secret" not in session.id
    assert "provider-secret" not in resource_id

    resolved = store.resolve(session.id, resource_id)
    assert resolved is not None
    resolved_session, resolved_url = resolved
    assert resolved_url == upstream
    assert resolved_session.headers["Authorization"] == "Bearer provider-secret"
    assert resolved_session.headers["Cookie"] == "provider=session-secret"
    assert resolved_session.profile_id == "android-tv-modern"


def test_unknown_hls_resource_is_not_resolved():
    store = GatewaySessionStore(ttl_seconds=60)
    session = store.create({})
    assert store.resolve(session.id, "not-a-real-resource") is None
    assert store.resolve("not-a-real-session", "x") is None
