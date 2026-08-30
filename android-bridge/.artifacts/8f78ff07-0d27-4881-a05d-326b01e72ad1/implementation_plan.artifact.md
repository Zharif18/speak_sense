# Implementation Plan: Relocating Android Development Environment to D: Drive

The goal is to free up space on the C: drive (currently 0 GB free) by moving the Android SDK, Gradle home, and AVDs to the D: drive (231 GB free).

## User Review Required

> [!IMPORTANT]
> This process involves moving several gigabytes of data. It may take some time depending on your disk speed.
> **You will need to restart Android Studio after these changes are applied.**

> [!WARNING]
> Moving the Android SDK while Android Studio is running can cause temporary errors in the IDE until it is restarted and pointed to the new location.

## Proposed Changes

### 1. Relocate Gradle Home (`.gradle`)
We will move the Gradle cache and configuration to `D:\Android\.gradle`.
- Create the target directory on D:.
- Use `robocopy` to move the contents.
- Set the `GRADLE_USER_HOME` environment variable to `D:\Android\.gradle`.

### 2. Relocate Android SDK
We will move the SDK to `D:\Android\Sdk`.
- Create the target directory on D:.
- Use `robocopy` to move the contents.
- Set the `ANDROID_HOME` and `ANDROID_SDK_ROOT` environment variables to `D:\Android\Sdk`.

### 3. Relocate Android Virtual Devices (AVDs)
We will move the emulator images to `D:\Android\.android\avd`.
- Set the `ANDROID_AVD_HOME` environment variable to `D:\Android\.android\avd`.

## Verification Plan

### Manual Verification
- Check that `D:\Android` contains the moved folders.
- Verify that C: drive has regained several gigabytes of free space.
- Open Android Studio and verify the SDK path in **Settings > Appearance & Behavior > System Settings > Android SDK**.
- Run a Gradle build to ensure it uses the new Gradle home.
