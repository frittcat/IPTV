package tv.familystream.client

import android.graphics.BitmapFactory
import android.graphics.Color
import android.graphics.drawable.GradientDrawable
import android.os.Bundle
import android.view.Gravity
import android.view.KeyEvent
import android.view.View
import android.view.ViewGroup
import android.widget.FrameLayout
import android.widget.GridLayout
import android.widget.HorizontalScrollView
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import androidx.activity.OnBackPressedCallback
import androidx.appcompat.app.AppCompatActivity
import androidx.media3.common.MediaItem
import androidx.media3.common.PlaybackException
import androidx.media3.common.Player
import androidx.media3.common.util.UnstableApi
import androidx.media3.datasource.DefaultHttpDataSource
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.exoplayer.source.DefaultMediaSourceFactory
import androidx.media3.ui.AspectRatioFrameLayout
import androidx.media3.ui.PlayerView
import java.net.HttpURLConnection
import java.net.URL

@UnstableApi
class MainActivity : AppCompatActivity() {
    private lateinit var api: FamilyStreamApi
    private lateinit var player: ExoPlayer
    private lateinit var playerView: PlayerView
    private lateinit var sideBar: LinearLayout
    private lateinit var contentHost: LinearLayout
    private lateinit var sectionTitle: TextView
    private lateinit var statusText: TextView
    private lateinit var fullscreenHost: FrameLayout

    private var backAction: (() -> Unit)? = null
    private var liveChannels: List<Channel> = emptyList()
    private var currentLiveIndex = -1
    private var currentSection = "Destaques"
    private var playerFullscreen = false
    private var playerOriginalParent: ViewGroup? = null
    private var playerOriginalIndex = -1
    private var playerOriginalLayoutParams: ViewGroup.LayoutParams? = null

