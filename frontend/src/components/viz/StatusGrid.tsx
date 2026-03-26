interface StatusItem {
  name: string;
  color: string;
  detail?: string;
}

interface StatusGridProps {
  items: StatusItem[];
}

export function StatusGrid({ items }: StatusGridProps) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 my-2">
      {items.map((item) => (
        <div
          key={item.name}
          className="flex items-center gap-2.5 bg-background border border-border rounded-lg px-3 py-2 text-xs"
          style={{ borderLeftWidth: 3, borderLeftColor: item.color }}
        >
          <span
            className="w-2.5 h-2.5 rounded-full shrink-0 ring-2 ring-offset-1"
            style={{
              background: item.color,
              ["--tw-ring-color" as string]: `color-mix(in srgb, ${item.color} 30%, transparent)`,
              ["--tw-ring-offset-color" as string]: "var(--bg)",
            }}
          />
          <span className="text-foreground font-medium flex-1">{item.name}</span>
          {item.detail && (
            <span className="text-sub text-[11px] tabular-nums">{item.detail}</span>
          )}
        </div>
      ))}
    </div>
  );
}
