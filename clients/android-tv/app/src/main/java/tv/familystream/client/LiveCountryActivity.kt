package tv.familystream.client

import android.content.Intent
import android.graphics.Color
import android.graphics.drawable.GradientDrawable
import android.os.Bundle
import android.view.Gravity
import android.view.KeyEvent
import android.view.View
import android.view.ViewGroup
import android.widget.FrameLayout
import android.widget.HorizontalScrollView
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

@UnstableApi
class LiveCountryActivity : AppCompatActivity() {
    private lateinit var api: FamilyStreamApi
    private lateinit var player: ExoPlayer
    private lateinit var playerView: PlayerView
    private lateinit var channelList: LinearLayout
    private lateinit var statusText: TextView
    private lateinit var fullscreenHost: FrameLayout
    private lateinit var categoryScroll: HorizontalScrollView

    private val countryButtons = linkedMapOf<String, TextView>()
    private val categoryButtons = linkedMapOf<String, TextView>()
    private var channels: List<Channel> = emptyList()
    private var currentIndex = -1
    private var currentCountry = "BR"
    private var currentSection = ""
    private var playerFullscreen = false
    private var playerOriginalParent: ViewGroup? = null
    private var playerOriginalIndex = -1
    private var playerOriginalLayoutParams: ViewGroup.LayoutParams? = null

    private val brSections = listOf(
        "" to "TODOS",
        "Esportes" to "ESPORTES",
        "Filmes & Séries" to "FILMES & SÉRIES",
        "Documentários" to "DOCUMENTÁRIOS",
        "Notícias" to "NOTÍCIAS",
        "Infantil" to "INFANTIL",
        "Abertos" to "ABERTOS",
        "Variedades" to "VARIEDADES",
    )

