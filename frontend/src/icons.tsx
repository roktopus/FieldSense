import type { SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement> & { size?: number };

function base({ size = 18, className, ...rest }: IconProps) {
  return {
    width: size,
    height: size,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.75,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    className,
    "aria-hidden": true as const,
    ...rest,
  };
}

export function IconWell(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M12 3v18" />
      <path d="M8 7h8" />
      <path d="M9 11c0 2 1.5 4 3 6 1.5-2 3-4 3-6" />
      <circle cx="12" cy="11" r="1.2" fill="currentColor" stroke="none" />
    </svg>
  );
}

export function IconTable(p: IconProps) {
  return (
    <svg {...base(p)}>
      <rect x="3" y="4" width="18" height="16" rx="2" />
      <path d="M3 10h18M3 14h18M9 4v16M15 4v16" />
    </svg>
  );
}

export function IconChart(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M4 19V5" />
      <path d="M4 19h16" />
      <path d="M8 16v-5M12 16V8M16 16v-3" />
    </svg>
  );
}

export function IconTrend(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M4 18 9 12l4 3 7-9" />
      <path d="M15 6h5v5" />
    </svg>
  );
}

export function IconMap(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M9 4 3 6v14l6-2 6 2 6-2V4l-6 2-6-2z" />
      <path d="M9 4v14M15 6v14" />
    </svg>
  );
}

export function IconThermometer(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M14 14.76V5a2 2 0 1 0-4 0v9.76a4 4 0 1 0 4 0z" />
    </svg>
  );
}

export function IconUser(p: IconProps) {
  return (
    <svg {...base(p)}>
      <circle cx="12" cy="8" r="3.5" />
      <path d="M5 20a7 7 0 0 1 14 0" />
    </svg>
  );
}

export function IconCalendar(p: IconProps) {
  return (
    <svg {...base(p)}>
      <rect x="3" y="5" width="18" height="16" rx="2" />
      <path d="M3 10h18M8 3v4M16 3v4" />
    </svg>
  );
}

export function IconAlert(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M12 3 2.5 20h19L12 3z" />
      <path d="M12 10v4M12 17h.01" />
    </svg>
  );
}

export function IconEvidence(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M8 4h7l5 5v11a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z" />
      <path d="M14 4v5h5M9 13h6M9 17h4" />
    </svg>
  );
}

export function IconSpark(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M12 3v4M12 17v4M4.9 6.5l2.8 2.8M16.3 14.7l2.8 2.8M3 12h4M17 12h4M4.9 17.5l2.8-2.8M16.3 9.3l2.8-2.8" />
    </svg>
  );
}

export function IconCheck(p: IconProps) {
  return (
    <svg {...base(p)}>
      <circle cx="12" cy="12" r="9" />
      <path d="m8.5 12.5 2.2 2.2 4.8-5" />
    </svg>
  );
}

export function IconX(p: IconProps) {
  return (
    <svg {...base(p)}>
      <circle cx="12" cy="12" r="9" />
      <path d="m9 9 6 6M15 9l-6 6" />
    </svg>
  );
}

export function IconInfo(p: IconProps) {
  return (
    <svg {...base(p)}>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 11v5M12 8h.01" />
    </svg>
  );
}

export function IconSend(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M5 12h10M13 8l4 4-4 4" />
    </svg>
  );
}

export function IconBot(p: IconProps) {
  return (
    <svg {...base(p)}>
      <rect x="5" y="8" width="14" height="11" rx="3" />
      <path d="M12 4v4M9 13h.01M15 13h.01M9 16h6" />
    </svg>
  );
}

export function IconHeat(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M12 21a5 5 0 0 0 5-5c0-3-5-7-5-7s-5 4-5 7a5 5 0 0 0 5 5z" />
      <path d="M9 10c1-2 2-4 3-7 1 3 2 5 3 7" />
    </svg>
  );
}
