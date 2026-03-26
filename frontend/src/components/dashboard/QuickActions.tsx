interface QuickActionsProps {
  deviceLocalIp: string;
}

const QUICK_LINKS = [
  { label: "System Stats", hash: "" },
  { label: "Run Backup", hash: "#backup" },
  { label: "Logs", hash: "#logs" },
  { label: "Wiki", hash: "#wiki" },
];

/**
 * Quick-link buttons to specific webdash pages on the local device.
 * Pure <a> tags — no fetch, no client-side state. Opens in new tab.
 */
export function QuickActions({ deviceLocalIp }: QuickActionsProps) {
  const base = `https://${deviceLocalIp}`;

  return (
    <div>
      <p className="text-[11px] text-dim font-medium uppercase tracking-wider mb-1.5">
        Quick links
      </p>
      <div className="flex flex-wrap gap-1.5">
        {QUICK_LINKS.map((link) => (
          <a
            key={link.label}
            href={`${base}/${link.hash}`}
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs font-medium px-2.5 py-1.5 rounded-md border border-border bg-background text-bright hover:border-[var(--accent)] transition-colors"
          >
            {link.label}
          </a>
        ))}
      </div>
    </div>
  );
}
