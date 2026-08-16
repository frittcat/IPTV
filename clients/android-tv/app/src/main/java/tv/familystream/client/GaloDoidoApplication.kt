package tv.familystream.client

import android.app.Activity
import android.app.Application
import android.os.Bundle
import android.view.View
import android.view.ViewGroup
import android.view.ViewTreeObserver
import android.widget.TextView
import androidx.media3.common.util.UnstableApi
import androidx.media3.ui.PlayerView

@UnstableApi
class GaloDoidoApplication : Application(), Application.ActivityLifecycleCallbacks {
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
            // Keep buffering internal, like the reference Android TV player:
            // no visible loading spinner and no controller popping up just
            // because the stream briefly re-buffers.
            view.setShowBuffering(PlayerView.SHOW_BUFFERING_NEVER)
            view.controllerAutoShow = false
            view.controllerShowTimeoutMs = 2500
        }

        if (view is TextView) {
            val current = view.text?.toString().orEmpty()
            if (current.contains("FamilyStream", ignoreCase = false)) {
                view.text = current.replace("FamilyStream", "GaloDoidoTV")
            }
            if (view.contentDescription?.toString()?.contains("FamilyStream") == true) {
                view.contentDescription = view.contentDescription.toString().replace("FamilyStream", "GaloDoidoTV")
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
