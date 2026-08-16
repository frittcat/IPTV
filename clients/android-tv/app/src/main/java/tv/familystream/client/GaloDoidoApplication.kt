package tv.familystream.client

import android.app.Activity
import android.app.Application
import android.os.Bundle
import android.text.TextUtils
import android.view.View
import android.view.ViewGroup
import android.view.ViewTreeObserver
import android.widget.TextView
import androidx.media3.common.util.UnstableApi
import androidx.media3.ui.PlayerView

@UnstableApi
class GaloDoidoApplication : Application(), Application.ActivityLifecycleCallbacks {
    private val menuLabels = setOf("Ao Vivo", "Destaques", "Filmes", "Séries", "Infantil", "Explorar")

    override fun onCreate() {
        super.onCreate()
        registerActivityLifecycleCallbacks(this)
    }

    override fun onActivityCreated(activity: Activity, savedInstanceState: Bundle?) {
        activity.title = "GaloDoidoTV"
        val root = activity.window.decorView
        root.viewTreeObserver.addOnGlobalLayoutListener(object : ViewTreeObserver.OnGlobalLayoutListener {
            override fun onGlobalLayout() {
                polishUi(root)
            }
        })
    }

    private fun polishUi(view: View) {
        if (view is PlayerView) {
            // Dedicated-TV behavior: buffering remains internal and the stock
            // ExoPlayer timeline/controller does not pop up during normal Live TV.
            // The remote can still summon controls explicitly when needed.
            view.setShowBuffering(PlayerView.SHOW_BUFFERING_NEVER)
            view.controllerAutoShow = false
            view.controllerShowTimeoutMs = 2500
            if (view.player?.isPlaying == true) view.hideController()
        }

        if (view is TextView) {
            val current = view.text?.toString().orEmpty()
            if (current.contains("FamilyStream", ignoreCase = false)) {
                view.text = current.replace("FamilyStream", "GaloDoidoTV")
            }
            if (view.contentDescription?.toString()?.contains("FamilyStream") == true) {
                view.contentDescription = view.contentDescription.toString().replace("FamilyStream", "GaloDoidoTV")
            }

            val polished = view.text?.toString().orEmpty()
            if (polished == "GaloDoidoTV") {
                view.isSingleLine = true
                view.maxLines = 1
                view.ellipsize = TextUtils.TruncateAt.END
                view.textSize = 18f
            } else if (polished in menuLabels) {
                view.isSingleLine = true
                view.maxLines = 1
                view.ellipsize = TextUtils.TruncateAt.END
            }
        }

        if (view is ViewGroup) {
            for (index in 0 until view.childCount) polishUi(view.getChildAt(index))
        }
    }

    override fun onActivityStarted(activity: Activity) = Unit
    override fun onActivityResumed(activity: Activity) = polishUi(activity.window.decorView)
    override fun onActivityPaused(activity: Activity) = Unit
    override fun onActivityStopped(activity: Activity) = Unit
    override fun onActivitySaveInstanceState(activity: Activity, outState: Bundle) = Unit
    override fun onActivityDestroyed(activity: Activity) = Unit
}
