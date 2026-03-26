interface DonutProps {
  percent: number;
  size: number;
  label?: string;
  centerText: string;
  subText?: string;
  color?: string;
  /** When true, adds a subtle glow effect around the arc */
  glow?: boolean;
}

export function Donut({
  percent,
  size,
  label,
  centerText,
  subText,
  color = "var(--accent)",
  glow = false,
}: DonutProps) {
  const r = (size - 8) / 2;
  const circ = 2 * Math.PI * r;
  const dashPct = Math.min(100, Math.max(0, percent));
  const filled = (circ * dashPct) / 100;
  const filterId = `glow-${size}`;

  return (
    <div className="text-center">
      <svg
        width={size}
        height={size}
        viewBox={`0 0 ${size} ${size}`}
        className="block mx-auto"
      >
        {glow && (
          <defs>
            <filter id={filterId} x="-50%" y="-50%" width="200%" height="200%">
              <feGaussianBlur in="SourceGraphic" stdDeviation="3" result="blur" />
              <feMerge>
                <feMergeNode in="blur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
          </defs>
        )}
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
          filter={glow ? `url(#${filterId})` : undefined}
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
