interface SparklineProps {
  data: number[];
  width: number;
  height: number;
}

export function Sparkline({ data, width, height }: SparklineProps) {
  if (!data.length) return null;

  const max = Math.max(...data, 1);
  const step = width / Math.max(data.length - 1, 1);

  const points = data
    .map((v, i) => `${Math.round(i * step)},${Math.round(height - (v / max) * (height - 4) - 2)}`)
    .join(" ");

  const fillPoints = `0,${height} ${points} ${width},${height}`;

  return (
    <svg
      className="my-2"
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
