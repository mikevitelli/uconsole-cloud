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
    <div className="flex flex-wrap gap-1.5 my-2">
      {items.map((item) => {
        const isActive = selected === item.name;
        return (
          <button
            key={item.name}
            onClick={() => onSelect(isActive ? null : item.name)}
            className="flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs transition-colors cursor-pointer border"
            style={{
              background: isActive ? `${item.color}22` : "transparent",
              borderColor: isActive ? item.color : "var(--border)",
              color: isActive ? item.color : "var(--sub)",
            }}
          >
            <span
              className="w-2 h-2 rounded-full shrink-0"
              style={{ background: item.color }}
            />
            <span>{item.name}</span>
            <span className="tabular-nums opacity-70">{item.count.toLocaleString()}</span>
          </button>
        );
      })}
    </div>
  );
}
