type ScoreScaleProps = {
  value: number;
  onChange: (value: number) => void;
  disabled?: boolean;
};

const SCORES = [1, 2, 3, 4, 5];

export function ScoreScale({ value, onChange, disabled = false }: ScoreScaleProps) {
  return (
    <div role="radiogroup" aria-label="Score from 1 to 5" className="w-full max-w-md">
      <div className="relative flex items-center justify-between">
        <div className="absolute left-4 right-4 top-1/2 h-1 -translate-y-1/2 rounded-full bg-slate-200" />
        <div
          className="absolute left-4 top-1/2 h-1 -translate-y-1/2 rounded-full bg-blue-600 transition-all"
          style={{ width: `calc((100% - 2rem) * ${(value - 1) / (SCORES.length - 1)})` }}
        />
        {SCORES.map((score) => (
          <button
            key={score}
            type="button"
            role="radio"
            aria-checked={score === value}
            disabled={disabled}
            onClick={() => onChange(score)}
            className={`relative z-10 flex h-8 w-8 items-center justify-center rounded-full border-2 text-sm font-semibold transition-all disabled:opacity-50 ${
              score <= value
                ? "border-blue-600 bg-blue-600 text-white"
                : "border-slate-300 bg-white text-slate-600 hover:border-blue-400"
            }`}
          >
            {score}
          </button>
        ))}
      </div>
    </div>
  );
}
