package tv.familystream.client

import android.app.Activity
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.provider.Settings
import androidx.core.content.FileProvider
import org.json.JSONObject
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import java.security.MessageDigest

internal data class AppUpdate(
    val versionCode: Int,
    val versionName: String,
    val required: Boolean,
    val apkUrl: String,
    val sha256: String,
    val notes: String?,
)

internal object AppUpdateManager {
    private const val APK_MIME = "application/vnd.android.package-archive"
    private const val MAX_REDIRECTS = 6

    fun checkForUpdate(): AppUpdate? {
        val payload = readText(BuildConfig.UPDATE_MANIFEST_URL)
        val root = JSONObject(payload)
        val versionCode = root.getInt("version_code")
        if (versionCode <= BuildConfig.VERSION_CODE) return null

        val apkUrl = root.getString("apk_url")
        require(apkUrl.startsWith("https://")) { "Update APK must use HTTPS" }
        val sha256 = root.getString("sha256").lowercase()
        require(sha256.matches(Regex("[0-9a-f]{64}"))) { "Invalid update SHA-256" }

        return AppUpdate(
            versionCode = versionCode,
            versionName = root.optString("version_name", versionCode.toString()),
            required = root.optBoolean("required", true),
            apkUrl = apkUrl,
            sha256 = sha256,
            notes = root.optString("notes").takeIf { it.isNotBlank() },
        )
    }

    fun canInstallPackages(activity: Activity): Boolean =
        Build.VERSION.SDK_INT < Build.VERSION_CODES.O || activity.packageManager.canRequestPackageInstalls()

    fun openInstallPermission(activity: Activity) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        activity.startActivity(
            Intent(
                Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
                Uri.parse("package:${activity.packageName}"),
            ),
        )
    }

    fun downloadUpdate(
        activity: Activity,
        update: AppUpdate,
        onProgress: (Int) -> Unit,
    ): File {
        val directory = File(activity.cacheDir, "updates").apply { mkdirs() }
        val target = File(directory, "GaloDoidoTV-update.apk")
        val connection = openHttps(update.apkUrl)
        try {
            val total = connection.contentLengthLong
            var downloaded = 0L
            connection.inputStream.use { input ->
                target.outputStream().buffered().use { output ->
                    val buffer = ByteArray(DEFAULT_BUFFER_SIZE)
                    while (true) {
                        val count = input.read(buffer)
                        if (count < 0) break
                        output.write(buffer, 0, count)
                        downloaded += count
                        if (total > 0L) {
                            onProgress(((downloaded * 100L) / total).toInt().coerceIn(0, 100))
                        }
                    }
                }
            }
        } finally {
            connection.disconnect()
        }

        val actual = sha256(target)
        check(actual.equals(update.sha256, ignoreCase = true)) {
            target.delete()
            "Update checksum mismatch"
        }
        return target
    }

    fun launchInstaller(activity: Activity, apk: File) {
        val uri = FileProvider.getUriForFile(
            activity,
            "${BuildConfig.APPLICATION_ID}.fileprovider",
            apk,
        )
        val intent = Intent(Intent.ACTION_INSTALL_PACKAGE).apply {
            data = uri
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
            putExtra(Intent.EXTRA_NOT_UNKNOWN_SOURCE, true)
        }
        activity.startActivity(intent)
    }

    private fun readText(url: String): String {
        require(url.startsWith("https://")) { "Update manifest must use HTTPS" }
        val connection = openHttps(url)
        return try {
            connection.inputStream.bufferedReader().use { it.readText() }
        } finally {
            connection.disconnect()
        }
    }

    private fun openHttps(initialUrl: String): HttpURLConnection {
        var current = initialUrl
        repeat(MAX_REDIRECTS + 1) { redirectCount ->
            val connection = (URL(current).openConnection() as HttpURLConnection).apply {
                connectTimeout = 8_000
                readTimeout = 20_000
                requestMethod = "GET"
                instanceFollowRedirects = false
                setRequestProperty("User-Agent", "GaloDoidoTV/${BuildConfig.VERSION_NAME}")
                setRequestProperty("Accept", "*/*")
            }
            val code = connection.responseCode
            if (code in 200..299) return connection
            if (code in setOf(301, 302, 303, 307, 308) && redirectCount < MAX_REDIRECTS) {
                val location = connection.getHeaderField("Location")
                    ?: error("Update redirect without Location")
                connection.disconnect()
                val resolved = URL(URL(current), location).toString()
                require(resolved.startsWith("https://")) { "Refusing non-HTTPS update redirect" }
                current = resolved
            } else {
                connection.disconnect()
                error("Update HTTP $code")
            }
        }
        error("Too many update redirects")
    }

    private fun sha256(file: File): String {
        val digest = MessageDigest.getInstance("SHA-256")
        file.inputStream().use { input ->
            val buffer = ByteArray(DEFAULT_BUFFER_SIZE)
            while (true) {
                val count = input.read(buffer)
                if (count < 0) break
                digest.update(buffer, 0, count)
            }
        }
        return digest.digest().joinToString("") { "%02x".format(it) }
    }
}
