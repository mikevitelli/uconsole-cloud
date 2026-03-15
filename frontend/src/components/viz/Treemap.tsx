"use client";

interface TreemapItem {
  name: string;
  value: number;
  color: string;
}

interface TreemapProps {
  items: TreemapItem[];
  height: number;
  onSelect?: (name: string) => void;
  selected?: string | null;
}

interface Rect {
  x: number;
  y: number;
  w: number;
  h: number;
  name: string;
  value: number;
  color: string;
}

function layoutRow(
  items: TreemapItem[],
  x: number,
  y: number,
  w: number,
  h: number
): Rect[] {
  if (items.length === 0) return [];
  if (items.length === 1) {
    return [{ x, y, w, h, ...items[0] }];
  }

  const total = items.reduce((s, i) => s + i.value, 0);
  const rects: Rect[] = [];

  // Squarified: split at the point that minimizes worst aspect ratio
  const horizontal = w >= h;
  let bestSplit = 1;
  let bestWorst = Infinity;

  for (let split = 1; split < items.length; split++) {
    const firstSum = items.slice(0, split).reduce((s, i) => s + i.value, 0);
    const firstFrac = firstSum / total;
    const secondFrac = 1 - firstFrac;

    // Compute worst aspect ratio in first group
    let worst = 0;
    if (horizontal) {
      const sliceW = w * firstFrac;
      let offset = 0;
      for (let i = 0; i < split; i++) {
        const frac = items[i].value / firstSum;
        const cellH = h * frac;
        const ar = Math.max(sliceW / cellH, cellH / sliceW);
        if (ar > worst) worst = ar;
        offset += cellH;
      }
      const sliceW2 = w * secondFrac;
      const secondSum = total - firstSum;
      for (let i = split; i < items.length; i++) {
        const frac = items[i].value / secondSum;
        const cellH = h * frac;
        const ar = Math.max(sliceW2 / cellH, cellH / sliceW2);
        if (ar > worst) worst = ar;
      }
    } else {
      const sliceH = h * firstFrac;
      for (let i = 0; i < split; i++) {
        const frac = items[i].value / firstSum;
        const cellW = w * frac;
        const ar = Math.max(sliceH / cellW, cellW / sliceH);
        if (ar > worst) worst = ar;
      }
      const sliceH2 = h * secondFrac;
      const secondSum = total - firstSum;
      for (let i = split; i < items.length; i++) {
        const frac = items[i].value / secondSum;
        const cellW = w * frac;
        const ar = Math.max(sliceH2 / cellW, cellW / sliceH2);
        if (ar > worst) worst = ar;
      }
    }

    if (worst < bestWorst) {
      bestWorst = worst;
      bestSplit = split;
    }
  }

  const firstItems = items.slice(0, bestSplit);
  const secondItems = items.slice(bestSplit);
  const firstSum = firstItems.reduce((s, i) => s + i.value, 0);
  const firstFrac = firstSum / total;

  if (horizontal) {
    const w1 = w * firstFrac;
    rects.push(...layoutRow(firstItems, x, y, w1, h));
    rects.push(...layoutRow(secondItems, x + w1, y, w - w1, h));
  } else {
    const h1 = h * firstFrac;
    rects.push(...layoutRow(firstItems, x, y, w, h1));
    rects.push(...layoutRow(secondItems, x, y + h1, w, h - h1));
  }

  return rects;
}

export function Treemap({ items, height, onSelect, selected }: TreemapProps) {
  const sorted = [...items].sort((a, b) => b.value - a.value);
  const W = 600;
  const gap = 1;
  const rects = layoutRow(sorted, 0, 0, W, height);

  return (
    <svg
      viewBox={`0 0 ${W} ${height}`}
      className="w-full"
      style={{ aspectRatio: `${W} / ${height}` }}
    >
      {rects.map((r) => {
        const isSelected = selected === r.name;
        const showLabel = r.w > 60 && r.h > 30;
        return (
          <g
            key={r.name}
            onClick={() => onSelect?.(r.name)}
            className="cursor-pointer"
          >
            <rect
              x={r.x + gap}
              y={r.y + gap}
              width={Math.max(0, r.w - gap * 2)}
              height={Math.max(0, r.h - gap * 2)}
              rx={3}
              fill={r.color}
              opacity={isSelected ? 1 : 0.75}
              className="hover:opacity-100 transition-opacity"
            />
            {isSelected && (
              <rect
                x={r.x + gap}
                y={r.y + gap}
                width={Math.max(0, r.w - gap * 2)}
                height={Math.max(0, r.h - gap * 2)}
                rx={3}
                fill="none"
                stroke="var(--bright)"
                strokeWidth={2}
              />
            )}
            {showLabel && (
              <>
                <text
                  x={r.x + r.w / 2}
                  y={r.y + r.h / 2 - 5}
                  textAnchor="middle"
                  fill="#fff"
                  fontSize={12}
                  fontWeight={600}
                >
                  {r.name}
                </text>
                <text
                  x={r.x + r.w / 2}
                  y={r.y + r.h / 2 + 10}
                  textAnchor="middle"
                  fill="rgba(255,255,255,0.7)"
                  fontSize={10}
                >
                  {r.value.toLocaleString()}
                </text>
              </>
            )}
          </g>
        );
      })}
    </svg>
  );
}
