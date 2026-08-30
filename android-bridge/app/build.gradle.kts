plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.speaksense.bridge"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.speaksense.bridge"
        minSdk = 28   // Health Connect requires API 28+ (via the standalone HC app) / 34 for the built-in version
        targetSdk = 34
        versionCode = 1
        versionName = "1.0"
    }

    buildTypes {
        release {
            isMinifyEnabled = false
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }
    buildFeatures {
        viewBinding = true
    }
}

dependencies {
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.appcompat:appcompat:1.7.0")
    implementation("com.google.android.material:material:1.12.0")

    // Health Connect client — reads NoiseFit's synced data.
    implementation("androidx.health.connect:connect-client:1.1.0-alpha07")

    // Background periodic sync.
    implementation("androidx.work:work-runtime-ktx:2.9.1")

    // Coroutines, for the async Health Connect + network calls.
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.8.1")
}
