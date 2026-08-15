# Fontes

| Name | Homepage | Feed URL/API | Type | Country | License/provenance | Date checked | Imported channels | Working channels | Notes |
|---|---|---|---|---|---|---|---:|---:|---|
| IPTV-org API | https://github.com/iptv-org/api | https://iptv-org.github.io/api/streams.json | API | Internacional | Dados comunitários; verificar origem de cada stream | 2026-08-15 | Após `/api/sync` | Após health check | Fonte estruturada principal |
| IPTV-org playlists | https://github.com/iptv-org/iptv | https://iptv-org.github.io/iptv/index.m3u | M3U | Internacional | Links públicos mantidos pelo projeto; uso deve respeitar a origem | 2026-08-15 | Próxima etapa | Próxima etapa | Inclui playlists por país/categoria |
| Free-TV IPTV | https://github.com/Free-TV/IPTV | https://raw.githubusercontent.com/Free-TV/IPTV/master/playlist.m3u8 | M3U | Internacional | Projeto independente; verificar licença e procedência por item | 2026-08-15 | Próxima etapa | Próxima etapa | Tratar como fonte independente |
| Dispatcharr | https://github.com/Dispatcharr/dispatcharr | Docker image `ghcr.io/dispatcharr/dispatcharr:latest` | Middleware | N/A | AGPL-3.0 | 2026-08-15 | N/A | N/A | Proxy, M3U, XMLTV, HDHR e failover |
| Jellyfin | https://jellyfin.org | Integração local M3U/XMLTV | Media server | N/A | Projeto open source; consultar licença oficial | 2026-08-15 | N/A | N/A | Interface familiar final |

## Política

A aplicação não publica automaticamente fontes protegidas por DRM, autenticação, tokens privados ou geoblocking. Conteúdo VOD somente deve ser adicionado quando a licença permitir reutilização e redistribuição por URL remota.
