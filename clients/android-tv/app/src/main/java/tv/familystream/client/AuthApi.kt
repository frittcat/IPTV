package tv.familystream.client

import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

internal data class LoginResult(
    val token: String,
    val username: String,
    val expiresAt: String?,
)

internal enum class SessionValidation {
    VALID,
    INVALID,
    UNAVAILABLE,
}

internal object AuthApi {
    fun login(
        baseUrl: String,
        username: String,
        password: String,
        deviceId: String,
        deviceName: String,
    ): LoginResult {
        val connection = open(baseUrl, "/api/v1/auth/login", "POST").apply {
            setRequestProperty("Content-Type", "application/json; charset=utf-8")
            doOutput = true
        }
        val payload = JSONObject()
            .put("username", username.trim())
            .put("password", password)
            .put("device_id", deviceId)
            .put("device_name", deviceName)
            .toString()
        return try {
            connection.outputStream.use { it.write(payload.toByteArray(Charsets.UTF_8)) }
            val code = connection.responseCode
            val body = responseBody(connection, code)
            if (code !in 200..299) {
                throw IllegalStateException(errorMessage(body, code))
            }
            val root = JSONObject(body)
            LoginResult(
                token = root.getString("token"),
                username = root.optString("username", username.trim()),
                expiresAt = root.optString("expires_at").takeIf { it.isNotBlank() },
            )
        } finally {
            connection.disconnect()
        }
    }

    fun validateSession(baseUrl: String, token: String): SessionValidation {
        val connection = open(baseUrl, "/api/v1/auth/session", "GET").apply {
            setRequestProperty("Authorization", "Bearer $token")
        }
        return try {
            when (connection.responseCode) {
                in 200..299 -> SessionValidation.VALID
                401, 403 -> SessionValidation.INVALID
                else -> SessionValidation.UNAVAILABLE
            }
        } catch (_: Exception) {
            SessionValidation.UNAVAILABLE
        } finally {
            connection.disconnect()
        }
    }

    fun logout(baseUrl: String, token: String) {
        val connection = open(baseUrl, "/api/v1/auth/logout", "POST").apply {
            setRequestProperty("Authorization", "Bearer $token")
            doOutput = true
        }
        try {
            connection.outputStream.use { it.write(ByteArray(0)) }
            connection.responseCode
        } finally {
            connection.disconnect()
        }
    }

    private fun open(baseUrl: String, path: String, method: String): HttpURLConnection {
        return (URL("${baseUrl.trimEnd('/')}$path").openConnection() as HttpURLConnection).apply {
            connectTimeout = 8_000
            readTimeout = 12_000
            requestMethod = method
            instanceFollowRedirects = true
            setRequestProperty("Accept", "application/json")
            setRequestProperty("X-GaloDoidoTV-Device", "android-tv-modern")
        }
    }

    private fun responseBody(connection: HttpURLConnection, code: Int): String {
        val stream = if (code in 200..299) connection.inputStream else connection.errorStream
        return stream?.bufferedReader()?.use { it.readText() }.orEmpty()
    }

    private fun errorMessage(body: String, code: Int): String {
        val detail = runCatching { JSONObject(body).optString("detail") }.getOrNull()
        return when {
            !detail.isNullOrBlank() -> detail
            code == 401 -> "Usuário ou senha inválidos"
            code == 403 -> "Este usuário atingiu o limite de dispositivos"
            else -> "Erro de autenticação HTTP $code"
        }
    }
}
