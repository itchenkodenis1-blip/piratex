interface Props {
  size?: number;
  className?: string;
}

export function FlagLogo({ size = 32, className }: Props) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 48 48"
      className={className}
      aria-hidden="true"
    >
      <circle cx="24" cy="24" r="23" fill="#201F1D" stroke="#3A3936" />
      <rect x="20" y="7" width="4.5" height="36" rx="2" fill="#F0EFED" />
      <circle cx="22.25" cy="7" r="3" fill="#F0EFED" />
      <path d="M27 9 L37 12 L27 15 Z" fill="#141413" stroke="#A8A29E" strokeWidth="1.4" strokeLinejoin="round" />
      <path d="M27 15 L37 12" stroke="#A8A29E" strokeWidth="1.4" />
    </svg>
  );
}