"use client";

import { useRef, useEffect, useState, useCallback } from "react";

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
const WEEKS = 52;

const MONTH_NAMES = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

const FULL_MONTHS = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

function ordinal(day: number): string {
  if (day > 3 && day < 21) return `${day}th`;
  switch (day % 10) {
    case 1: return `${day}st`;
    case 2: return `${day}nd`;
    case 3: return `${day}rd`;
    default: return `${day}th`;
  }
}

function formatTooltip(dateStr: string, count: number): string {
  const [y, m, d] = dateStr.split("-").map(Number);
  const month = FULL_MONTHS[m - 1];
  const day = ordinal(d);
  if (count === 0) return `No backups on ${month} ${day}, ${y}.`;
  return `${count} backup${count !== 1 ? "s" : ""} on ${month} ${day}.`;
}

interface Tooltip {
  text: string;
  x: number;
  y: number;
}

export function CalendarGrid({ data }: CalendarGridProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [mounted, setMounted] = useState(false);
  const [tooltip, setTooltip] = useState<Tooltip | null>(null);

  // eslint-disable-next-line react-hooks/set-state-in-effect -- hydration guard pattern
  useEffect(() => { setMounted(true); }, []);

  // Auto-scroll to the right (current day) on mount
  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollLeft = el.scrollWidth;
  }, [mounted]);

  const handleCellEnter = useCallback((e: React.MouseEvent<SVGRectElement>, dateStr: string, count: number) => {
    const cellRect = (e.target as SVGRectElement).getBoundingClientRect();
    setTooltip({
      text: formatTooltip(dateStr, count),
      x: cellRect.left + cellRect.width / 2,
      y: cellRect.top,
    });
  }, []);

  const handleCellLeave = useCallback(() => {
    setTooltip(null);
  }, []);

  // Don't render date-dependent SVG on server to avoid hydration mismatch
  if (!mounted) {
    return (
      <div className="w-full overflow-x-auto h-[103px]" />
    );
  }

  // Always show a full year ending today, like GitHub
  const today = new Date();
  today.setHours(0, 0, 0, 0);

  // Find the start: go back ~52 weeks, align to Sunday
  const start = new Date(today);
  start.setDate(start.getDate() - (WEEKS * 7) + 1);
  start.setDate(start.getDate() - start.getDay()); // align to Sunday

  const cells: { date: string; count: number; col: number; row: number }[] = [];
  const monthLabels: { label: string; col: number }[] = [];
  let lastMonth = -1;

  const cursor = new Date(start);
  let col = 0;
  while (cursor <= today) {
    const dayOfWeek = cursor.getDay();
    if (dayOfWeek === 0 && cursor > start) col++;

    const key = cursor.toISOString().slice(0, 10);
    cells.push({ date: key, count: data[key] || 0, col, row: dayOfWeek });

    // Track month labels (first Sunday of each new month)
    const month = cursor.getMonth();
    if (month !== lastMonth && dayOfWeek === 0) {
      monthLabels.push({ label: MONTH_NAMES[month], col });
      lastMonth = month;
    }

    cursor.setDate(cursor.getDate() + 1);
  }

  const maxCol = col;
  const labelW = 16;
  const monthLabelH = 12;
  const svgW = labelW + (maxCol + 1) * (CELL + GAP);
  const svgH = monthLabelH + 7 * (CELL + GAP);

  return (
    <div ref={containerRef} className="relative">
      <div ref={scrollRef} className="w-full overflow-x-auto">
        <svg
          viewBox={`0 0 ${svgW} ${svgH}`}
          className="w-full"
          style={{ minWidth: 680 }}
        >
          {/* Month labels */}
          {monthLabels.map((m) => (
            <text
              key={`${m.label}-${m.col}`}
              x={labelW + m.col * (CELL + GAP)}
              y={9}
              fill="var(--dim)"
              fontSize={8}
            >
              {m.label}
            </text>
          ))}
          {/* Day labels */}
          {DAY_LABELS.map((label, i) =>
            label ? (
              <text
                key={i}
                x={0}
                y={monthLabelH + i * (CELL + GAP) + CELL - 1}
                fill="var(--dim)"
                fontSize={8}
              >
                {label}
              </text>
            ) : null
          )}
          {/* Cells */}
          {cells.map((c) => (
            <rect
              key={c.date}
              x={labelW + c.col * (CELL + GAP)}
              y={monthLabelH + c.row * (CELL + GAP)}
              width={CELL}
              height={CELL}
              rx={2}
              fill={getColor(c.count)}
              onMouseEnter={(e) => handleCellEnter(e, c.date, c.count)}
              onMouseLeave={handleCellLeave}
              className="cursor-pointer"
            />
          ))}
        </svg>
      </div>

      {/* GitHub-style tooltip — rendered via portal-like fixed positioning to escape overflow clipping */}
      {tooltip && (
        <div
          className="fixed pointer-events-none"
          style={{
            left: tooltip.x,
            top: tooltip.y - 4,
            transform: "translate(-50%, -100%)",
            zIndex: 9999,
          }}
        >
          <div className="bg-[#1b1f23] text-white text-xs font-medium px-2.5 py-1.5 rounded-md whitespace-nowrap border border-[#3d444d] shadow-lg">
            {tooltip.text}
          </div>
          <div
            className="w-0 h-0 mx-auto"
            style={{
              borderLeft: "6px solid transparent",
              borderRight: "6px solid transparent",
              borderTop: "6px solid #3d444d",
            }}
          />
        </div>
      )}
    </div>
  );
}
