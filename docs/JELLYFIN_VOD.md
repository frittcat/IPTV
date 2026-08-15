# Jellyfin VOD remoto

Adicione `data/vod/movies` e `data/vod/shows` como bibliotecas no Jellyfin após iniciar o Compose. O FamilyStream gera `.strm` com URLs estáveis locais e, quando houver metadata aprovada, cria a estrutura necessária para indexação.

A compatibilidade de seek, pause/resume, legendas embedded e sidecar depende do upstream e do cliente Jellyfin. O proxy preserva `Range`, `Content-Range`, `Accept-Ranges`, `Content-Type` e headers autorizados; ele não faz transcode do vídeo nem armazena o arquivo inteiro. Quando o stream upstream for HLS, a origem precisa fornecer um manifest compatível com o cliente ou com o Dispatcharr.

A versão do Jellyfin deve ser verificada pelo administrador antes de habilitar bibliotecas remotas em produção. A integração automática de refresh por API ainda depende de `JELLYFIN_URL` e `JELLYFIN_API_KEY`, que permanecem opcionais e nunca devem ser versionados.
