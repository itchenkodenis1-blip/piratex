import { useTranslation } from "../i18n";
import { useRegion } from "../region";

export function CookiePolicyPage() {
  const { t } = useTranslation();
  const r = useRegion();

  const sub = (text: string) =>
    text
      .replace(/\{brand\}/g, r.brand)
      .replace(/\{entity\}/g, r.legalEntity)
      .replace(/\{email\}/g, r.supportEmail);

  return (
    <div className="w-full max-w-2xl mx-auto space-y-8">
      <h1 className="text-3xl font-serif font-medium text-cream">{t.cookie_policy_title}</h1>
      <p className="text-sm text-cream-dim leading-relaxed">{sub(t.cookie_policy_intro)}</p>

      <section className="space-y-2">
        <h2 className="text-lg font-medium text-cream">{t.cookie_policy_what_title}</h2>
        <p className="text-sm text-cream-dim leading-relaxed">{sub(t.cookie_policy_what_text)}</p>
      </section>

      <section className="space-y-4">
        <h2 className="text-lg font-medium text-cream">{t.cookie_policy_types_title}</h2>

        <div className="bg-surface border border-border-subtle rounded-xl p-4 space-y-1">
          <h3 className="text-sm font-medium text-cream">{t.cookie_policy_essential_title}</h3>
          <p className="text-sm text-cream-dim leading-relaxed">{sub(t.cookie_policy_essential_text)}</p>
        </div>

        <div className="bg-surface border border-border-subtle rounded-xl p-4 space-y-1">
          <h3 className="text-sm font-medium text-cream">{t.cookie_policy_functional_title}</h3>
          <p className="text-sm text-cream-dim leading-relaxed">{sub(t.cookie_policy_functional_text)}</p>
        </div>

        <div className="bg-surface border border-border-subtle rounded-xl p-4 space-y-1">
          <h3 className="text-sm font-medium text-cream">{t.cookie_policy_analytics_title}</h3>
          <p className="text-sm text-cream-dim leading-relaxed">{sub(t.cookie_policy_analytics_text)}</p>
        </div>
      </section>

      <section className="space-y-2">
        <h2 className="text-lg font-medium text-cream">{t.cookie_policy_manage_title}</h2>
        <p className="text-sm text-cream-dim leading-relaxed whitespace-pre-line">{sub(t.cookie_policy_manage_text)}</p>
      </section>

      <section className="space-y-2">
        <h2 className="text-lg font-medium text-cream">{t.cookie_policy_contact_title}</h2>
        <p className="text-sm text-cream-dim leading-relaxed">{sub(t.cookie_policy_contact_text)}</p>
      </section>
    </div>
  );
}
