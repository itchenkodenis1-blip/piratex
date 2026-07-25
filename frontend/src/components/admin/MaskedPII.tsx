import { useState } from "react";

type MaskType = "email" | "telegram" | "name" | "text";

interface MaskedPIIProps {
  type: MaskType;
  value: string | null | undefined;
  fallback?: React.ReactNode;
  className?: string;
}

function maskEmail(v: string): string {
  const at = v.indexOf("@");
  if (at <= 0) return v;
  const local = v.slice(0, at);
  const domain = v.slice(at);
  const show = Math.min(4, local.length);
  return local.slice(0, show) + "*".repeat(Math.max(1, local.length - show)) + domain;
}

function maskTelegram(v: string): string {
  const clean = v.startsWith("@") ? v.slice(1) : v;
  const show = Math.min(4, clean.length);
  return clean.slice(0, show) + "*".repeat(Math.max(1, clean.length - show));
}

function maskName(v: string): string {
  const parts = v.trim().split(/\s+/);
  if (parts.length <= 1) return v.slice(0, 2) + "***";
  return parts[0] + " " + parts.slice(1).map(p => p.slice(0, 1) + "***").join(" ");
}

function maskText(v: string): string {
  if (v.length <= 2) return v;
  return v.slice(0, 2) + "***";
}

const maskers: Record<MaskType, (v: string) => string> = {
  email: maskEmail,
  telegram: maskTelegram,
  name: maskName,
  text: maskText,
};

export default function MaskedPII({ type, value, fallback, className }: MaskedPIIProps) {
  const [revealed, setRevealed] = useState(false);

  if (!value) {
    return <>{fallback ?? "—"}</>;
  }

  const masked = maskers[type](value);
  const display = type === "telegram" ? `@${value}` : value;

  return (
    <span
      className={`cursor-help transition-opacity duration-150 ${className ?? ""}`}
      onMouseEnter={() => setRevealed(true)}
      onMouseLeave={() => setRevealed(false)}
    >
      {revealed ? display : masked}
    </span>
  );
}
