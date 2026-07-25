import { useTranslation } from "../i18n";
import { useRegion } from "../region";

export function TermsPage() {
  const { t } = useTranslation();
  const r = useRegion();

  const sub = (text: string) => {
    let s = text
      .replace(/\{brand\}/g, r.brand)
      .replace(/\{entity\}/g, r.legalEntity)
      .replace(/\{details\}/g, r.legalDetails)
      .replace(/\{address\}/g, r.legalAddress)
      .replace(/\{email\}/g, r.supportEmail);
    // Clean up empty placeholder artifacts (INT region has no details/address)
    s = s.replace(/ \(\)/g, "");
    s = s.replace(/,?\s*(?:address|адрес|adresse|endereco)\s*:\s*(?=\s*[\n("])/gi, " ");
    s = s.replace(/^.*:\s*$/gm, "");
    s = s.replace(/\n{3,}/g, "\n\n");
    return s.trim();
  };

  const sections = [
    { title: t.terms_definitions_title, text: t.terms_definitions_text },
    { title: t.terms_subject_title, text: t.terms_subject_text },
    { title: t.terms_acceptance_title, text: t.terms_acceptance_text },
    { title: t.terms_pricing_title, text: t.terms_pricing_text },
    { title: t.terms_payment_title, text: t.terms_payment_text },
    { title: t.terms_recurring_title, text: t.terms_recurring_text },
    { title: t.terms_cancellation_title, text: t.terms_cancellation_text },
    { title: t.terms_obligations_title, text: t.terms_obligations_text },
    { title: t.terms_ai_title, text: t.terms_ai_text },
    { title: t.terms_liability_title, text: t.terms_liability_text },
    { title: t.terms_ip_title, text: t.terms_ip_text },
    { title: t.terms_personaldata_title, text: t.terms_personaldata_text },
    { title: t.terms_termination_title, text: t.terms_termination_text },
    { title: t.terms_modifications_title, text: t.terms_modifications_text },
    { title: t.terms_disputes_title, text: t.terms_disputes_text },
    { title: t.terms_forcemajeure_title, text: t.terms_forcemajeure_text },
    { title: t.terms_contact_title, text: t.terms_contact_text },
  ];

  return (
    <div className="w-full max-w-2xl mx-auto space-y-8">
      <h1 className="text-3xl font-serif font-medium text-cream">{t.terms_title}</h1>
      <p className="text-sm text-cream-dim leading-relaxed whitespace-pre-line">{sub(t.terms_intro)}</p>

      {sections.map((s) => (
        <section key={s.title} className="space-y-2">
          <h2 className="text-lg font-medium text-cream">{s.title}</h2>
          <p className="text-sm text-cream-dim leading-relaxed whitespace-pre-line">{sub(s.text)}</p>
        </section>
      ))}
    </div>
  );
}
