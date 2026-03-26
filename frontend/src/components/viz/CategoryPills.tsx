"use client";

interface PillItem {
  name: string;
  count: number;
  color: string;
}

interface CategoryPillsProps {
  items: PillItem[];
  selected: string | null;
  onSelect: (name: string | null) => void;
}

export function CategoryPills({ items, selected, onSelect }: CategoryPillsProps) {
  return (
    <div className="flex flex-wrap gap-1.5 my-3">
      {items.map((item) => {
        const isActive = selected === item.name;
        return (
          <button
            key={item.name}
            onClick={() => onSelect(isActive ? null : item.name)}
            className="flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-medium transition-all cursor-pointer border hover:brightness-125"
            style={{
              background: isActive ? `${item.color}22` : "var(--card)",
              borderColor: isActive ? item.color : "var(--border)",
              color: isActive ? item.color : "var(--text)",
              boxShadow: isActive ? `0 0 8px ${item.color}20` : "none",
            }}
          >
            <span
              className="w-2 h-2 rounded-full shrink-0"
              style={{ background: item.color }}
            />
            <span>{item.name}</span>
            <span
              className="tabular-nums text-[10px] rounded-full px-1.5 py-0.5 ml-0.5"
              style={{
                background: isActive ? `${item.color}18` : "var(--bg)",
                color: isActive ? item.color : "var(--sub)",
              }}
            >
              {item.count.toLocaleString()}
            </span>
          </button>
        );
      })}
    </div>
  );
}
