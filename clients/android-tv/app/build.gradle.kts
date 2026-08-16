plugins {
    id("com.android.application")
}

android {
    namespace = "tv.familystream.client"
    compileSdk = 36

    defaultConfig {
        applicationId = "tv.familystream.client"
        minSdk = 23
        targetSdk = 36
        versionCode = 30002
        versionName = "0.3.0-dev"
        buildConfigField("String", "DEFAULT_SERVER_URL", "\"http://10.0.2.2:8080\"")
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
