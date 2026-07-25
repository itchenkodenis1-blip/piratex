import { useTranslation } from "../i18n";

interface Props {
  title: string;
}

const FAKE_LINES = [
  "Lorem ipsum dolor sit amet consectetur adipiscing elit sed do eiusmod",
  "Ut enim ad minim veniam quis nostrud exercitation ullamco laboris",
  "Duis aute irure dolor in reprehenderit in voluptate velit esse cillum",
];

export function LockedSection({ title }: Props) {
  const { t } = useTranslation();

  const handleClick = () => {
    window.dispatchEvent(
      new CustomEvent("piratex:limit-reached", {
        detail: { reason: "teaser_unlock" },
      })
    );
  };

  return (
    <div className="relative rounded-xl border border-border-subtle bg-surface-light/30 p-5 overflow-hidden">
      <h3 className="text-xs font-medium text-cream-muted uppercase tracking-widest mb-3">
        {title}
      </h3>
      <div className="space-y-2 select-none" aria-hidden="true">
        {FAKE_LINES.map((line, i) => (
          <p key={i} className="text-sm text-cream-dim" style={{ filter: "blur(5px)" }}>
            {line}
          </p>
        ))}
      </div>
      <div className="absolute inset-0 flex flex-col items-center justify-center bg-surface/40">
        <svg className="w-5 h-5 text-cream-muted mb-1.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
          <path d="M7 11V7a5 5 0 0 1 10 0v4" />
        </svg>
        <p className="text-xs text-cream-dim mb-2">{t.teaser_locked}</p>
        <button
          onClick={handleClick}
          className="px-4 py-1.5 bg-accent hover:bg-accent-hover text-white text-xs font-medium rounded-full transition-colors"
        >
          {t.teaser_cta_button}
        </button>
      </div>
    </div>
  );
}
