package tv.familystream.client

import android.content.Context
import android.provider.Settings
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import java.security.KeyStore
import java.util.UUID
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

internal object SessionState {
    @Volatile
    var token: String? = null
}

internal class SessionStore(private val context: Context) {
    private val preferences = context.getSharedPreferences("galodoidotv_auth", Context.MODE_PRIVATE)

    fun deviceId(): String {
        val existing = preferences.getString(KEY_DEVICE_ID, null)?.takeIf { it.isNotBlank() }
        if (existing != null) return existing

        val androidId = runCatching {
            Settings.Secure.getString(context.contentResolver, Settings.Secure.ANDROID_ID)
        }.getOrNull()?.takeIf { it.isNotBlank() }
        val id = androidId?.let { "android-$it" } ?: "device-${UUID.randomUUID()}"
        preferences.edit().putString(KEY_DEVICE_ID, id).apply()
        return id
    }

    fun saveToken(token: String, username: String?) {
        val cipher = Cipher.getInstance(TRANSFORMATION)
        cipher.init(Cipher.ENCRYPT_MODE, secretKey())
        val encrypted = cipher.doFinal(token.toByteArray(Charsets.UTF_8))
        val payload = ByteArray(cipher.iv.size + encrypted.size)
        System.arraycopy(cipher.iv, 0, payload, 0, cipher.iv.size)
        System.arraycopy(encrypted, 0, payload, cipher.iv.size, encrypted.size)
        preferences.edit()
            .putString(KEY_TOKEN, Base64.encodeToString(payload, Base64.NO_WRAP))
            .putString(KEY_USERNAME, username)
            .apply()
        SessionState.token = token
    }

    fun loadToken(): String? {
        val encoded = preferences.getString(KEY_TOKEN, null) ?: return null
        return runCatching {
            val payload = Base64.decode(encoded, Base64.NO_WRAP)
            require(payload.size > IV_SIZE)
            val iv = payload.copyOfRange(0, IV_SIZE)
            val encrypted = payload.copyOfRange(IV_SIZE, payload.size)
            val cipher = Cipher.getInstance(TRANSFORMATION)
            cipher.init(Cipher.DECRYPT_MODE, secretKey(), GCMParameterSpec(128, iv))
            cipher.doFinal(encrypted).toString(Charsets.UTF_8)
        }.getOrElse {
            clearToken()
            null
        }?.also { SessionState.token = it }
    }

    fun username(): String? = preferences.getString(KEY_USERNAME, null)

    fun clearToken() {
        preferences.edit().remove(KEY_TOKEN).remove(KEY_USERNAME).apply()
        SessionState.token = null
    }

    private fun secretKey(): SecretKey {
        val keyStore = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (keyStore.getKey(KEY_ALIAS, null) as? SecretKey)?.let { return it }

        val generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore")
        generator.init(
            KeyGenParameterSpec.Builder(
                KEY_ALIAS,
                KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT,
            )
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setRandomizedEncryptionRequired(true)
                .setKeySize(256)
                .build(),
        )
        return generator.generateKey()
    }

    companion object {
        private const val KEY_ALIAS = "galodoidotv_client_session_v1"
        private const val KEY_TOKEN = "session_token"
        private const val KEY_USERNAME = "session_username"
        private const val KEY_DEVICE_ID = "device_id"
        private const val TRANSFORMATION = "AES/GCM/NoPadding"
        private const val IV_SIZE = 12
    }
}
