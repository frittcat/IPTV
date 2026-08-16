# GaloDoidoTV Android TV — referência de paridade e acabamento

Objetivo: reproduzir a experiência funcional e visual observada no APK de referência com implementação própria do GaloDoidoTV, mantendo o app mais estável, rápido e simples de operar por controle remoto.

## Prioridade P0 — identidade e abertura

- [x] Nome visível GaloDoidoTV.
- [x] Banner Android TV próprio.
- [x] Corrigir launcher para usar uma única marca limpa, evitando sensação de imagens sobrepostas.
- [x] Splash dedicada antes da Home, com logo GaloDoidoTV grande e visível.
- [x] Fade curto da splash para a Home.
- [x] Barra lateral sem quebra vertical de "GaloDoidoTV" e labels do menu sem quebra de linha.
- [ ] Substituir definitivamente qualquer identificador visual legado que ainda seja encontrado em telas secundárias.

## Prioridade P0 — player Live TV

- [x] Reprodução Live de ponta a ponta via resolver + gateway + ExoPlayer.
- [x] Buffering interno sem spinner padrão visível.
- [x] Não abrir automaticamente timeline/controles do ExoPlayer durante buffering normal.
- [ ] Player Live sem aparência de player genérico; overlay próprio do GaloDoidoTV.
- [ ] Troca de canal mais seca e rápida, mantendo o player aquecido entre canais.
- [ ] Fallback automático para a próxima origem saudável quando uma origem falhar durante a abertura.
- [ ] Mensagem de erro curta e amigável; detalhes técnicos apenas em diagnóstico.
- [ ] CH+/CH- e setas com comportamento consistente em toda a tela Ao Vivo.

## Prioridade P1 — navegação e layout TV

- [ ] Sidebar compacta com ícones quando recolhida e texto quando expandida.
- [ ] Foco D-pad bem visível, sem saltos inesperados.
- [ ] Home com preview Live integrado e trilhos de conteúdo.
- [ ] Ao Vivo com lista lateral, logo do canal, país/categoria e EPG atual/próximo quando disponível.
- [ ] Transições discretas e rápidas, sem animações que atrasem o uso.
- [ ] Back sempre previsível: player -> detalhe/lista -> Home -> sair.

## Prioridade P1 — qualidade do catálogo Live

- [ ] Priorizar França, Brasil e Portugal antes de canais internacionais.
- [ ] Agrupar por país e categoria.
- [ ] Logos consistentes e cacheados.
- [ ] EPG atual/próximo quando houver guia disponível.
- [ ] Ocultar automaticamente streams offline, falsos positivos HTTP e origens instáveis.
- [ ] Revalidar saúde em segundo plano sem interromper reprodução.

## Prioridade P1 — Filmes e Séries

- [ ] Catálogo real publicado com direitos aprovados.
- [ ] Detalhes de filme: capa, backdrop, sinopse, ano, duração, áudio/legendas e botão Assistir.
- [ ] Séries com temporadas e episódios reais.
- [ ] Retomar reprodução / continuar assistindo.
- [ ] Seleção de áudio e legenda antes ou durante a reprodução.
- [ ] Player VOD com controles próprios, mantendo buffering visualmente discreto.

## Prioridade P2 — desempenho e robustez

- [ ] Pré-resolver próximo canal ao navegar pela lista.
- [ ] Cache curto de manifests/metadata sem expor URLs privadas.
- [ ] Telemetria local de tempo de abertura, falhas e fallback.
- [ ] Perfil por dispositivo/codec para evitar fontes incompatíveis.
- [ ] Testes automatizados para gateway HLS, Range, MIME, fallback, headers e navegação Android TV.

## Critério de aceite

A experiência final deve parecer um aplicativo de TV dedicado: abre com identidade clara, responde imediatamente ao controle remoto, não expõe elementos técnicos do player, não mostra buffering como parte normal da interface, troca canais de forma rápida e organiza conteúdo de maneira simples. A referência serve como alvo de experiência; o código, branding e arquitetura permanecem próprios do GaloDoidoTV.
