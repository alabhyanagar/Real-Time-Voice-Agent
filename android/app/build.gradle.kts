plugins {
    id("com.android.application")
    kotlin("android")
    kotlin("plugin.serialization")
}

android { namespace = "com.voiceagent.android"; compileSdk = 35
    buildFeatures { buildConfig = true }
    defaultConfig {
        applicationId = "com.voiceagent.android"; minSdk = 26; targetSdk = 35; versionCode = 1; versionName = "0.1.0"
        buildConfigField("String", "VOICE_AGENT_WS_URL", "\"ws://10.0.2.2:8000/api/v1/ws/audio\"")
    }
}

dependencies {
    implementation(platform("androidx.compose:compose-bom:2024.12.01"))
    implementation("androidx.activity:activity-compose:1.10.0")
    implementation("androidx.core:core-ktx:1.15.0")
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.8.7")
    implementation("androidx.lifecycle:lifecycle-runtime-compose:2.8.7")
    implementation("androidx.datastore:datastore-preferences:1.1.1")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.9.0")
    implementation("org.jetbrains.kotlinx:kotlinx-serialization-json:1.7.3")
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
}
