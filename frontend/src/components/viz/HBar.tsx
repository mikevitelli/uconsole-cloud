const COLORS = [
  "#58a6ff", "#3fb950", "#d29922", "#f85149",
  "#bc8cff", "#79c0ff", "#56d364", "#e3b341",
  "#ff7b72", "#d2a8ff",
];

interface HBarItem {
  name: string;
  value: number;
  label?: string;
}

interface HBarProps {
  items: HBarItem[];
  maxVal?: number;
}

export function HBar({ items, maxVal }: HBarProps) {
  const max = maxVal || Math.max(...items.map((i) => i.value), 1);

  return (
    <div className="my-1">
      {items.map((item, i) => {
        const pct = Math.round((item.value * 100) / max);
        return (
          <div key={item.name} className="flex items-center gap-2 py-0.5 text-sm">
            <span className="text-sub min-w-20 sm:min-w-[90px] overflow-hidden text-ellipsis whitespace-nowrap shrink-0">
              {item.name}
            </span>
            <div className="flex-1 h-2.5 bg-[#21262d] rounded-full overflow-hidden">
              <div
                className="h-full rounded-full transition-[width] duration-300"
                style={{ width: `${pct}%`, background: COLORS[i % COLORS.length] }}
              />
            </div>
            <span className="min-w-10 sm:min-w-[45px] text-right text-dim tabular-nums">
              {item.label || String(item.value)}
            </span>
          </div>
        );
      })}
    </div>
  );
}
