import type { BackupEntry } from "@/lib/types";
import type { DeviceStatusPayload } from "@/lib/deviceStatus";
import { daysSince, getLastBackupByCategory } from "@/lib/utils";
import { COVERAGE_ITEMS } from "@/lib/backup-config";

interface SystemSummaryProps {
  backups: BackupEntry[];
  deviceStatus: DeviceStatusPayload | null;
  deviceAgeMinutes: number;
  totalPackages: number;
}


function restoreReadiness(backups: BackupEntry[]): number {
  const EXPECTED_CATEGORIES = COVERAGE_ITEMS.map((i) => i.backupCategory);

  const lastBackup = getLastBackupByCategory(backups);
  // "all" means every category was backed up — expand to individual items
  if (lastBackup["all"]) {
    for (const cat of EXPECTED_CATEGORIES) {
      if (!lastBackup[cat]) lastBackup[cat] = lastBackup["all"];
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

  const readinessColor =
    readiness >= 80
      ? "var(--green)"
      : readiness >= 50
        ? "var(--yellow)"
        : "var(--red)";

  const backupColor =
    daysSinceBackup === null
      ? "var(--red)"
      : daysSinceBackup < 3
        ? "var(--green)"
        : daysSinceBackup < 7
          ? "var(--yellow)"
          : "var(--red)";

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-5">
      {/* Restore Readiness */}
      <div
        className="relative overflow-hidden bg-card border border-border rounded-xl px-4 py-4 text-center"
        style={{ borderBottomColor: readinessColor, borderBottomWidth: 2 }}
      >
        <div
          className="text-3xl font-bold tabular-nums tracking-tight"
          style={{ color: readinessColor }}
        >
          {readiness}%
        </div>
        <div className="text-xs text-sub mt-1 font-medium uppercase tracking-wider">
          Restore Ready
        </div>
      </div>

      {/* Last Backup */}
      <div
        className="relative overflow-hidden bg-card border border-border rounded-xl px-4 py-4 text-center"
        style={{ borderBottomColor: backupColor, borderBottomWidth: 2 }}
      >
        <div
          className="text-3xl font-bold tabular-nums tracking-tight"
          style={{ color: backupColor }}
        >
          {daysSinceBackup === null
            ? "\u2014"
            : daysSinceBackup === 0
              ? "Today"
              : `${daysSinceBackup}d`}
        </div>
        <div className="text-xs text-sub mt-1 font-medium uppercase tracking-wider">
          Last Backup
        </div>
      </div>

      {/* Device Status */}
      <div
        className="relative overflow-hidden bg-card border border-border rounded-xl px-4 py-4 text-center"
        style={{
          borderBottomColor: deviceOnline ? "var(--green)" : "var(--dim)",
          borderBottomWidth: 2,
        }}
      >
        <div className="flex items-center justify-center gap-2">
          <span
            className="relative flex h-3 w-3"
          >
            {deviceOnline && (
              <span
                className="absolute inline-flex h-full w-full rounded-full opacity-75 animate-ping"
                style={{ background: "var(--green)" }}
              />
            )}
            <span
              className="relative inline-flex h-3 w-3 rounded-full"
              style={{
                background: deviceOnline ? "var(--green)" : "var(--dim)",
              }}
            />
          </span>
          <span
            className="text-2xl font-bold"
            style={{
              color: deviceOnline ? "var(--green)" : "var(--dim)",
            }}
          >
            {deviceOnline ? "Online" : "Offline"}
          </span>
        </div>
        <div className="text-xs text-sub mt-1.5 font-medium">
          {deviceStatus
            ? `${deviceStatus.battery.capacity}% \u00b7 ${deviceStatus.cpu.tempC.toFixed(0)}\u00b0C`
            : "No signal"}
        </div>
      </div>

      {/* Packages */}
      <div
        className="relative overflow-hidden bg-card border border-border rounded-xl px-4 py-4 text-center"
        style={{ borderBottomColor: "var(--accent)", borderBottomWidth: 2 }}
      >
        <div
          className="text-3xl font-bold tabular-nums tracking-tight"
          style={{ color: "var(--accent)" }}
        >
          {totalPackages.toLocaleString()}
        </div>
        <div className="text-xs text-sub mt-1 font-medium uppercase tracking-wider">
          Packages Tracked
        </div>
      </div>
    </div>
  );
}
