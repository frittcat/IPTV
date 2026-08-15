# Segurança v0.2

O backend rejeita esquemas que não sejam HTTP/HTTPS e bloqueia localhost, loopback, redes privadas IPv4/IPv6, link-local, endereços reservados e endpoints de metadata após resolução DNS. Fontes LAN somente devem ser aceitas mediante uma política confiável explícita; não foram adicionados atalhos para contornar geoblocking, DRM ou autenticação.

O painel exige HTTP Basic com senha armazenada como hash PBKDF2-SHA256 em `ADMIN_PASSWORD_HASH`. O instalador gera uma senha administrativa aleatória e um PostgreSQL password aleatório no `.env` local. Nenhum `.env`, token, cookie, senha, URL Xtream ou API key deve entrar no Git.

O proxy VOD encaminha apenas URLs registradas no banco e não expõe credenciais nos arquivos `.strm`. O cache permanente de vídeo permanece desabilitado. O CI valida testes, compilação e build da imagem; containers não foram runtime validated nesta sessão porque Docker não está disponível no ambiente atual.
