import { useTranslation } from "../i18n";
import { useRegion } from "../region";

export function RefundPolicyPage() {
  const { t } = useTranslation();
  const r = useRegion();

  const sub = (text: string) =>
    text
      .replace(/\{brand\}/g, r.brand)
      .replace(/\{entity\}/g, r.legalEntity)
      .replace(/\{email\}/g, r.supportEmail);

  return (
    <div className="w-full max-w-2xl mx-auto space-y-8">
      <h1 className="text-3xl font-serif font-medium text-cream">{t.refund_title}</h1>
      <p className="text-sm text-cream-dim leading-relaxed">{sub(t.refund_intro)}</p>

      <section className="space-y-2">
        <h2 className="text-lg font-medium text-cream">{t.refund_right_title}</h2>
        <p className="text-sm text-cream-dim leading-relaxed">{sub(t.refund_right_text)}</p>
      </section>

      <section className="space-y-2">
        <h2 className="text-lg font-medium text-cream">{t.refund_how_title}</h2>
        <p className="text-sm text-cream-dim leading-relaxed whitespace-pre-line">{sub(t.refund_how_text)}</p>
      </section>

      <section className="space-y-2">
        <h2 className="text-lg font-medium text-cream">{t.refund_timeline_title}</h2>
        <p className="text-sm text-cream-dim leading-relaxed">{sub(t.refund_timeline_text)}</p>
      </section>

      <section className="space-y-2">
        <h2 className="text-lg font-medium text-cream">{t.refund_exceptions_title}</h2>
        <p className="text-sm text-cream-dim leading-relaxed whitespace-pre-line">{sub(t.refund_exceptions_text)}</p>
      </section>

      <section className="space-y-2">
        <h2 className="text-lg font-medium text-cream">{t.refund_contact_title}</h2>
        <p className="text-sm text-cream-dim leading-relaxed">{sub(t.refund_contact_text)}</p>
      </section>
    </div>
  );
}
