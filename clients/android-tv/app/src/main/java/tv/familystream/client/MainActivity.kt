package tv.familystream.client

import android.graphics.Color
import android.graphics.drawable.GradientDrawable
import android.os.Bundle
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.widget.LinearLayout
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.media3.common.MediaItem
import androidx.media3.common.util.UnstableApi
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.ui.AspectRatioFrameLayout
import androidx.media3.ui.PlayerView
import java.net.HttpURLConnection
import java.net.URL

@UnstableApi
class MainActivity : AppCompatActivity() {
    private lateinit var player: ExoPlayer
    private lateinit var playerView: PlayerView
    private lateinit var sideBar: LinearLayout
    private lateinit var sectionTitle: TextView
    private lateinit var statusText: TextView

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

        player = ExoPlayer.Builder(this).build().also {
            it.setHandleAudioBecomingNoisy(true)
        }
        setContentView(buildTvUi())
        loadFirstLiveChannel()
    }

    private fun buildTvUi(): View {
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            setBackgroundColor(Color.rgb(11, 13, 18))
            layoutParams = ViewGroup.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.MATCH_PARENT,
            )
        }

        sideBar = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(dp(18), dp(20), dp(18), dp(20))
            background = rounded(Color.rgb(17, 21, 29), dp(18).toFloat())
            layoutParams = LinearLayout.LayoutParams(expandedSidebarWidth, ViewGroup.LayoutParams.MATCH_PARENT)
        }

        val brand = TextView(this).apply {
            text = "FamilyStream"
            textSize = 23f
            setTextColor(Color.WHITE)
            setPadding(dp(14), 0, 0, dp(24))
        }
        sideBar.addView(brand)

        val menuItems = listOf("Ao Vivo", "Destaques", "Filmes", "Séries", "Infantil", "Explorar")
        menuItems.forEachIndexed { index, label ->
            sideBar.addView(menuButton(label, index == 0))
        }

        val content = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(28), dp(24), dp(28), dp(24))
            layoutParams = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.MATCH_PARENT, 1f)
        }

        sectionTitle = TextView(this).apply {
            text = "Ao Vivo"
            textSize = 30f
            setTextColor(Color.WHITE)
            setPadding(0, 0, 0, dp(12))
        }

        playerView = PlayerView(this).apply {
            player = this@MainActivity.player
            useController = true
            controllerAutoShow = true
            resizeMode = AspectRatioFrameLayout.RESIZE_MODE_FIT
            setShowBuffering(PlayerView.SHOW_BUFFERING_WHEN_PLAYING)
            layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f)
            background = rounded(Color.BLACK, dp(14).toFloat())
            isFocusable = true
        }

        statusText = TextView(this).apply {
            text = "Conectando ao FamilyStream…"
            textSize = 17f
            setTextColor(Color.LTGRAY)
            setPadding(0, dp(12), 0, 0)
        }

        content.addView(sectionTitle)
        content.addView(playerView)
        content.addView(statusText)

        root.addView(sideBar)
        root.addView(content)
        return root
    }

    private fun menuButton(label: String, first: Boolean): TextView {
        return TextView(this).apply {
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
            background = rounded(if (first) Color.rgb(45, 52, 67) else Color.TRANSPARENT, dp(12).toFloat())

            setOnFocusChangeListener { view, hasFocus ->
                val item = view as TextView
                item.background = rounded(
                    if (hasFocus) Color.rgb(65, 73, 92) else Color.TRANSPARENT,
                    dp(12).toFloat(),
                )
                animateSidebar(hasFocus)
            }
            setOnClickListener {
                sectionTitle.text = label
                when (label) {
                    "Ao Vivo" -> loadFirstLiveChannel()
                    else -> statusText.text = "$label: catálogo em integração com a API FamilyStream v0.3"
                }
            }
        }
    }

    private fun animateSidebar(expanded: Boolean) {
        val params = sideBar.layoutParams
        params.width = if (expanded) expandedSidebarWidth else collapsedSidebarWidth
        sideBar.layoutParams = params
    }

    private fun loadFirstLiveChannel() {
        statusText.text = "Carregando primeiro canal disponível…"
        Thread {
            try {
                val playlistUrl = "$serverUrl/family-tv.m3u"
                val connection = (URL(playlistUrl).openConnection() as HttpURLConnection).apply {
                    connectTimeout = 7000
                    readTimeout = 7000
                    requestMethod = "GET"
                    setRequestProperty("Accept", "application/vnd.apple.mpegurl,text/plain,*/*")
                }
                val code = connection.responseCode
                if (code !in 200..299) error("HTTP $code")
                val text = connection.inputStream.bufferedReader().use { it.readText() }
                connection.disconnect()
                val playable = text.lineSequence()
                    .map { it.trim() }
                    .firstOrNull { it.startsWith("http://") || it.startsWith("https://") }
                    ?: error("playlist sem canais publicados")

                runOnUiThread {
                    player.setMediaItem(MediaItem.fromUri(playable))
                    player.prepare()
                    player.playWhenReady = true
                    statusText.text = "Ao Vivo · resolver adaptativo · $serverUrl"
                    playerView.requestFocus()
                }
            } catch (exc: Exception) {
                runOnUiThread {
                    statusText.text = "Servidor indisponível: ${exc.message ?: exc.javaClass.simpleName}"
                }
            }
        }.start()
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
