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
    <div className={`grid gap-2 my-3 ${items.length <= 2 ? "grid-cols-1 sm:grid-cols-2" : "grid-cols-2 sm:grid-cols-4"}`}>
      {items.map((item, i) => (
        <div
          key={`${i}-${item.label}`}
          className="bg-background border border-border rounded-lg px-3 py-2.5 text-center"
        >
          <div
            className="text-xl font-extrabold tabular-nums tracking-tight leading-tight"
            style={{ color: item.color || "var(--bright)" }}
          >
            {item.value}
          </div>
          <div className="text-[11px] text-sub mt-1 leading-tight">{item.label}</div>
        </div>
      ))}
    </div>
  );
}
