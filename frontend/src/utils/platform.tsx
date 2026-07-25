// eslint-disable-next-line react-refresh/only-export-components
export const PLATFORM_COLORS: Record<string, string> = {
  instagram: "bg-pink-500/20 text-pink-300 border-pink-500/30",
  youtube: "bg-red-500/20 text-red-300 border-red-500/30",
  tiktok: "bg-cyan-500/20 text-cyan-300 border-cyan-500/30",
};

export function PlatformIcon({ platform }: { platform: string }) {
  const p = platform.toLowerCase();
  const cls = "w-6 h-6 sm:w-7 sm:h-7 drop-shadow-lg";
  if (p === "instagram") {
    return (
      <svg className={cls} viewBox="0 0 24 24" fill="none">
        <defs>
          <radialGradient id="ig" cx="30%" cy="107%" r="150%">
            <stop offset="0%" stopColor="#fdf497" />
            <stop offset="5%" stopColor="#fdf497" />
            <stop offset="45%" stopColor="#fd5949" />
            <stop offset="60%" stopColor="#d6249f" />
            <stop offset="90%" stopColor="#285AEB" />
          </radialGradient>
        </defs>
        <rect x="2" y="2" width="20" height="20" rx="6" fill="url(#ig)" />
        <circle cx="12" cy="12" r="4.5" stroke="white" strokeWidth="1.8" fill="none" />
        <circle cx="17.2" cy="6.8" r="1.2" fill="white" />
      </svg>
    );
  }
  if (p === "youtube") {
    return (
      <svg className={cls} viewBox="0 0 24 24" fill="none">
        <rect x="1" y="4" width="22" height="16" rx="4" fill="#FF0000" />
        <path d="M10 8.5v7l6-3.5-6-3.5z" fill="white" />
      </svg>
    );
  }
  if (p === "tiktok") {
    return (
      <svg className={cls} viewBox="0 0 24 24" fill="none">
        <rect x="2" y="2" width="20" height="20" rx="6" fill="black" />
        <path d="M16.5 8.5c-1.1-.8-1.8-2-1.9-3.5h-2.1v10.5a2.5 2.5 0 1 1-1.7-2.4V11a4.5 4.5 0 1 0 3.7 4.5V10c.8.6 1.8 1 2.9 1V8.9c-.3 0-.6 0-.9-.1z" fill="white" />
      </svg>
    );
  }
  return null;
}
