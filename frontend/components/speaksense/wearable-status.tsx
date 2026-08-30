"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { API_BASE } from "@/lib/api";
import { DEMO_USER_ID } from "@/lib/constants";

type ConnectionStatus = {
  user_id: string;
  device_type: string | null;
  connected: boolean;
  connected_at: string | null;
  last_synced_at: string | null;
};

const STALE_AFTER_MINUTES = 60;

function minutesAgo(iso: string | null): number | null {
  if (!iso) return null;
  return Math.round((Date.now() - new Date(iso).getTime()) / 60000);
}

function formatAgo(iso: string | null): string {
  const mins = minutesAgo(iso);
  if (mins === null) return "never";
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins} min ago`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours} hr ago`;
  return `${Math.round(hours / 24)} day(s) ago`;
}

async function fetchStatus(): Promise<ConnectionStatus | null> {
  try {
    const res = await fetch(`${API_BASE}/api/wearables/user/${DEMO_USER_ID}/status`);
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

/**
 * Connect/disconnect UI for the watch bridge. "Connecting" here can't pair
 * Bluetooth or Health Connect directly from the browser (that has to happen
 * on the phone, via the SpeakSense Watch Bridge app reading Health Connect)
 * -- so this card's job is: show the setup steps, then poll the backend for
 * the first synced reading and flip to "connected" automatically. Disconnect
 * is a real in-app action: it stops heart-rate data from being factored into
 * coaching feedback, with an option to also delete stored readings.
 */
export function WearableStatusCard() {
  const [status, setStatus] = useState<ConnectionStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [showSetup, setShowSetup] = useState(false);
  const [checking, setChecking] = useState(false);
  const [showDisconnectConfirm, setShowDisconnectConfirm] = useState(false);
  const [deleteHistory, setDeleteHistory] = useState(false);
  const [disconnecting, setDisconnecting] = useState(false);

  useEffect(() => {
    fetchStatus().then((s) => {
      setStatus(s);
      setLoading(false);
    });
  }, []);

  async function checkNow() {
    setChecking(true);
    const s = await fetchStatus();
    setStatus(s);
    setChecking(false);
    if (s?.connected) setShowSetup(false);
  }

  async function disconnect() {
    setDisconnecting(true);
    try {
      const res = await fetch(`${API_BASE}/api/wearables/user/${DEMO_USER_ID}/disconnect`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ delete_history: deleteHistory }),
      });
      if (res.ok) {
        setStatus(await res.json());
      }
    } finally {
      setDisconnecting(false);
      setShowDisconnectConfirm(false);
      setDeleteHistory(false);
    }
  }

  const stale =
    status?.connected && minutesAgo(status.last_synced_at) !== null &&
    (minutesAgo(status.last_synced_at) as number) > STALE_AFTER_MINUTES;

  if (loading) {
    return (
      <Card className="p-5">
        <p className="text-sm text-ink/40">Checking watch connection…</p>
      </Card>
    );
  }

  return (
    <Card className="p-5">
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-2.5">
          <span
            className={`h-2.5 w-2.5 rounded-full ${
              status?.connected ? (stale ? "bg-amber-500" : "bg-teal-600") : "bg-ink/20"
            }`}
          />
          <div>
            <p className="text-sm font-medium">
              {status?.connected
                ? stale
                  ? "Watch connected, but hasn't synced recently"
                  : "Watch connected"
                : "Watch not connected"}
            </p>
            {status?.connected && (
              <p className="text-xs text-ink/40">
                {status.device_type ?? "device"} · last synced {formatAgo(status.last_synced_at)}
              </p>
            )}
            {!status?.connected && (
              <p className="text-xs text-ink/40">
                Heart-rate context won't be included in coaching feedback until connected.
              </p>
            )}
          </div>
        </div>

        {status?.connected ? (
          <Button variant="ghost" size="sm" onClick={() => setShowDisconnectConfirm(true)}>
            Disconnect
          </Button>
        ) : (
          <Button size="sm" onClick={() => setShowSetup((v) => !v)}>
            Connect watch
          </Button>
        )}
      </div>

      {showSetup && !status?.connected && (
        <div className="mt-4 rounded-xl border border-line bg-white/60 p-4 text-sm text-ink/70 space-y-3">
          <p className="font-medium text-ink">Connect your NoiseFit (or similar) watch</p>
          <ol className="list-decimal list-inside space-y-1.5 text-ink/70">
            <li>Make sure the NoiseFit app is syncing to <strong>Google Health Connect</strong> on your phone (NoiseFit app → Settings → Health Connect).</li>
            <li>Install the <strong>SpeakSense Watch Bridge</strong> app on your phone (see <code className="text-xs bg-ink/5 px-1 rounded">android-bridge/README.md</code> in the project).</li>
            <li>Open it, tap <strong>Grant permissions</strong>, then <strong>Sync now</strong>.</li>
          </ol>
          <p className="text-xs text-ink/40">
            Once the bridge app posts its first reading, this page will pick it up automatically.
          </p>
          <Button size="sm" variant="secondary" onClick={checkNow} disabled={checking}>
            {checking ? "Checking…" : "I've done this — check connection"}
          </Button>
        </div>
      )}

      {showDisconnectConfirm && (
        <div className="mt-4 rounded-xl border border-line bg-white/60 p-4 text-sm text-ink/70 space-y-3">
          <p>
            Disconnecting stops heart-rate data from being used in future coaching feedback.
          </p>
          <p className="text-xs text-amber-700">
            This only updates SpeakSense — if the bridge app on your phone is still
            auto-syncing, it may reconnect the next time it syncs. Turn off "Auto-sync"
            in the bridge app too if you want syncing to fully stop.
          </p>
          <label className="flex items-center gap-2 text-xs text-ink/60">
            <input
              type="checkbox"
              checked={deleteHistory}
              onChange={(e) => setDeleteHistory(e.target.checked)}
            />
            Also delete all stored heart-rate history
          </label>
          <div className="flex gap-2">
            <Button size="sm" variant="ghost" onClick={disconnect} disabled={disconnecting}>
              {disconnecting ? "Disconnecting…" : "Confirm disconnect"}
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => {
                setShowDisconnectConfirm(false);
                setDeleteHistory(false);
              }}
              disabled={disconnecting}
            >
              Cancel
            </Button>
          </div>
        </div>
      )}
    </Card>
  );
}
