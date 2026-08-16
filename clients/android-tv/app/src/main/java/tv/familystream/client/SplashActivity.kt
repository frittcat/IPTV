package tv.familystream.client

import android.content.Intent
import android.graphics.Color
import android.os.Bundle
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.widget.FrameLayout
import android.widget.ImageView
import android.widget.TextView
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
            scaleType = ImageView.ScaleType.FIT_CENTER
            contentDescription = "GaloDoidoTV"
        }
        root.addView(
            logo,
            FrameLayout.LayoutParams(dp(430), dp(430), Gravity.CENTER),
        )
        val status = TextView(this).apply {
            text = "GaloDoidoTV"
            textSize = 24f
            gravity = Gravity.CENTER
            setTextColor(Color.rgb(245, 196, 0))
        }
        root.addView(
            status,
            FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(60), Gravity.BOTTOM).apply {
                bottomMargin = dp(38)
            },
        )
        setContentView(root)

        root.postDelayed({
            val next = Intent(this, MainActivity::class.java)
            intent.getStringExtra("server_url")?.let { next.putExtra("server_url", it) }
            startActivity(next)
            finish()
        }, 1200L)
    }

    private fun dp(value: Int): Int = (value * resources.displayMetrics.density).toInt()
}
