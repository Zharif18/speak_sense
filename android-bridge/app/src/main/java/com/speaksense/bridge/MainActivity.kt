package com.speaksense.bridge

import android.os.Bundle
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.health.connect.client.HealthConnectClient
import androidx.health.connect.client.PermissionController
import androidx.health.connect.client.permission.HealthPermission
import androidx.health.connect.client.records.HeartRateRecord
import androidx.health.connect.client.records.StepsRecord
import androidx.lifecycle.lifecycleScope
import com.speaksense.bridge.databinding.ActivityMainBinding
import kotlinx.coroutines.launch

class MainActivity : AppCompatActivity() {

    companion object {
        // Must match frontend/lib/constants.ts DEMO_USER_ID until real auth exists.
        const val DEMO_USER_ID = "00000000-0000-0000-0000-000000000001"
        // Swap for your deployed Render backend URL, or your LAN IP for local testing.
        const val DEFAULT_API_BASE = "https://speaksense-backend.onrender.com"
    }

    private lateinit var binding: ActivityMainBinding
    private lateinit var prefs: Prefs

    private val PERMISSIONS = setOf(
        HealthPermission.getReadPermission(HeartRateRecord::class),
        HealthPermission.getReadPermission(StepsRecord::class),
    )

    private val requestPermissions =
        registerForActivityResult(PermissionController.createRequestPermissionResultContract()) { granted ->
            setStatus(
                if (granted.containsAll(PERMISSIONS)) "Permissions granted. Ready to sync."
                else "Permission denied — heart-rate/steps can't be read until granted."
            )
        }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)
        prefs = Prefs(this)

        binding.apiBaseInput.setText(prefs.apiBase)
        binding.userIdInput.setText(prefs.userId)

        val availability = HealthConnectClient.getSdkStatus(this)
        if (availability != HealthConnectClient.SDK_AVAILABLE) {
            setStatus("Health Connect isn't available on this device. Install it from the Play Store first.")
            binding.grantButton.isEnabled = false
            binding.syncButton.isEnabled = false
            return
        }

        binding.grantButton.setOnClickListener {
            requestPermissions.launch(PERMISSIONS)
        }

        binding.syncButton.setOnClickListener {
            prefs.apiBase = binding.apiBaseInput.text.toString()
            prefs.userId = binding.userIdInput.text.toString()
            runSync()
        }

        binding.autoSyncSwitch.setOnCheckedChangeListener { _, isChecked ->
            if (isChecked) {
                SyncWorker.enablePeriodic(this)
                setStatus("Auto-sync enabled (every 15 min).")
            } else {
                SyncWorker.disablePeriodic(this)
                setStatus("Auto-sync disabled.")
            }
        }
    }

    private fun runSync() {
        setStatus("Syncing…")
        binding.syncButton.isEnabled = false
        lifecycleScope.launch {
            val client = HealthConnectClient.getOrCreate(this@MainActivity)
            val granted = client.permissionController.getGrantedPermissions()
            if (!granted.containsAll(PERMISSIONS)) {
                setStatus("Missing permissions — tap 'Grant permissions' first.")
                binding.syncButton.isEnabled = true
                return@launch
            }

            val result = WearableSync.syncOnce(this@MainActivity, prefs.apiBase, prefs.userId)
            val summary = buildString {
                append("Synced: ${result.heartRatePosted} heart-rate, ${result.motionPosted} motion readings.")
                if (result.errors.isNotEmpty()) {
                    append("\n${result.errors.size} issue(s):\n")
                    append(result.errors.take(5).joinToString("\n"))
                }
            }
            setStatus(summary)
            binding.syncButton.isEnabled = true
        }
    }

    private fun setStatus(text: String) {
        binding.statusText.text = text
    }
}
