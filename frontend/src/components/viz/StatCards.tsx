interface StatCardItem {
  value: string;
  label: string;
  color?: string;
}

interface StatCardsProps {
  items: StatCardItem[];
}

export function StatCards({ items }: StatCardsProps) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 my-3">
      {items.map((item) => (
        <div
          key={item.label}
          className="bg-background border border-border rounded-lg px-2.5 py-2 text-center"
        >
          <div
            className="text-lg font-bold tabular-nums"
            style={{ color: item.color || "var(--bright)" }}
          >
            {item.value}
          </div>
          <div className="text-xs text-dim mt-0.5">{item.label}</div>
        </div>
      ))}
    </div>
  );
}
