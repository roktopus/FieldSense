type Props = {
  /** Compact mark-only (e.g. favicon-sized contexts) */
  markOnly?: boolean;
  className?: string;
};

/**
 * FieldSense brand mark: wellhead stem + sensing arcs (field intelligence).
 * Colors follow Wellhead tokens (copper / moss on pine).
 */
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
        <rect width="40" height="40" rx="10" fill="#143832" />
        {/* Sensing arcs */}
        <path
          d="M12 22c0-4.4 3.6-8 8-8s8 3.6 8 8"
          stroke="#c46b2d"
          strokeWidth="1.75"
          strokeLinecap="round"
          opacity="0.9"
        />
        <path
          d="M15.5 22c0-2.5 2-4.5 4.5-4.5s4.5 2 4.5 4.5"
          stroke="#1a7a6d"
          strokeWidth="1.75"
          strokeLinecap="round"
        />
        {/* Wellhead / derrick stem */}
        <path
          d="M20 10v18"
          stroke="#f7f8f6"
          strokeWidth="2"
          strokeLinecap="round"
        />
        <path
          d="M15 14h10"
          stroke="#f7f8f6"
          strokeWidth="2"
          strokeLinecap="round"
        />
        <circle cx="20" cy="22" r="2.25" fill="#c46b2d" />
        <path
          d="M17 30h6"
          stroke="#f7f8f6"
          strokeWidth="1.75"
          strokeLinecap="round"
          opacity="0.7"
        />
      </svg>
      {!markOnly ? (
        <span className="min-w-0 text-left leading-tight">
          <span className="fs-brand-mark block font-display text-[1.35rem] font-semibold tracking-tight text-white">
            FieldSense
          </span>
          <span className="mt-0.5 block text-[11px] font-medium leading-snug text-stone/65">
            Field intelligence for your wells
          </span>
        </span>
      ) : null}
    </span>
  );
}
