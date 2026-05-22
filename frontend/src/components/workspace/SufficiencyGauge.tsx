"use client";
// components/workspace/SufficiencyGauge.tsx — Phase 12: Information completeness meter

interface SufficiencyField {
  key: string;
  label: string;
  icon: string;
  filled: boolean;
  weight: number; // contribution to overall score
}

interface Props {
  fields: SufficiencyField[];
  className?: string;
}

function GaugeArc({ score }: { score: number }) {
  // SVG arc from 210° to 330° (240° sweep)
  const R = 36;
  const cx = 48;
  const cy = 52;
  const toRad = (deg: number) => (deg * Math.PI) / 180;

  const startAngle = 210;
  const sweepTotal = 240;
  const endAngle = startAngle + sweepTotal * score;

  const polarToCart = (angle: number) => ({
    x: cx + R * Math.cos(toRad(angle)),
    y: cy + R * Math.sin(toRad(angle)),
  });

  const start = polarToCart(startAngle);
  const end = polarToCart(endAngle);
  const largeArc = sweepTotal * score > 180 ? 1 : 0;

  const bgEnd = polarToCart(startAngle + sweepTotal);

  const color =
    score >= 0.75 ? "#34d399"  // emerald
    : score >= 0.5 ? "#fbbf24" // amber
    : score >= 0.25 ? "#f97316" // orange
    : "#f87171"; // red

  const label =
    score >= 0.75 ? "Strong"
    : score >= 0.5 ? "Adequate"
    : score >= 0.25 ? "Weak"
    : "Insufficient";

  return (
    <div className="flex flex-col items-center">
      <svg width="96" height="72" viewBox="0 0 96 72">
        {/* Background track */}
        <path
          d={`M ${start.x} ${start.y} A ${R} ${R} 0 1 1 ${bgEnd.x} ${bgEnd.y}`}
          fill="none"
          stroke="#1e293b"
          strokeWidth="7"
          strokeLinecap="round"
        />
        {/* Filled arc */}
        {score > 0.01 && (
          <path
            d={`M ${start.x} ${start.y} A ${R} ${R} 0 ${largeArc} 1 ${end.x} ${end.y}`}
            fill="none"
            stroke={color}
            strokeWidth="7"
            strokeLinecap="round"
            style={{ transition: "all 0.6s ease" }}
          />
        )}
        {/* Center % */}
        <text x={cx} y={cy - 4} textAnchor="middle" fill="white" fontSize="13" fontWeight="700">
          {Math.round(score * 100)}%
        </text>
        <text x={cx} y={cy + 10} textAnchor="middle" fill={color} fontSize="7" fontWeight="600">
          {label.toUpperCase()}
        </text>
      </svg>
    </div>
  );
}

export default function SufficiencyGauge({ fields, className = "" }: Props) {
  const filled = fields.filter(f => f.filled);
  const totalWeight = fields.reduce((s, f) => s + f.weight, 0);
  const filledWeight = filled.reduce((s, f) => s + (f.filled ? f.weight : 0), 0);
  const score = totalWeight > 0 ? filledWeight / totalWeight : 0;

  const scoreColor =
    score >= 0.75 ? "text-emerald-400"
    : score >= 0.5 ? "text-amber-400"
    : score >= 0.25 ? "text-orange-400"
    : "text-red-400";

  const borderColor =
    score >= 0.75 ? "border-emerald-800/40 bg-emerald-950/10"
    : score >= 0.5 ? "border-amber-800/40 bg-amber-950/10"
    : "border-slate-700/50 bg-slate-900/30";

  return (
    <div className={`rounded-xl border p-3 ${borderColor} ${className}`}>
      <div className="flex items-center justify-between mb-2">
        <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-slate-400 flex items-center gap-1.5">
          <span className="h-1.5 w-1.5 rounded-full bg-cyan-400" />
          Case Completeness
        </p>
        <span className={`text-[10px] font-bold ${scoreColor}`}>
          {filled.length}/{fields.length} fields
        </span>
      </div>

      {/* Arc gauge */}
      <GaugeArc score={score} />

      {/* Field dots */}
      <div className="flex flex-wrap gap-1.5 mt-2">
        {fields.map(f => (
          <div
            key={f.key}
            title={f.label}
            className={`flex items-center gap-1 text-[9px] px-1.5 py-0.5 rounded-full border transition-all ${
              f.filled
                ? "border-emerald-700/40 bg-emerald-900/20 text-emerald-400"
                : f.weight >= 3
                ? "border-red-700/40 bg-red-900/10 text-red-400"
                : "border-slate-700/40 bg-slate-800/30 text-slate-600"
            }`}
          >
            <span>{f.icon}</span>
            <span className="font-medium">{f.label}</span>
            {!f.filled && f.weight >= 3 && <span className="text-red-400">*</span>}
          </div>
        ))}
      </div>

      {/* Missing critical hint */}
      {score < 0.5 && (
        <p className="text-[9px] text-slate-600 mt-2 text-center">
          * Required fields — add for safer analysis
        </p>
      )}
    </div>
  );
}
