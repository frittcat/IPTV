# Live TV v0.2

A sincronização importa IPTV-org e Free-TV, bloqueia DMCA/NSFW, normaliza metadados e registra candidatos como `new`. Um canal somente passa a `published=1` depois de um health check que produza `healthy` ou `degraded` dentro do limiar configurado.

O health check preserva `Referer` e `User-Agent`, solicita uma faixa pequena, mede a latência do manifest e registra o resultado em `stream_health`. O endpoint operacional é `GET /api/health-check?limit=20`; em produção ele deve ser executado pelo scheduler com concorrência controlada, nunca contra milhares de URLs simultaneamente.

A playlist publicada usa `/live/stream/{channel_id}` em vez da URL upstream. O proxy ordena streams por primary e score, testa candidatos e encaminha o primeiro disponível. O comportamento de failover foi implementado no backend; a integração nativa do Dispatcharr depende do Swagger da versão instalada e não é forçada por endpoints presumidos.
