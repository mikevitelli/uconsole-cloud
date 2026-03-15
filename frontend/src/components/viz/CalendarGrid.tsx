interface CalendarGridProps {
  data: Record<string, number>;
}

const COLORS = ["#21262d", "#0e4429", "#006d32", "#26a641", "#3fb950"];

function getColor(count: number): string {
  if (count === 0) return COLORS[0];
  if (count === 1) return COLORS[1];
  if (count === 2) return COLORS[2];
  if (count === 3) return COLORS[3];
  return COLORS[4];
}

const DAY_LABELS = ["", "M", "", "W", "", "F", ""];
const CELL = 11;
const GAP = 2;

export function CalendarGrid({ data }: CalendarGridProps) {
  const dates = Object.keys(data).sort();
  if (dates.length === 0) return null;

  // Build grid: 7 rows (Sun-Sat) x N weeks
  const first = new Date(dates[0] + "T00:00:00");
  const last = new Date(dates[dates.length - 1] + "T00:00:00");
  const startDay = first.getDay(); // 0=Sun

  // Generate all dates from start of first week to end of last week
  const gridStart = new Date(first);
  gridStart.setDate(gridStart.getDate() - startDay);

  const cells: { date: string; count: number; col: number; row: number }[] = [];
  let maxCol = 0;
  const cursor = new Date(gridStart);
  while (cursor <= last) {
    const key = cursor.toISOString().slice(0, 10);
    const dayOfWeek = cursor.getDay();
    const diffDays = Math.round(
      (cursor.getTime() - gridStart.getTime()) / 86400000
    );
    const col = Math.floor(diffDays / 7);
    if (col > maxCol) maxCol = col;
    cells.push({ date: key, count: data[key] || 0, col, row: dayOfWeek });
    cursor.setDate(cursor.getDate() + 1);
  }

  const labelW = 16;
  const svgW = labelW + (maxCol + 1) * (CELL + GAP);
  const svgH = 7 * (CELL + GAP);

  return (
    <svg
      viewBox={`0 0 ${svgW} ${svgH}`}
      className="w-full max-w-md"
      style={{ aspectRatio: `${svgW} / ${svgH}` }}
    >
      {DAY_LABELS.map((label, i) =>
        label ? (
          <text
            key={i}
            x={0}
            y={i * (CELL + GAP) + CELL - 1}
            fill="var(--dim)"
            fontSize={8}
          >
            {label}
          </text>
        ) : null
      )}
      {cells.map((c) => (
        <rect
          key={c.date}
          x={labelW + c.col * (CELL + GAP)}
          y={c.row * (CELL + GAP)}
          width={CELL}
          height={CELL}
          rx={2}
          fill={getColor(c.count)}
        >
          <title>
            {c.date}: {c.count} commit{c.count !== 1 ? "s" : ""}
          </title>
        </rect>
      ))}
    </svg>
  );
}
