interface DonutProps {
  percent: number;
  size: number;
  label?: string;
  centerText: string;
  subText?: string;
  color?: string;
}

export function Donut({
  percent,
  size,
  label,
  centerText,
  subText,
  color = "var(--accent)",
}: DonutProps) {
  const r = (size - 8) / 2;
  const circ = 2 * Math.PI * r;
  const dashPct = Math.min(100, Math.max(0, percent));
  const filled = (circ * dashPct) / 100;

  return (
    <div className="text-center">
      <svg
        width={size}
        height={size}
        viewBox={`0 0 ${size} ${size}`}
        className="block mx-auto"
      >
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke="#21262d"
          strokeWidth={5}
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={color}
          strokeWidth={5}
          strokeDasharray={`${filled} ${circ - filled}`}
          strokeDashoffset={-circ * 0.25}
          strokeLinecap="round"
          className="transition-[stroke-dasharray] duration-500"
        />
        <text
          x={size / 2}
          y={size / 2 - 2}
          textAnchor="middle"
          fill="var(--bright)"
          fontSize={size * 0.2}
          fontWeight={700}
        >
          {centerText}
        </text>
        {subText && (
          <text
            x={size / 2}
            y={size / 2 + size * 0.12}
            textAnchor="middle"
            fill="var(--dim)"
            fontSize={size * 0.1}
          >
            {subText}
          </text>
        )}
      </svg>
      {label && (
        <div className="text-xs text-dim mt-1">{label}</div>
      )}
    </div>
  );
}
