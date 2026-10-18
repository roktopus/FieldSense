type Props = {
  /** Compact mark-only (e.g. favicon-sized contexts) */
  markOnly?: boolean;
  className?: string;
};

/** Side-view pump jack. White tile so it stays readable on the black sidebar. */
export function FieldSenseLogo({ markOnly = false, className = "" }: Props) {
  return (
    <span className={`inline-flex items-center gap-2.5 ${className}`}>
      <svg
        width={markOnly ? 28 : 36}
        height={markOnly ? 28 : 36}
        viewBox="0 0 40 40"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        className="shrink-0"
        aria-hidden
      >
        <rect width="40" height="40" rx="8" fill="#ffffff" />
        <path d="M8 34h24" stroke="#0a0a0a" strokeWidth="1.6" strokeLinecap="round" />
        <path
          d="M14.5 34 20 16.5 25.5 34"
          stroke="#0a0a0a"
          strokeWidth="1.6"
          strokeLinejoin="round"
          strokeLinecap="round"
        />
        <path
          d="M8.5 21.5 20 16.5 30 12"
          stroke="#0a0a0a"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <path
          d="M30 12c3.2 1.2 4.2 5.2 2.4 8.2"
          stroke="#0a0a0a"
          strokeWidth="2"
          strokeLinecap="round"
        />
        <path d="M32.2 20.2v9.2" stroke="#0a0a0a" strokeWidth="1.5" strokeLinecap="round" />
        <path d="M29.6 30.6h5.2" stroke="#0a0a0a" strokeWidth="2" strokeLinecap="round" />
        <rect x="7.2" y="18.6" width="4.2" height="4.6" rx="0.6" fill="#0a0a0a" />
        <circle cx="15.2" cy="27.5" r="2.3" stroke="#0a0a0a" strokeWidth="1.4" />
        <path d="M15.2 27.5 12.6 25.2" stroke="#0a0a0a" strokeWidth="1.4" strokeLinecap="round" />
      </svg>
      {!markOnly ? (
        <span className="min-w-0 text-left leading-tight">
          <span className="fs-brand-mark block text-[15px] font-semibold tracking-tight text-white">
            FieldSense
          </span>
          <span className="mt-0.5 block text-[11px] leading-snug text-white/70">
            Field intelligence
          </span>
        </span>
      ) : null}
    </span>
  );
}
