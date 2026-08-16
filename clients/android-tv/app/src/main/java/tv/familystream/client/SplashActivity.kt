package tv.familystream.client

import android.content.Intent
import android.graphics.Color
import android.os.Bundle
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
            setBackgroundColor(Color.BLACK)
        }
        root.addView(
            ImageView(this).apply {
                setImageResource(R.drawable.galodoidotv_splash)
                scaleType = ImageView.ScaleType.CENTER_CROP
                contentDescription = "GaloDoidoTV"
            },
            FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.MATCH_PARENT,
            ),
        )
        setContentView(root)

        root.postDelayed({
            val next = Intent(this, MainActivity::class.java)
            intent.getStringExtra("server_url")?.let { next.putExtra("server_url", it) }
            startActivity(next)
            finish()
        }, 1400L)
    }
}
