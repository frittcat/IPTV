package tv.familystream.client

import android.app.AlertDialog
import android.content.Intent
import android.graphics.Color
import android.os.Bundle
import android.view.Gravity
import android.view.View
import android.widget.FrameLayout
import android.widget.ImageView
import androidx.appcompat.app.AppCompatActivity

class SplashActivity : AppCompatActivity() {
    private lateinit var root: FrameLayout
    private var minimumSplashElapsed = false
    private var updateCheckFinished = false
    private var pendingUpdate: AppUpdate? = null
    private var awaitingInstallPermission = false
    private var downloadStarted = false
    private var updateDialogVisible = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.decorView.systemUiVisibility = (
            View.SYSTEM_UI_FLAG_FULLSCREEN or
                View.SYSTEM_UI_FLAG_HIDE_NAVIGATION or
                View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
            )

        root = FrameLayout(this).apply {
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
        logo.animate().alpha(1f).setDuration(320L).start()

        root.postDelayed({
            minimumSplashElapsed = true
            continueIfReady()
        }, 1900L)

        Thread {
            val result = runCatching { AppUpdateManager.checkForUpdate() }
            runOnUiThread {
                updateCheckFinished = true
                pendingUpdate = result.getOrNull()
                val update = pendingUpdate
                if (update != null) {
                    showUpdatePrompt(update)
                } else {
                    continueIfReady()
                }
            }
        }.start()
    }

    override fun onResume() {
        super.onResume()
        if (!awaitingInstallPermission) return
        awaitingInstallPermission = false
        val update = pendingUpdate ?: return
        if (AppUpdateManager.canInstallPackages(this)) {
            startDownload(update)
        } else {
            showUpdatePrompt(update, permissionNeeded = true)
        }
    }

    private fun continueIfReady() {
        if (!minimumSplashElapsed || !updateCheckFinished || pendingUpdate != null || isFinishing) return
        val next = Intent(this, MainActivity::class.java)
        intent.getStringExtra("server_url")?.let { next.putExtra("server_url", it) }
        startActivity(next)
        finish()
        overridePendingTransition(android.R.anim.fade_in, android.R.anim.fade_out)
    }

    private fun showUpdatePrompt(update: AppUpdate, permissionNeeded: Boolean = false) {
        if (updateDialogVisible || downloadStarted || isFinishing) return
        updateDialogVisible = true
        val message = buildString {
            if (permissionNeeded) {
                append("Para atualizar automaticamente, permita que o GaloDoidoTV instale apps desta fonte.\n\n")
            }
            append("Nova versão ${update.versionName} disponível.")
            update.notes?.let { append("\n\n$it") }
        }
        val builder = AlertDialog.Builder(this)
            .setTitle(if (update.required) "Atualização necessária" else "Atualização disponível")
            .setMessage(message)
            .setCancelable(!update.required)
            .setPositiveButton(if (permissionNeeded) "Permitir e atualizar" else "Atualizar agora") { _, _ ->
                updateDialogVisible = false
                if (!AppUpdateManager.canInstallPackages(this)) {
                    awaitingInstallPermission = true
                    AppUpdateManager.openInstallPermission(this)
                } else {
                    startDownload(update)
                }
            }

        if (!update.required) {
            builder.setNegativeButton("Depois") { _, _ ->
                updateDialogVisible = false
                pendingUpdate = null
                continueIfReady()
            }
        }
        builder.setOnDismissListener { updateDialogVisible = false }
        builder.show()
    }

    private fun startDownload(update: AppUpdate) {
        if (downloadStarted || isFinishing) return
        downloadStarted = true
        val progress = AlertDialog.Builder(this)
            .setTitle("Atualizando GaloDoidoTV")
            .setMessage("Baixando atualização… 0%")
            .setCancelable(false)
            .create()
        progress.show()

        Thread {
            val result = runCatching {
                AppUpdateManager.downloadUpdate(this, update) { percent ->
                    runOnUiThread {
                        if (progress.isShowing) progress.setMessage("Baixando atualização… $percent%")
                    }
                }
            }
            runOnUiThread {
                if (result.isSuccess) {
                    progress.setMessage("Download concluído. Abrindo instalador…")
                    runCatching { AppUpdateManager.launchInstaller(this, result.getOrThrow()) }
                        .onFailure { error ->
                            progress.dismiss()
                            downloadStarted = false
                            showUpdateError(update, error)
                        }
                } else {
                    progress.dismiss()
                    downloadStarted = false
                    showUpdateError(update, result.exceptionOrNull())
                }
            }
        }.start()
    }

    private fun showUpdateError(update: AppUpdate, error: Throwable?) {
        AlertDialog.Builder(this)
            .setTitle("Não foi possível atualizar")
            .setMessage("O download da atualização falhou${error?.message?.let { ": $it" } ?: "."}")
            .setCancelable(!update.required)
            .setPositiveButton("Tentar novamente") { _, _ -> startDownload(update) }
            .apply {
                if (!update.required) {
                    setNegativeButton("Continuar") { _, _ ->
                        pendingUpdate = null
                        continueIfReady()
                    }
                }
            }
            .show()
    }
}
