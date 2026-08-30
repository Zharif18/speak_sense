package com.speaksense.bridge

import android.content.Context
import androidx.health.connect.client.HealthConnectClient
import androidx.health.connect.client.records.HeartRateRecord
import androidx.health.connect.client.records.StepsRecord
import androidx.health.connect.client.request.ReadRecordsRequest
import androidx.health.connect.client.time.TimeRangeFilter
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.time.Instant
import java.time.format.DateTimeFormatter
import java.util.concurrent.TimeUnit

/**
 * Reads heart-rate + steps from Health Connect (as synced by the NoiseFit
 * app) since the last successful sync, and POSTs each one to SpeakSense's
 * /api/wearables/ingest as an untagged (no session_id) reading. The web app
 * links these to a specific session afterwards via /session/{id}/claim --
 * see android-bridge/README.md for the full flow.
 */
object WearableSync {

    private const val DEVICE_TYPE = "noisefit"
    private val ISO = DateTimeFormatter.ISO_INSTANT

    data class Result(val heartRatePosted: Int, val motionPosted: Int, val errors: List<String>)

    suspend fun syncOnce(context: Context, apiBase: String, userId: String): Result =
        withContext(Dispatchers.IO) {
            val prefs = Prefs(context)
            val client = HealthConnectClient.getOrCreate(context)

            val now = Instant.now()
            var since = prefs.lastSyncTime ?: now.minus(7, java.time.temporal.ChronoUnit.DAYS)
            var range = TimeRangeFilter.between(since, now)
            val errors = mutableListOf<String>()

            // --- Heart rate ---
            var hrPosted = 0
            try {
                var hrRecords = client.readRecords(
                    ReadRecordsRequest(HeartRateRecord::class, timeRangeFilter = range)
                ).records

                // If no records in incremental window, fallback to past 7 days
                if (hrRecords.isEmpty() && prefs.lastSyncTime != null) {
                    since = now.minus(7, java.time.temporal.ChronoUnit.DAYS)
                    range = TimeRangeFilter.between(since, now)
                    hrRecords = client.readRecords(
                        ReadRecordsRequest(HeartRateRecord::class, timeRangeFilter = range)
                    ).records
                }

                for (record in hrRecords) {
                    for (sample in record.samples) {
                        val (ok, err) = postReading(
                            apiBase, userId,
                            metricType = "heart_rate",
                            value = sample.beatsPerMinute.toDouble(),
                            unit = "bpm",
                            recordedAt = sample.time,
                        )
                        if (ok) hrPosted++ else errors.add("HR sample @${sample.time}: $err")
                    }
                }
            } catch (e: Exception) {
                errors.add("Heart rate read failed: ${e.message}")
            }

            // --- Steps, bucketed per-minute as a rough motion-index proxy ---
            var motionPosted = 0
            try {
                val stepRecords = client.readRecords(
                    ReadRecordsRequest(StepsRecord::class, timeRangeFilter = range)
                ).records
                val perMinute = LinkedHashMap<Long, Long>() // epoch-minute -> step count
                for (record in stepRecords) {
                    val minuteBucket = record.startTime.epochSecond / 60
                    perMinute[minuteBucket] = (perMinute[minuteBucket] ?: 0L) + record.count
                }
                for ((minuteBucket, steps) in perMinute) {
                    val recordedAt = Instant.ofEpochSecond(minuteBucket * 60)
                    val (ok, err) = postReading(
                        apiBase, userId,
                        metricType = "motion_index",
                        value = steps.toDouble(),
                        unit = "steps_per_min",
                        recordedAt = recordedAt,
                    )
                    if (ok) motionPosted++ else errors.add("Motion @$recordedAt: $err")
                }
            } catch (e: Exception) {
                errors.add("Steps read failed: ${e.message}")
            }

            if (hrPosted > 0 || motionPosted > 0) {
                prefs.lastSyncTime = now
            }
            Result(hrPosted, motionPosted, errors)
        }

    private fun postReading(
        apiBase: String,
        userId: String,
        metricType: String,
        value: Double,
        unit: String,
        recordedAt: Instant,
    ): Pair<Boolean, String?> {
        return try {
            val cleanBase = if (!apiBase.startsWith("http://") && !apiBase.startsWith("https://")) "http://$apiBase" else apiBase
            val url = URL("${cleanBase.trimEnd('/')}/api/wearables/ingest")
            val conn = (url.openConnection() as HttpURLConnection).apply {
                requestMethod = "POST"
                doOutput = true
                connectTimeout = 10_000
                readTimeout = 10_000
                setRequestProperty("Content-Type", "application/json")
            }
            val body = JSONObject().apply {
                put("user_id", userId)
                put("device_type", DEVICE_TYPE)
                put("metric_type", metricType)
                put("value", value)
                put("unit", unit)
                put("recorded_at", ISO.format(recordedAt))
            }
            conn.outputStream.use { it.write(body.toString().toByteArray()) }
            val code = conn.responseCode
            val isSuccess = code in 200..299
            val errMsg = if (!isSuccess) "HTTP $code: ${conn.responseMessage}" else null
            conn.disconnect()
            Pair(isSuccess, errMsg)
        } catch (e: Exception) {
            Pair(false, e.javaClass.simpleName + ": " + (e.message ?: "network error"))
        }
    }
}

/** Tiny SharedPreferences wrapper for the last-sync watermark + user config. */
class Prefs(context: Context) {
    private val sp = context.getSharedPreferences("speaksense_bridge", Context.MODE_PRIVATE)

    var apiBase: String
        get() = sp.getString("api_base", MainActivity.DEFAULT_API_BASE) ?: MainActivity.DEFAULT_API_BASE
        set(value) = sp.edit().putString("api_base", value).apply()

    var userId: String
        get() = sp.getString("user_id", MainActivity.DEMO_USER_ID) ?: MainActivity.DEMO_USER_ID
        set(value) = sp.edit().putString("user_id", value).apply()

    var lastSyncTime: Instant?
        get() = sp.getLong("last_sync_epoch", -1).takeIf { it > 0 }?.let(Instant::ofEpochSecond)
        set(value) = sp.edit().putLong("last_sync_epoch", value?.epochSecond ?: -1).apply()
}