    private val serverUrl: String by lazy {
        intent.getStringExtra("server_url")
            ?.trimEnd('/')
            ?.takeIf { it.startsWith("http://") || it.startsWith("https://") }
            ?: getSharedPreferences("galodoidotv", MODE_PRIVATE)
                .getString("server_url", null)
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
                            Player.STATE_READY -> if (player.playWhenReady && currentIndex in channels.indices) {
                                statusText.text = channels[currentIndex].name
                            }
                            Player.STATE_ENDED -> statusText.text = "Reprodução finalizada"
                        }
                    }
                })
            }

        setContentView(buildScreen())
        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                if (playerFullscreen) exitPlayerFullscreen() else returnToMain()
            }
        })
        loadCountry("BR")
    }

    private fun buildScreen(): View {
        val root = FrameLayout(this).apply {
            setBackgroundColor(Color.rgb(8, 10, 15))
        }
        val shell = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(28), dp(18), dp(28), dp(18))
        }

        shell.addView(TextView(this).apply {
            text = "GaloDoidoTV · Ao Vivo"
            textSize = 28f
            setTextColor(Color.WHITE)
            setPadding(dp(4), 0, 0, dp(8))
        })

        val countryTabs = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(58)).apply {
                bottomMargin = dp(8)
            }
        }
        listOf("BR" to "BRASIL", "PT" to "PORTUGAL", "FR" to "FRANÇA").forEach { (code, label) ->
            val button = countryButton(code, label)
            countryButtons[code] = button
            countryTabs.addView(button)
        }
        shell.addView(countryTabs)

        categoryScroll = HorizontalScrollView(this).apply {
            isHorizontalScrollBarEnabled = false
            layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(56)).apply {
                bottomMargin = dp(10)
            }
        }
        val categoryRow = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
        }
        brSections.forEach { (section, label) ->
            val button = categoryButton(section, label)
            categoryButtons[section] = button
            categoryRow.addView(button)
        }
        categoryScroll.addView(categoryRow)
        shell.addView(categoryScroll)

        val body = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        val channelScroll = ScrollView(this).apply {
            layoutParams = LinearLayout.LayoutParams(dp(390), ViewGroup.LayoutParams.MATCH_PARENT).apply {
                marginEnd = dp(20)
            }
            background = rounded(Color.rgb(16, 20, 29), dp(16).toFloat())
        }
        channelList = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(12), dp(12), dp(12), dp(12))
        }
        channelScroll.addView(channelList)

        val playerHost = FrameLayout(this).apply {
            layoutParams = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.MATCH_PARENT, 1f)
            background = rounded(Color.BLACK, dp(16).toFloat())
        }
        playerView = buildPlayerView().apply {
            layoutParams = FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.MATCH_PARENT,
            )
        }
        playerHost.addView(playerView)

        body.addView(channelScroll)
        body.addView(playerHost)
        shell.addView(body, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f))

        statusText = TextView(this).apply {
            text = "Carregando canais…"
            textSize = 15f
            setTextColor(Color.rgb(174, 182, 199))
            setPadding(dp(4), dp(8), 0, 0)
        }
        shell.addView(statusText)

        root.addView(
            shell,
            FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT),
        )
        fullscreenHost = FrameLayout(this).apply {
            visibility = View.GONE
            setBackgroundColor(Color.BLACK)
        }
        root.addView(
            fullscreenHost,
            FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT),
        )
        return root
    }

    private fun countryButton(code: String, label: String): TextView = TextView(this).apply {
        text = label
        textSize = 18f
        gravity = Gravity.CENTER
        setTextColor(Color.WHITE)
        isFocusable = true
        isFocusableInTouchMode = false
        layoutParams = LinearLayout.LayoutParams(0, dp(52), 1f).apply { marginEnd = dp(12) }
        background = rounded(Color.rgb(28, 34, 46), dp(12).toFloat())
        setOnClickListener { loadCountry(code) }
        setOnFocusChangeListener { view, focused ->
            view.background = rounded(
                when {
                    focused -> Color.rgb(84, 99, 129)
                    currentCountry == code -> Color.rgb(53, 66, 91)
                    else -> Color.rgb(28, 34, 46)
                },
                dp(12).toFloat(),
            )
        }
    }

    private fun categoryButton(section: String, label: String): TextView = TextView(this).apply {
        text = label
        textSize = 14f
        gravity = Gravity.CENTER
        setTextColor(Color.WHITE)
        isFocusable = true
        isFocusableInTouchMode = false
        setPadding(dp(18), 0, dp(18), 0)
        layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, dp(46)).apply {
            marginEnd = dp(8)
        }
        background = rounded(Color.rgb(24, 29, 39), dp(10).toFloat())
        setOnClickListener {
            if (currentCountry == "BR") loadSection(section)
        }
        setOnFocusChangeListener { view, focused ->
            view.background = rounded(
                when {
                    focused -> Color.rgb(84, 99, 129)
                    currentCountry == "BR" && currentSection == section -> Color.rgb(53, 66, 91)
                    else -> Color.rgb(24, 29, 39)
                },
                dp(10).toFloat(),
            )
        }
    }

    private fun loadCountry(code: String) {
        currentCountry = code
        currentSection = ""
        categoryScroll.visibility = if (code == "BR") View.VISIBLE else View.GONE
        refreshCountryButtons()
        refreshCategoryButtons()
        loadChannels()
    }

    private fun loadSection(section: String) {
        if (currentCountry != "BR") return
        currentSection = section
        refreshCategoryButtons()
        loadChannels()
    }

    private fun loadChannels() {
        currentIndex = -1
        channels = emptyList()
        player.stop()
        channelList.removeAllViews()
        val scope = if (currentCountry == "BR" && currentSection.isNotBlank()) {
            "${countryName(currentCountry)} · $currentSection"
        } else {
            countryName(currentCountry)
        }
        channelList.addView(messageRow("Carregando $scope…"))
        statusText.text = "Buscando canais de $scope…"
        val countrySnapshot = currentCountry
        val sectionSnapshot = currentSection

        Thread {
            runCatching {
                api.channels(
                    limit = 500,
                    country = countrySnapshot,
                    section = sectionSnapshot.takeIf { countrySnapshot == "BR" && it.isNotBlank() },
                )
            }.onSuccess { result ->
                runOnUiThread {
                    if (countrySnapshot == currentCountry && sectionSnapshot == currentSection) {
                        renderChannels(result)
                    }
                }
            }.onFailure { error ->
                runOnUiThread {
                    if (countrySnapshot != currentCountry || sectionSnapshot != currentSection) return@runOnUiThread
                    channelList.removeAllViews()
                    channelList.addView(messageRow("Não foi possível carregar os canais."))
                    statusText.text = error.message ?: "Falha ao carregar canais"
                }
            }
        }.start()
    }

    private fun renderChannels(result: List<Channel>) {
        channels = result
        channelList.removeAllViews()
        val label = if (currentCountry == "BR" && currentSection.isNotBlank()) {
            "${countryName(currentCountry)} · $currentSection"
        } else {
            countryName(currentCountry)
        }
        statusText.text = "${result.size} canais disponíveis em $label · OK no player = tela cheia"
        if (result.isEmpty()) {
            channelList.addView(messageRow("Nenhum canal saudável publicado nesta seção."))
            return
        }

        result.forEachIndexed { index, channel ->
            channelList.addView(channelAction(channel.name) {
                currentIndex = index
                playChannel(channel, requestFocus = true)
            })
        }
        currentIndex = 0
        playChannel(result[0], requestFocus = false)
        channelList.getChildAt(0)?.requestFocus()
    }

    private fun playChannel(channel: Channel, requestFocus: Boolean) {
        statusText.text = "Analisando fontes para ${channel.name}…"
        Thread {
            runCatching { api.resolvePlayback("live", channel.id) }
                .onSuccess { resolution ->
                    runOnUiThread {
                        val item = MediaItem.Builder()
                            .setUri(resolution.url)
                            .apply { resolution.mimeType?.let { setMimeType(it) } }
                            .setMediaId("live:${channel.id}")
                            .build()
                        player.setMediaItem(item)
                        player.prepare()
                        player.playWhenReady = true
                        val quality = listOfNotNull(
                            resolution.videoCodec?.uppercase(),
                            resolution.height?.let { "${it}p" },
                            resolution.audioCodec?.uppercase(),
                        ).joinToString(" · ")
                        statusText.text = if (quality.isBlank()) channel.name else "${channel.name} · $quality"
                        if (requestFocus) playerView.requestFocus()
                    }
                }
                .onFailure { error ->
                    runOnUiThread {
                        statusText.text = "Não foi possível reproduzir ${channel.name} · ${error.message ?: error.javaClass.simpleName}"
                    }
                }
        }.start()
    }

    private fun buildPlayerView(): PlayerView = PlayerView(this).apply {
        player = this@LiveCountryActivity.player
        useController = true
        controllerAutoShow = false
        controllerShowTimeoutMs = 2500
        resizeMode = AspectRatioFrameLayout.RESIZE_MODE_FIT
        setShowBuffering(PlayerView.SHOW_BUFFERING_NEVER)
        background = rounded(Color.BLACK, dp(14).toFloat())
        isFocusable = true
        isFocusableInTouchMode = false
        setOnClickListener { if (!playerFullscreen) enterPlayerFullscreen(this) }
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
            parent.addView(view, playerOriginalIndex.coerceIn(0, parent.childCount), params)
            view.requestFocus()
        }
        playerOriginalParent = null
        playerOriginalLayoutParams = null
        playerOriginalIndex = -1
    }

    override fun dispatchKeyEvent(event: KeyEvent): Boolean {
        if (event.action == KeyEvent.ACTION_DOWN && channels.isNotEmpty()) {
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
        if (channels.isEmpty()) return
        currentIndex = if (currentIndex !in channels.indices) 0 else {
            (currentIndex + delta + channels.size) % channels.size
        }
        playChannel(channels[currentIndex], requestFocus = false)
    }

    private fun refreshCountryButtons() {
        countryButtons.forEach { (code, button) ->
            button.background = rounded(
                if (code == currentCountry) Color.rgb(53, 66, 91) else Color.rgb(28, 34, 46),
                dp(12).toFloat(),
            )
        }
    }

    private fun refreshCategoryButtons() {
        categoryButtons.forEach { (section, button) ->
            button.background = rounded(
                if (currentCountry == "BR" && section == currentSection) Color.rgb(53, 66, 91) else Color.rgb(24, 29, 39),
                dp(10).toFloat(),
            )
        }
    }

    private fun countryName(code: String): String = when (code) {
        "BR" -> "Brasil"
        "PT" -> "Portugal"
        "FR" -> "França"
        else -> code
    }

    private fun channelAction(label: String, click: () -> Unit): TextView = TextView(this).apply {
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
            view.background = rounded(
                if (focused) Color.rgb(70, 83, 108) else Color.rgb(28, 34, 46),
                dp(11).toFloat(),
            )
        }
    }

    private fun messageRow(value: String): TextView = TextView(this).apply {
        text = value
        textSize = 16f
        setTextColor(Color.rgb(185, 193, 209))
        setPadding(dp(16), dp(20), dp(16), dp(20))
    }

    private fun returnToMain() {
        startActivity(Intent(this, MainActivity::class.java).apply {
            putExtra("server_url", serverUrl)
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK
        })
        finish()
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
