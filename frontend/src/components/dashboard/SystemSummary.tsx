import type { BackupEntry } from "@/lib/types";
import type { DeviceStatusPayload } from "@/lib/deviceStatus";
import { daysSince } from "@/lib/utils";

interface SystemSummaryProps {
  backups: BackupEntry[];
  deviceStatus: DeviceStatusPayload | null;
  deviceAgeMinutes: number;
  totalPackages: number;
}


function restoreReadiness(backups: BackupEntry[]): number {
  const EXPECTED_CATEGORIES = [
    "packages",
    "system",
    "config",
    "desktop",
    "browser",
    "git",
    "scripts",
    "dotfiles",
    "gh",
  ];

  const lastBackup: Record<string, string> = {};
  for (const b of backups) {
    for (const c of b.categories) {
      if (!lastBackup[c]) lastBackup[c] = b.date;
    }
    if (b.categories.includes("all")) {
      for (const cat of EXPECTED_CATEGORIES) {
        if (!lastBackup[cat]) lastBackup[cat] = b.date;
      }
    }
  }

  let score = 0;
  for (const cat of EXPECTED_CATEGORIES) {
    const date = lastBackup[cat];
    if (!date) continue;
    const days = daysSince(date);
    if (days < 7) score += 1;
    else if (days < 14) score += 0.5;
    else score += 0.2;
  }

  return Math.round((score / EXPECTED_CATEGORIES.length) * 100);
}

export function SystemSummary({
  backups,
  deviceStatus,
  deviceAgeMinutes,
  totalPackages,
}: SystemSummaryProps) {
  const lastBackupDate = backups.length > 0 ? backups[0].date : null;
  const daysSinceBackup = lastBackupDate ? daysSince(lastBackupDate) : null;
  const readiness = restoreReadiness(backups);

  const deviceOnline = deviceStatus !== null && deviceAgeMinutes < 10;

  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mb-4">
      {/* Restore Readiness */}
      <div className="bg-card border border-border rounded-xl px-3 py-2.5 text-center">
        <div
          className="text-xl font-bold tabular-nums"
          style={{
            color:
              readiness >= 80
                ? "var(--green)"
                : readiness >= 50
                  ? "var(--yellow)"
                  : "var(--red)",
          }}
        >
          {readiness}%
        </div>
        <div className="text-[11px] text-dim mt-0.5">Restore Ready</div>
      </div>

      {/* Last Backup */}
      <div className="bg-card border border-border rounded-xl px-3 py-2.5 text-center">
        <div
          className="text-xl font-bold tabular-nums"
          style={{
            color:
              daysSinceBackup === null
                ? "var(--red)"
                : daysSinceBackup === 0
                  ? "var(--green)"
                  : daysSinceBackup < 3
                    ? "var(--green)"
                    : daysSinceBackup < 7
                      ? "var(--yellow)"
                      : "var(--red)",
          }}
        >
          {daysSinceBackup === null
            ? "—"
            : daysSinceBackup === 0
              ? "Today"
              : `${daysSinceBackup}d`}
        </div>
        <div className="text-[11px] text-dim mt-0.5">Last Backup</div>
      </div>

      {/* Device Status */}
      <div className="bg-card border border-border rounded-xl px-3 py-2.5 text-center">
        <div className="flex items-center justify-center gap-1.5">
          <span
            className="w-2.5 h-2.5 rounded-full"
            style={{
              background: deviceOnline ? "var(--green)" : "var(--dim)",
            }}
          />
          <span
            className="text-lg font-bold"
            style={{
              color: deviceOnline ? "var(--green)" : "var(--dim)",
            }}
          >
            {deviceOnline ? "Online" : "Offline"}
          </span>
        </div>
        <div className="text-[11px] text-dim mt-0.5">
          {deviceStatus
            ? `${deviceStatus.battery.capacity}% · ${deviceStatus.cpu.tempC.toFixed(0)}°C`
            : "No signal"}
        </div>
      </div>

      {/* Packages */}
      <div className="bg-card border border-border rounded-xl px-3 py-2.5 text-center">
        <div className="text-xl font-bold tabular-nums text-bright">
          {totalPackages.toLocaleString()}
        </div>
        <div className="text-[11px] text-dim mt-0.5">Packages Tracked</div>
      </div>
    </div>
  );
}
