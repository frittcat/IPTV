# VOD remoto v0.2

O FamilyStream mantém metadata, direitos, posters, NFO e arquivos `.strm`; não mantém filmes ou episódios completos. O `.strm` aponta para `/vod/stream/{vod_id}`, e o backend resolve o provider cadastrado no momento da reprodução.

Os providers públicos iniciais são Internet Archive, Wikimedia Commons e NASA. Itens com direitos claramente compatíveis — Public Domain, CC0, CC BY ou CC BY-SA — podem ser publicados automaticamente; itens ambíguos permanecem no banco com `rights_status=review_required` e `published=false`.

A sincronização pode ser iniciada com `POST /api/v1/vod/sync?provider=archive_org&limit=10`. O catálogo paginado está em `GET /api/v1/vod?page=1&page_size=50&item_type=movie`. O proxy aceita `GET`, `HEAD` e o cabeçalho `Range`, sem armazenar o vídeo completo.

M3U VOD autorizado pode ser adaptado pela classe `M3UVODProvider`, que diferencia Live TV, filmes, séries e conteúdo desconhecido. Xtream requer `XTREAM_URL`, `XTREAM_USERNAME` e `XTREAM_PASSWORD` fornecidos legitimamente pelo administrador; essas variáveis nunca devem ser versionadas.
