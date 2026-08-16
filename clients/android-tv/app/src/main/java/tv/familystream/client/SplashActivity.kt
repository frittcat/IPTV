package tv.familystream.client

import android.content.Intent
import android.graphics.Color
import android.os.Bundle
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.widget.FrameLayout
import android.widget.ImageView
import androidx.appcompat.app.AppCompatActivity

class SplashActivity : AppCompatActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.decorView.systemUiVisibility = (
            View.SYSTEM_UI_FLAG_FULLSCREEN or
                View.SYSTEM_UI_FLAG_HIDE_NAVIGATION or
                View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
            )

        val root = FrameLayout(this).apply {
            setBackgroundColor(Color.rgb(5, 5, 5))
        }

        val logo = ImageView(this).apply {
            setImageResource(R.drawable.galodoidotv_logo)
            scaleType = ImageView.ScaleType.CENTER_INSIDE
            adjustViewBounds = true
            contentDescription = "GaloDoidoTV"
            alpha = 0f
        }
        root.addView(
            logo,
            FrameLayout.LayoutParams(
                (resources.displayMetrics.widthPixels * 0.66f).toInt(),
                (resources.displayMetrics.heightPixels * 0.66f).toInt(),
                Gravity.CENTER,
            ),
        )
        setContentView(root)

        // Make the product mark unmistakable before the home screen appears.
        logo.animate().alpha(1f).setDuration(320L).start()

        root.postDelayed({
            val next = Intent(this, MainActivity::class.java)
            intent.getStringExtra("server_url")?.let { next.putExtra("server_url", it) }
            startActivity(next)
            finish()
            overridePendingTransition(android.R.anim.fade_in, android.R.anim.fade_out)
        }, 1900L)
    }
}
