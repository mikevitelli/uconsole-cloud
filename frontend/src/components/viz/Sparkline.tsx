interface SparklineProps {
  data: number[];
  width: number;
  height: number;
}

export function Sparkline({ data, width, height }: SparklineProps) {
  if (!data.length) return null;

  const max = Math.max(...data, 1);
  const padLeft = 24;
  const padRight = 4;
  const padTop = 4;
  const padBottom = 2;
  const plotW = width - padLeft - padRight;
  const plotH = height - padTop - padBottom;
  const step = plotW / Math.max(data.length - 1, 1);

  const points = data
    .map((v, i) => `${Math.round(padLeft + i * step)},${Math.round(padTop + plotH - (v / max) * plotH)}`)
    .join(" ");

  const fillPoints = `${padLeft},${padTop + plotH} ${points} ${padLeft + plotW},${padTop + plotH}`;

  // Horizontal grid lines at 0, mid, max
  const gridLines = [0, 0.5, 1].map((frac) => ({
    y: Math.round(padTop + plotH - frac * plotH),
    label: String(Math.round(frac * max)),
  }));

  return (
    <svg
      width="100%"
      height="100%"
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
    >
      <defs>
        <linearGradient id="sparkGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="var(--accent)" stopOpacity={0.3} />
          <stop offset="100%" stopColor="var(--accent)" stopOpacity={0} />
        </linearGradient>
      </defs>
      {/* Grid lines */}
      {gridLines.map((g) => (
        <g key={g.y}>
          <line
            x1={padLeft}
            y1={g.y}
            x2={width - padRight}
            y2={g.y}
            stroke="var(--border)"
            strokeWidth={0.5}
            strokeDasharray="3,3"
          />
          <text
            x={padLeft - 4}
            y={g.y + 3}
            textAnchor="end"
            fill="var(--dim)"
            fontSize={7}
            style={{ fontFamily: "var(--font-mono)" }}
          >
            {g.label}
          </text>
        </g>
      ))}
      <polyline
        fill="none"
        stroke="var(--accent)"
        strokeWidth={1.5}
        points={points}
      />
      <polyline fill="url(#sparkGrad)" stroke="none" points={fillPoints} />
    </svg>
  );
}
