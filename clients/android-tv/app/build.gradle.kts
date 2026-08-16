plugins {
    id("com.android.application")
}

val releaseKeystorePath = System.getenv("GALODOIDOTV_KEYSTORE_PATH")
val releaseStorePassword = System.getenv("GALODOIDOTV_KEYSTORE_PASSWORD")
val releaseKeyAlias = System.getenv("GALODOIDOTV_KEY_ALIAS")
val releaseKeyPassword = System.getenv("GALODOIDOTV_KEY_PASSWORD")
val hasReleaseSigning = listOf(
    releaseKeystorePath,
    releaseStorePassword,
    releaseKeyAlias,
    releaseKeyPassword,
).all { !it.isNullOrBlank() }

android {
    namespace = "tv.familystream.client"
    compileSdk = 36

    defaultConfig {
        applicationId = "tv.familystream.client"
        minSdk = 23
        targetSdk = 36
        versionCode = 30009
        versionName = "0.3.0-dev.5"
        buildConfigField("String", "DEFAULT_SERVER_URL", "\"http://10.0.2.2:8080\"")
        buildConfigField(
            "String",
            "UPDATE_MANIFEST_URL",
            "\"https://github.com/frittcat/IPTV/releases/download/android-tv-dev/GaloDoidoTV-AndroidTV-update.json\"",
        )
    }

    if (hasReleaseSigning) {
        signingConfigs {
            create("release") {
                storeFile = file(releaseKeystorePath!!)
                storePassword = releaseStorePassword
                keyAlias = releaseKeyAlias
                keyPassword = releaseKeyPassword
            }
        }
    }

    buildTypes {
        getByName("release") {
            isMinifyEnabled = false
            if (hasReleaseSigning) {
                signingConfig = signingConfigs.getByName("release")
            }
        }
    }

    buildFeatures {
        buildConfig = true
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}

dependencies {
    implementation("androidx.core:core-ktx:1.17.0")
    implementation("androidx.appcompat:appcompat:1.7.1")
    implementation("androidx.activity:activity-ktx:1.12.4")
    implementation("androidx.media3:media3-exoplayer:1.10.1")
    implementation("androidx.media3:media3-exoplayer-hls:1.10.1")
    implementation("androidx.media3:media3-ui:1.10.1")
}
