package tv.familystream.client

import android.content.Intent
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.os.Build
import android.os.Bundle
import android.text.InputType
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.widget.Button
import android.widget.EditText
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity

class LoginActivity : AppCompatActivity() {
    private lateinit var usernameInput: EditText
    private lateinit var passwordInput: EditText
    private lateinit var loginButton: Button
    private lateinit var statusText: TextView
    private lateinit var sessionStore: SessionStore
    private var submitting = false

    private val serverPreferences by lazy { getSharedPreferences("galodoidotv", MODE_PRIVATE) }
    private val serverUrl: String by lazy {
        intent.getStringExtra("server_url")
            ?.trimEnd('/')
            ?.takeIf { it.startsWith("http://") || it.startsWith("https://") }
            ?: serverPreferences.getString("server_url", null)
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

        sessionStore = SessionStore(this)
        setContentView(buildLoginScreen())
        usernameInput.setText(sessionStore.username().orEmpty())
        if (usernameInput.text.isNullOrBlank()) usernameInput.requestFocus() else passwordInput.requestFocus()
    }

    private fun buildLoginScreen(): View {
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER
            setPadding(dp(70), dp(48), dp(70), dp(48))
            setBackgroundColor(Color.rgb(7, 9, 14))
            layoutParams = ViewGroup.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT)
        }

        val branding = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER
            layoutParams = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.MATCH_PARENT, 1.15f).apply {
                marginEnd = dp(54)
            }
        }
        branding.addView(
            ImageView(this).apply {
                setImageResource(R.drawable.galodoidotv_logo)
                scaleType = ImageView.ScaleType.CENTER_INSIDE
                contentDescription = "GaloDoidoTV"
            },
            LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(310)),
        )
        branding.addView(TextView(this).apply {
            text = "GaloDoidoTV"
            textSize = 34f
            gravity = Gravity.CENTER
            setTypeface(typeface, Typeface.BOLD)
            setTextColor(Color.WHITE)
        })
        branding.addView(TextView(this).apply {
            text = "Sua TV, em qualquer lugar."
            textSize = 17f
            gravity = Gravity.CENTER
            setTextColor(Color.rgb(170, 180, 200))
            setPadding(0, dp(10), 0, 0)
        })

        val panel = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(dp(42), dp(38), dp(42), dp(38))
            background = rounded(Color.rgb(17, 21, 30), dp(20).toFloat())
            layoutParams = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 0.85f)
        }
        panel.addView(TextView(this).apply {
            text = "Entrar"
            textSize = 29f
            setTypeface(typeface, Typeface.BOLD)
            setTextColor(Color.WHITE)
            setPadding(0, 0, 0, dp(8))
        })
        panel.addView(TextView(this).apply {
            text = "Use o usuário e a senha fornecidos para este aparelho."
            textSize = 16f
            setTextColor(Color.rgb(176, 185, 201))
            setPadding(0, 0, 0, dp(24))
        })

        usernameInput = editText("Usuário", false)
        passwordInput = editText("Senha", true)
        panel.addView(usernameInput)
        panel.addView(passwordInput)

        loginButton = Button(this).apply {
            text = "ENTRAR"
            textSize = 18f
            isAllCaps = false
            isFocusable = true
            setTextColor(Color.WHITE)
            background = rounded(Color.rgb(61, 79, 116), dp(12).toFloat())
            layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(62)).apply {
                topMargin = dp(14)
            }
            setOnClickListener { submitLogin() }
            setOnFocusChangeListener { view, focused ->
                view.background = rounded(
                    if (focused) Color.rgb(88, 111, 158) else Color.rgb(61, 79, 116),
                    dp(12).toFloat(),
                )
            }
        }
        panel.addView(loginButton)

        statusText = TextView(this).apply {
            text = ""
            textSize = 15f
            gravity = Gravity.CENTER
            setTextColor(Color.rgb(224, 151, 151))
            setPadding(0, dp(18), 0, 0)
        }
        panel.addView(statusText)

        root.addView(branding)
        root.addView(panel)
        return root
    }

    private fun editText(hintText: String, password: Boolean): EditText = EditText(this).apply {
        hint = hintText
        textSize = 18f
        setSingleLine(true)
        setTextColor(Color.WHITE)
        setHintTextColor(Color.rgb(138, 148, 167))
        setPadding(dp(18), 0, dp(18), 0)
        background = rounded(Color.rgb(29, 35, 48), dp(11).toFloat())
        inputType = if (password) {
            InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD
        } else {
            InputType.TYPE_CLASS_TEXT
        }
        isFocusable = true
        isFocusableInTouchMode = true
        layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(60)).apply {
            bottomMargin = dp(14)
        }
        setOnFocusChangeListener { view, focused ->
            view.background = rounded(
                if (focused) Color.rgb(46, 57, 78) else Color.rgb(29, 35, 48),
                dp(11).toFloat(),
            )
        }
    }

    private fun submitLogin() {
        if (submitting) return
        val username = usernameInput.text?.toString()?.trim().orEmpty()
        val password = passwordInput.text?.toString().orEmpty()
        if (username.length < 3 || password.length < 8) {
            statusText.text = "Confira o usuário e a senha."
            return
        }

        submitting = true
        loginButton.isEnabled = false
        statusText.setTextColor(Color.rgb(177, 188, 209))
        statusText.text = "Conectando…"
        val deviceName = listOf(Build.MANUFACTURER, Build.MODEL)
            .filter { it.isNotBlank() }
            .joinToString(" ")
            .take(120)

        Thread {
            val result = runCatching {
                AuthApi.login(
                    serverUrl,
                    username,
                    password,
                    sessionStore.deviceId(),
                    deviceName,
                )
            }
            runOnUiThread {
                submitting = false
                loginButton.isEnabled = true
                result.onSuccess { session ->
                    sessionStore.saveToken(session.token, session.username)
                    passwordInput.setText("")
                    startActivity(Intent(this, MainActivity::class.java).apply {
                        putExtra("server_url", serverUrl)
                        flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK
                    })
                    finish()
                }.onFailure { error ->
                    statusText.setTextColor(Color.rgb(224, 151, 151))
                    statusText.text = error.message ?: "Não foi possível entrar."
                    passwordInput.setText("")
                    passwordInput.requestFocus()
                }
            }
        }.start()
    }

    private fun rounded(color: Int, radius: Float) = GradientDrawable().apply {
        setColor(color)
        cornerRadius = radius
    }

    private fun dp(value: Int): Int = (value * resources.displayMetrics.density).toInt()
}