    private val expandedSidebarWidth by lazy { dp(286) }
    private val collapsedSidebarWidth by lazy { dp(104) }
    private val serverUrl: String by lazy {
        intent.getStringExtra("server_url")
            ?.trimEnd('/')
            ?.takeIf { it.startsWith("http://") || it.startsWith("https://") }
            ?: BuildConfig.DEFAULT_SERVER_URL
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.decorView.systemUiVisibility = (
            View.SYSTEM_UI_FLAG_FULLSCREEN or
                View.SYSTEM_UI_FLAG_HIDE_NAVIGATION or
                View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
            )

        api = FamilyStreamApi(serverUrl, maxHeight = 2160)
        val httpFactory = DefaultHttpDataSource.Factory()
            .setAllowCrossProtocolRedirects(true)
            .setDefaultRequestProperties(api.requestHeaders())
        player = ExoPlayer.Builder(this)
            .setMediaSourceFactory(DefaultMediaSourceFactory(httpFactory))
            .build()
            .also { exo ->
                exo.setHandleAudioBecomingNoisy(true)
                exo.addListener(object : Player.Listener {
                    override fun onPlayerError(error: PlaybackException) {
                        if (::statusText.isInitialized) {
                            statusText.text = "Falha de reprodução · ${error.errorCodeName}"
                        }
                    }

                    override fun onPlaybackStateChanged(playbackState: Int) {
                        if (!::statusText.isInitialized) return
                        when (playbackState) {
                            Player.STATE_BUFFERING -> statusText.text = "Carregando stream…"
                            Player.STATE_READY -> if (player.playWhenReady) statusText.text = "Reproduzindo"
                            Player.STATE_ENDED -> statusText.text = "Reprodução finalizada"
                        }
                    }
                })
            }

        setContentView(buildTvShell())
        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                if (playerFullscreen) {
                    exitPlayerFullscreen()
                    return
                }
                val action = backAction
                if (action != null) {
                    backAction = null
                    action()
                } else if (sideBar.width < expandedSidebarWidth) {
                    animateSidebar(true)
                    sideBar.getChildAt(1)?.requestFocus()
                } else {
                    finish()
                }
            }
        })
        showHome("Destaques")
    }

    private fun buildTvShell(): View {
        val root = FrameLayout(this).apply {
            setBackgroundColor(Color.rgb(8, 10, 15))
            layoutParams = ViewGroup.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.MATCH_PARENT,
            )
        }

        val shell = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            setBackgroundColor(Color.rgb(8, 10, 15))
        }

        sideBar = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(dp(18), dp(20), dp(18), dp(20))
            background = rounded(Color.rgb(16, 20, 29), dp(18).toFloat())
            layoutParams = LinearLayout.LayoutParams(expandedSidebarWidth, ViewGroup.LayoutParams.MATCH_PARENT)
        }

        val brand = TextView(this).apply {
            text = "GaloDoidoTV"
            textSize = 23f
            setTextColor(Color.WHITE)
            setPadding(dp(14), 0, 0, dp(24))
        }
        sideBar.addView(brand)

        listOf("Ao Vivo", "Destaques", "Filmes", "Séries", "Infantil", "Explorar").forEach { label ->
            sideBar.addView(menuButton(label))
        }

        contentHost = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(26), dp(20), dp(30), dp(22))
            layoutParams = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.MATCH_PARENT, 1f)
        }

        shell.addView(sideBar)
        shell.addView(contentHost)
        root.addView(
            shell,
            FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT),
        )

        fullscreenHost = FrameLayout(this).apply {
            visibility = View.GONE
            setBackgroundColor(Color.BLACK)
            isFocusable = true
            isFocusableInTouchMode = false
        }
        root.addView(
            fullscreenHost,
            FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT),
        )
        return root
    }

    private fun menuButton(label: String): TextView = TextView(this).apply {
        text = label
        textSize = 19f
        gravity = Gravity.CENTER_VERTICAL
        setTextColor(Color.WHITE)
        isFocusable = true
        isFocusableInTouchMode = false
        setPadding(dp(18), 0, dp(12), 0)
        layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(58)).apply {
            bottomMargin = dp(6)
        }
        background = rounded(Color.TRANSPARENT, dp(12).toFloat())
        setOnFocusChangeListener { view, hasFocus ->
            (view as TextView).background = rounded(
                if (hasFocus) Color.rgb(55, 65, 84) else Color.TRANSPARENT,
                dp(12).toFloat(),
            )
            animateSidebar(hasFocus)
        }
        setOnClickListener {
            backAction = null
            currentSection = label
            when (label) {
                "Ao Vivo" -> showLive()
                "Destaques" -> showHome("Destaques")
                "Filmes" -> showCatalog("movie")
                "Séries" -> showCatalog("series")
                "Infantil" -> showKids()
                "Explorar" -> showHome("Explorar")
            }
        }
    }

    private fun prepareScreen(title: String, status: String = "Conectando ao GaloDoidoTV…") {
        contentHost.removeAllViews()
        sectionTitle = TextView(this).apply {
            text = title
            textSize = 31f
            setTextColor(Color.WHITE)
            setPadding(0, 0, 0, dp(10))
        }
        statusText = TextView(this).apply {
            text = status
            textSize = 15f
            setTextColor(Color.rgb(174, 182, 199))
            setPadding(0, dp(8), 0, 0)
        }
        contentHost.addView(sectionTitle)
    }

    private fun finishScreen(body: View) {
        contentHost.addView(
            body,
            LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f),
        )
        contentHost.addView(statusText)
    }

    private fun showHome(title: String) {
        currentSection = title
        backAction = null
        prepareScreen(title, "Carregando catálogo…")
        val loading = centeredMessage("Sincronizando catálogo e canais…")
        finishScreen(loading)
        Thread {
            runCatching { api.home() }
                .onSuccess { feed -> runOnUiThread { renderHome(feed, title) } }
                .onFailure { error -> runOnUiThread { showNetworkError(title, error) } }
        }.start()
    }

    private fun renderHome(feed: HomeFeed, title: String) {
        prepareScreen(title, "${feed.live.size} canais em destaque · ${feed.movies.size} filmes · ${feed.series.size} séries")
        val scroll = ScrollView(this)
        val column = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(0, 0, 0, dp(20))
        }

        val hero = FrameLayout(this).apply {
            layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(400)).apply {
                bottomMargin = dp(20)
            }
        }
        playerView = buildPlayerView().apply {
            layoutParams = FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.MATCH_PARENT,
            )
        }
        hero.addView(playerView)
        column.addView(hero)

        if (feed.movies.isNotEmpty()) column.addView(buildCatalogRail("Filmes", feed.movies) { showMovieDetail(it) })
        if (feed.series.isNotEmpty()) column.addView(buildCatalogRail("Séries", feed.series) { showSeriesDetail(it) })
        if (feed.live.isEmpty() && feed.movies.isEmpty() && feed.series.isEmpty()) {
            column.addView(centeredMessage("Nenhum conteúdo publicado ainda. Execute a sincronização no servidor."))
        }

        scroll.addView(column)
        finishScreen(scroll)
        feed.live.firstOrNull()?.let { channel ->
            liveChannels = feed.live
            currentLiveIndex = 0
            play("live", channel.id, channel.name, requestFocus = false)
        }
    }

    private fun showLive() {
        currentSection = "Ao Vivo"
        backAction = null
        prepareScreen("Ao Vivo", "Carregando canais publicados…")
        finishScreen(centeredMessage("Preparando TV ao vivo…"))
        Thread {
            runCatching { if (liveChannels.isNotEmpty()) liveChannels else api.channels() }
                .onSuccess { channels ->
                    liveChannels = channels
                    runOnUiThread { renderLive(channels) }
                }
                .onFailure { error -> runOnUiThread { showNetworkError("Ao Vivo", error) } }
        }.start()
    }

    private fun renderLive(channels: List<Channel>) {
        prepareScreen("Ao Vivo", "${channels.size} canais disponíveis · OK no player = tela cheia · CH+/CH− troca rapidamente")
        if (channels.isEmpty()) {
            finishScreen(centeredMessage("Nenhum canal saudável publicado."))
            return
        }

        val split = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        val channelScroll = ScrollView(this).apply {
            layoutParams = LinearLayout.LayoutParams(dp(360), ViewGroup.LayoutParams.MATCH_PARENT).apply {
                marginEnd = dp(20)
            }
            background = rounded(Color.rgb(16, 20, 29), dp(16).toFloat())
        }
        val list = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(12), dp(12), dp(12), dp(12))
        }
        channels.forEachIndexed { index, channel ->
            list.addView(textAction(channel.name) {
                currentLiveIndex = index
                play("live", channel.id, channel.name)
            })
        }
        channelScroll.addView(list)

        playerView = buildPlayerView().apply {
            layoutParams = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.MATCH_PARENT, 1f)
        }
        split.addView(channelScroll)
        split.addView(playerView)
        finishScreen(split)

        val index = currentLiveIndex.takeIf { it in channels.indices } ?: 0
        currentLiveIndex = index
        play("live", channels[index].id, channels[index].name, requestFocus = false)
        list.getChildAt(index)?.requestFocus()
    }

    private fun showCatalog(itemType: String) {
        val title = if (itemType == "movie") "Filmes" else "Séries"
        currentSection = title
        backAction = null
        prepareScreen(title, "Carregando catálogo…")
        finishScreen(centeredMessage("Organizando $title…"))
        Thread {
            runCatching { api.catalog(itemType) }
                .onSuccess { items -> runOnUiThread { renderCatalog(title, items) } }
                .onFailure { error -> runOnUiThread { showNetworkError(title, error) } }
        }.start()
    }

    private fun renderCatalog(title: String, items: List<CatalogItem>) {
        prepareScreen(title, "${items.size} itens publicados")
        val scroll = ScrollView(this)
        val grid = GridLayout(this).apply {
            columnCount = 5
            useDefaultMargins = false
            setPadding(0, dp(4), 0, dp(24))
        }
        items.forEach { item ->
            grid.addView(catalogCard(item) {
                if (item.itemType == "series") showSeriesDetail(item) else showMovieDetail(item)
            })
        }
        if (items.isEmpty()) grid.addView(centeredMessage("Nenhum item publicado nesta seção."))
        scroll.addView(grid)
        finishScreen(scroll)
        grid.getChildAt(0)?.requestFocus()
    }

    private fun showMovieDetail(item: CatalogItem) {
        backAction = { showCatalog("movie") }
        prepareScreen(item.title, if (item.playable) "Pronto para reproduzir" else "Sem stream publicado")
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            setPadding(0, dp(8), 0, dp(12))
        }
        val poster = ImageView(this).apply {
            scaleType = ImageView.ScaleType.CENTER_CROP
            background = rounded(Color.rgb(28, 33, 44), dp(16).toFloat())
            layoutParams = LinearLayout.LayoutParams(dp(310), ViewGroup.LayoutParams.MATCH_PARENT).apply {
                marginEnd = dp(28)
            }
        }
        loadImage(item.poster, poster)

        val info = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER_VERTICAL
            layoutParams = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.MATCH_PARENT, 1f)
        }
        info.addView(bigTitle(item.title))
        info.addView(metaText(listOfNotNull(item.year?.toString(), item.rating?.let { "★ %.1f".format(it) }).joinToString("  ·  ")))
        info.addView(bodyText(item.plot ?: "Sem sinopse disponível."))
        if (item.playable) {
            info.addView(textAction("▶ Assistir") { playInDetails("vod", item.id, item.title) })
        }
        info.addView(textAction("← Voltar para Filmes") { showCatalog("movie") })
        root.addView(poster)
        root.addView(info)
        finishScreen(root)
        info.getChildAt(if (item.playable) 3 else 2)?.requestFocus()
    }

    private fun showSeriesDetail(item: CatalogItem) {
        backAction = { showCatalog("series") }
        prepareScreen(item.title, "Carregando temporadas…")
        finishScreen(centeredMessage("Abrindo série…"))
        Thread {
            runCatching { api.seriesDetail(item.id) }
                .onSuccess { detail -> runOnUiThread { renderSeriesDetail(detail) } }
                .onFailure { error -> runOnUiThread { showNetworkError(item.title, error) } }
        }.start()
    }

    private fun renderSeriesDetail(detail: SeriesDetail) {
        backAction = { showCatalog("series") }
        prepareScreen(detail.title, "${detail.seasons.size} temporadas")
        val scroll = ScrollView(this)
        val column = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(0, dp(6), 0, dp(24))
        }
        column.addView(bigTitle(detail.title))
        column.addView(metaText(detail.year?.toString() ?: ""))
        column.addView(bodyText(detail.plot ?: "Sem sinopse disponível."))
        column.addView(sectionLabel("TEMPORADAS"))
        detail.seasons.forEach { season ->
            column.addView(textAction("Temporada ${season.number} · ${season.episodeCount} episódios") {
                showEpisodes(detail, season)
            })
        }
        column.addView(textAction("← Voltar para Séries") { showCatalog("series") })
        scroll.addView(column)
        finishScreen(scroll)
        column.getChildAt(4.coerceAtMost(column.childCount - 1))?.requestFocus()
    }

    private fun showEpisodes(detail: SeriesDetail, season: Season) {
        backAction = { renderSeriesDetail(detail) }
        prepareScreen("${detail.title} · Temporada ${season.number}", "Carregando episódios…")
        finishScreen(centeredMessage("Buscando episódios…"))
        Thread {
            runCatching { api.episodes(detail.id, season.number) }
                .onSuccess { episodes -> runOnUiThread { renderEpisodes(detail, season, episodes) } }
                .onFailure { error -> runOnUiThread { showNetworkError(detail.title, error) } }
        }.start()
    }

    private fun renderEpisodes(detail: SeriesDetail, season: Season, episodes: List<Episode>) {
        backAction = { renderSeriesDetail(detail) }
        prepareScreen("${detail.title} · T${season.number}", "${episodes.size} episódios")
        val scroll = ScrollView(this)
        val list = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(0, dp(4), 0, dp(24))
        }
        episodes.forEach { episode ->
            val label = "T%02dE%02d  %s%s".format(
                episode.season,
                episode.number,
                episode.title,
                if (episode.playable) "  ▶" else "",
            )
            list.addView(textAction(label) {
                if (episode.playable) playInDetails("episode", episode.id, label)
            })
        }
        list.addView(textAction("← Voltar para Temporadas") { renderSeriesDetail(detail) })
        scroll.addView(list)
        finishScreen(scroll)
        list.getChildAt(0)?.requestFocus()
    }

    private fun showKids() {
        currentSection = "Infantil"
        backAction = null
        prepareScreen("Infantil", "Modo infantil · catálogo autorizado")
        val column = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER
        }
        column.addView(bigTitle("Espaço Infantil"))
        column.addView(bodyText("A navegação infantil e o controle parental usarão o mesmo catálogo do GaloDoidoTV, com filtros por perfil."))
        column.addView(textAction("Ver filmes disponíveis") { showCatalog("movie") })
        column.addView(textAction("Ver séries disponíveis") { showCatalog("series") })
        finishScreen(column)
        column.getChildAt(2)?.requestFocus()
    }

    private fun playInDetails(kind: String, id: String, title: String) {
        prepareScreen(title, "Resolvendo melhor fonte para esta TV…")
        playerView = buildPlayerView()
        finishScreen(playerView)
        play(kind, id, title)
    }

    private fun play(kind: String, id: String, title: String, requestFocus: Boolean = true) {
        statusText.text = "Analisando fontes para $title…"
        Thread {
            runCatching { api.resolvePlayback(kind, id) }
                .onSuccess { resolution ->
                    runOnUiThread {
                        val item = MediaItem.Builder()
                            .setUri(resolution.url)
                            .apply { resolution.mimeType?.let { setMimeType(it) } }
                            .setMediaId("$kind:$id")
                            .build()
                        player.setMediaItem(item)
                        player.prepare()
                        player.playWhenReady = true
                        val quality = listOfNotNull(
                            resolution.videoCodec?.uppercase(),
                            resolution.height?.let { "${it}p" },
                            resolution.audioCodec?.uppercase(),
                        ).joinToString(" · ")
                        statusText.text = if (quality.isBlank()) title else "$title · $quality"
                        if (requestFocus) playerView.requestFocus()
                    }
                }
                .onFailure { error ->
                    runOnUiThread {
                        statusText.text = "Não foi possível reproduzir $title · ${error.message ?: error.javaClass.simpleName}"
                    }
                }
        }.start()
    }

    private fun buildPlayerView(): PlayerView = PlayerView(this).apply {
        player = this@MainActivity.player
        useController = true
        controllerAutoShow = true
        controllerShowTimeoutMs = 3500
        resizeMode = AspectRatioFrameLayout.RESIZE_MODE_FIT
        setShowBuffering(PlayerView.SHOW_BUFFERING_WHEN_PLAYING)
        background = rounded(Color.BLACK, dp(14).toFloat())
        isFocusable = true
        isFocusableInTouchMode = false
        setOnClickListener {
            if (!playerFullscreen) enterPlayerFullscreen(this)
        }
        setOnKeyListener { _, keyCode, event ->
            if (!playerFullscreen && event.action == KeyEvent.ACTION_DOWN &&
                keyCode in setOf(KeyEvent.KEYCODE_DPAD_CENTER, KeyEvent.KEYCODE_ENTER, KeyEvent.KEYCODE_NUMPAD_ENTER)
            ) {
                enterPlayerFullscreen(this)
                true
            } else {
                false
            }
        }
    }

    private fun enterPlayerFullscreen(view: PlayerView) {
        if (playerFullscreen) return
        val parent = view.parent as? ViewGroup ?: return
        playerOriginalParent = parent
        playerOriginalIndex = parent.indexOfChild(view)
        playerOriginalLayoutParams = view.layoutParams
        parent.removeView(view)

        fullscreenHost.removeAllViews()
        fullscreenHost.visibility = View.VISIBLE
        fullscreenHost.addView(
            view,
            FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT),
        )
        playerFullscreen = true
        view.requestFocus()
        view.showController()
    }

    private fun exitPlayerFullscreen() {
        if (!playerFullscreen) return
        val view = fullscreenHost.getChildAt(0) as? PlayerView
        fullscreenHost.removeAllViews()
        fullscreenHost.visibility = View.GONE
        playerFullscreen = false

        val parent = playerOriginalParent
        val params = playerOriginalLayoutParams
        if (view != null && parent != null && params != null) {
            val index = playerOriginalIndex.coerceIn(0, parent.childCount)
            parent.addView(view, index, params)
            view.requestFocus()
        }
        playerOriginalParent = null
        playerOriginalLayoutParams = null
        playerOriginalIndex = -1
    }

    private fun buildCatalogRail(title: String, items: List<CatalogItem>, click: (CatalogItem) -> Unit): View {
        val block = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply {
                bottomMargin = dp(18)
            }
        }
        block.addView(sectionLabel(title.uppercase()))
        val scroll = HorizontalScrollView(this).apply {
            isHorizontalScrollBarEnabled = false
            descendantFocusability = ViewGroup.FOCUS_AFTER_DESCENDANTS
        }
        val row = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            setPadding(0, dp(4), dp(20), dp(8))
        }
        items.forEach { row.addView(catalogCard(it) { click(it) }) }
        scroll.addView(row)
        block.addView(scroll)
        return block
    }

    private fun catalogCard(item: CatalogItem, click: () -> Unit): View {
        val card = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            isFocusable = true
            isFocusableInTouchMode = false
            background = rounded(Color.rgb(22, 27, 37), dp(14).toFloat())
            setPadding(dp(7), dp(7), dp(7), dp(10))
            layoutParams = ViewGroup.MarginLayoutParams(dp(210), dp(300)).apply {
                marginEnd = dp(14)
                bottomMargin = dp(14)
            }
            setOnClickListener { click() }
            setOnFocusChangeListener { view, focused ->
                view.animate().scaleX(if (focused) 1.055f else 1f).scaleY(if (focused) 1.055f else 1f).setDuration(120).start()
                view.background = rounded(
                    if (focused) Color.rgb(55, 67, 88) else Color.rgb(22, 27, 37),
                    dp(14).toFloat(),
                )
            }
        }
        val image = ImageView(this).apply {
            scaleType = ImageView.ScaleType.CENTER_CROP
            background = rounded(Color.rgb(35, 40, 52), dp(10).toFloat())
            layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(222))
        }
        loadImage(item.poster, image)
        val title = TextView(this).apply {
            text = item.title
            textSize = 15f
            maxLines = 2
            setTextColor(Color.WHITE)
            setPadding(dp(5), dp(8), dp(5), 0)
        }
        val meta = TextView(this).apply {
            text = listOfNotNull(item.year?.toString(), if (item.playable) "▶" else null).joinToString("  ")
            textSize = 12f
            setTextColor(Color.rgb(172, 181, 198))
            setPadding(dp(5), dp(3), dp(5), 0)
        }
        card.addView(image)
        card.addView(title)
        card.addView(meta)
        return card
    }

    private fun textAction(label: String, click: () -> Unit): TextView = TextView(this).apply {
        text = label
        textSize = 17f
        setTextColor(Color.WHITE)
        gravity = Gravity.CENTER_VERTICAL
        isFocusable = true
        isFocusableInTouchMode = false
        setPadding(dp(16), 0, dp(12), 0)
        layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(54)).apply {
            bottomMargin = dp(5)
        }
        background = rounded(Color.rgb(28, 34, 46), dp(11).toFloat())
        setOnClickListener { click() }
        setOnFocusChangeListener { view, focused ->
            (view as TextView).background = rounded(
                if (focused) Color.rgb(70, 83, 108) else Color.rgb(28, 34, 46),
                dp(11).toFloat(),
            )
        }
    }

    private fun sectionLabel(label: String): TextView = TextView(this).apply {
        text = label
        textSize = 15f
        setTextColor(Color.rgb(153, 170, 202))
        setPadding(dp(4), dp(8), 0, dp(8))
    }

    private fun bigTitle(value: String): TextView = TextView(this).apply {
        text = value
        textSize = 32f
        setTextColor(Color.WHITE)
        setPadding(0, 0, 0, dp(8))
    }

    private fun metaText(value: String): TextView = TextView(this).apply {
        text = value
        textSize = 16f
        setTextColor(Color.rgb(166, 178, 199))
        setPadding(0, 0, 0, dp(14))
    }

    private fun bodyText(value: String): TextView = TextView(this).apply {
        text = value
        textSize = 18f
        setTextColor(Color.rgb(220, 224, 233))
        maxLines = 8
        setLineSpacing(0f, 1.15f)
        setPadding(0, 0, 0, dp(22))
    }

    private fun centeredMessage(value: String): View = FrameLayout(this).apply {
        addView(
            TextView(this@MainActivity).apply {
                text = value
                textSize = 19f
                gravity = Gravity.CENTER
                setTextColor(Color.rgb(185, 193, 209))
            },
            FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT),
        )
    }

    private fun showNetworkError(title: String, error: Throwable) {
        prepareScreen(title, "Servidor indisponível")
        val column = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER
        }
        column.addView(bigTitle("Não consegui carregar esta seção"))
        column.addView(bodyText("${error.message ?: error.javaClass.simpleName}\n\nServidor: $serverUrl"))
        column.addView(textAction("Tentar novamente") {
            when (currentSection) {
                "Ao Vivo" -> showLive()
                "Filmes" -> showCatalog("movie")
                "Séries" -> showCatalog("series")
                "Infantil" -> showKids()
                else -> showHome(currentSection)
            }
        })
        finishScreen(column)
        column.getChildAt(2)?.requestFocus()
    }

    private fun loadImage(url: String?, image: ImageView) {
        if (url.isNullOrBlank() || !(url.startsWith("http://") || url.startsWith("https://"))) return
        image.tag = url
        Thread {
            runCatching {
                val connection = (URL(url).openConnection() as HttpURLConnection).apply {
                    connectTimeout = 5_000
                    readTimeout = 7_000
                    instanceFollowRedirects = true
                }
                try {
                    if (connection.responseCode !in 200..299) return@runCatching null
                    BitmapFactory.decodeStream(connection.inputStream)
                } finally {
                    connection.disconnect()
                }
            }.getOrNull()?.let { bitmap ->
                runOnUiThread {
                    if (image.tag == url) image.setImageBitmap(bitmap)
                }
            }
        }.start()
    }

    private fun animateSidebar(expanded: Boolean) {
        val params = sideBar.layoutParams
        params.width = if (expanded) expandedSidebarWidth else collapsedSidebarWidth
        sideBar.layoutParams = params
    }

    override fun dispatchKeyEvent(event: KeyEvent): Boolean {
        if (event.action == KeyEvent.ACTION_DOWN && currentSection == "Ao Vivo" && liveChannels.isNotEmpty()) {
            when (event.keyCode) {
                KeyEvent.KEYCODE_CHANNEL_UP -> {
                    zap(-1)
                    return true
                }
                KeyEvent.KEYCODE_CHANNEL_DOWN -> {
                    zap(1)
                    return true
                }
            }
        }
        return super.dispatchKeyEvent(event)
    }

    private fun zap(delta: Int) {
        if (liveChannels.isEmpty()) return
        currentLiveIndex = if (currentLiveIndex !in liveChannels.indices) 0 else {
            (currentLiveIndex + delta + liveChannels.size) % liveChannels.size
        }
        val channel = liveChannels[currentLiveIndex]
        play("live", channel.id, channel.name, requestFocus = false)
    }

    private fun rounded(color: Int, radius: Float) = GradientDrawable().apply {
        setColor(color)
        cornerRadius = radius
    }

    private fun dp(value: Int): Int = (value * resources.displayMetrics.density).toInt()

    override fun onDestroy() {
        player.release()
        super.onDestroy()
    }
}
