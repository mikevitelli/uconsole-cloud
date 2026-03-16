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
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5 my-2">
      {items.map((item) => (
        <div
          key={item.name}
          className="flex items-center gap-1.5 bg-background border border-border rounded-lg px-2.5 py-1.5 text-xs"
        >
          <span
            className="w-2 h-2 rounded-full shrink-0"
            style={{ background: item.color }}
          />
          <span className="text-foreground flex-1">{item.name}</span>
          {item.detail && (
            <span className="text-dim text-xs">{item.detail}</span>
          )}
        </div>
      ))}
    </div>
  );
}
