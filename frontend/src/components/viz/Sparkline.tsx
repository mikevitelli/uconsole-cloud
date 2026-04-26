interface SparklineProps {
  data: number[];
  width: number;
  height: number;
}

const LABEL_GUTTER = 22; // px reserved for y-axis labels in HTML overlay

export function Sparkline({ data, width, height }: SparklineProps) {
  if (!data.length) return null;

  const max = Math.max(...data, 1);
  const padTop = 4;
  const padBottom = 2;
  const plotH = height - padTop - padBottom;
  const step = width / Math.max(data.length - 1, 1);

  const points = data
    .map((v, i) => `${Math.round(i * step)},${Math.round(padTop + plotH - (v / max) * plotH)}`)
    .join(" ");

  const fillPoints = `0,${padTop + plotH} ${points} ${width},${padTop + plotH}`;

  const gridLines = [0, 0.5, 1].map((frac) => ({
    y: Math.round(padTop + plotH - frac * plotH),
    label: String(Math.round(frac * max)),
  }));

  return (
    <div className="relative w-full h-full" style={{ paddingLeft: LABEL_GUTTER }}>
      {/* Y-axis labels — rendered as HTML so they don't get stretched by the SVG */}
      <div className="absolute inset-y-0 left-0 w-[22px] pointer-events-none">
        {gridLines.map((g) => (
          <span
            key={g.y}
            className="absolute right-1 text-[10px] text-dim font-mono tabular-nums leading-none -translate-y-1/2"
            style={{ top: `${(g.y / height) * 100}%` }}
          >
            {g.label}
          </span>
        ))}
      </div>
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
        {gridLines.map((g) => (
          <line
            key={g.y}
            x1={0}
            y1={g.y}
            x2={width}
            y2={g.y}
            stroke="var(--border)"
            strokeWidth={0.5}
            strokeDasharray="3,3"
            vectorEffect="non-scaling-stroke"
          />
        ))}
        <polyline
          fill="none"
          stroke="var(--accent)"
          strokeWidth={1.5}
          points={points}
          vectorEffect="non-scaling-stroke"
        />
        <polyline fill="url(#sparkGrad)" stroke="none" points={fillPoints} />
      </svg>
    </div>
  );
}
