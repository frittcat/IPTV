# Dispatcharr v0.2

O Compose inicia Dispatcharr em `http://localhost:9191`. A documentação oficial atual expõe o Swagger em `/swagger/`; como os endpoints mutáveis podem mudar entre releases, o FamilyStream consulta `/swagger.json`, `/api/schema/` e `/openapi.json` em runtime e expõe o resultado em `/api/v1/dispatcharr/status`.

A integração segura recomendada é importar no Dispatcharr as URLs estáveis do FamilyStream: `http://familystream-backend:8080/family-tv.m3u` e `http://familystream-backend:8080/family-tv.xml`. O Jellyfin pode então consumir a saída M3U/XMLTV do Dispatcharr. A URL M3U do FamilyStream aponta para `/live/stream/{channel_id}`, que escolhe primary/fallback conforme health check.

Se a instalação do Dispatcharr exigir autenticação para operações da API, configure `DISPATCHARR_USERNAME` e `DISPATCHARR_PASSWORD` somente no `.env`. Quando o Swagger não estiver acessível, o endpoint indica `manual_configuration_required=true`; não são enviados POSTs especulativos para endpoints não confirmados.
