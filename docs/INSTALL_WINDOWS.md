# Instalação no Windows

Instale Docker Desktop com integração WSL2 e Git. No PowerShell, execute `git clone https://github.com/frittcat/IPTV.git`, entre na pasta e rode `.\scripts\install.ps1`. O script cria `.env`, baixa imagens, compila o backend e inicia os serviços.

Confirme com `docker compose ps`. O painel estará em `http://localhost:8080/admin/`, a documentação em `http://localhost:8080/docs` e o Dispatcharr em `http://localhost:9191`.
