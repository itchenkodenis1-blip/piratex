import { useTranslation } from "../i18n";
import { useRegion } from "../region";

export function PrivacyPolicyPage() {
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

  return (
    <div className="w-full max-w-2xl mx-auto space-y-8">
      <h1 className="text-3xl font-serif font-medium text-cream">{t.privacy_title}</h1>
      <p className="text-sm text-cream-dim leading-relaxed whitespace-pre-line">{sub(t.privacy_intro)}</p>

      <section className="space-y-2">
        <h2 className="text-lg font-medium text-cream">{t.privacy_data_title}</h2>
        <p className="text-sm text-cream-dim leading-relaxed whitespace-pre-line">{sub(t.privacy_data_text)}</p>
      </section>

      <section className="space-y-2">
        <h2 className="text-lg font-medium text-cream">{t.privacy_purposes_title}</h2>
        <p className="text-sm text-cream-dim leading-relaxed whitespace-pre-line">{sub(t.privacy_purposes_text)}</p>
      </section>

      <section className="space-y-2">
        <h2 className="text-lg font-medium text-cream">{t.privacy_legal_title}</h2>
        <p className="text-sm text-cream-dim leading-relaxed whitespace-pre-line">{sub(t.privacy_legal_text)}</p>
      </section>

      <section className="space-y-2">
        <h2 className="text-lg font-medium text-cream">{t.privacy_sharing_title}</h2>
        <p className="text-sm text-cream-dim leading-relaxed whitespace-pre-line">{sub(t.privacy_sharing_text)}</p>
      </section>

      <section className="space-y-2">
        <h2 className="text-lg font-medium text-cream">{t.privacy_retention_title}</h2>
        <p className="text-sm text-cream-dim leading-relaxed whitespace-pre-line">{sub(t.privacy_retention_text)}</p>
      </section>

      <section className="space-y-2">
        <h2 className="text-lg font-medium text-cream">{t.privacy_rights_title}</h2>
        <p className="text-sm text-cream-dim leading-relaxed whitespace-pre-line">{sub(t.privacy_rights_text)}</p>
      </section>

      <section className="space-y-2">
        <h2 className="text-lg font-medium text-cream">{t.privacy_security_title}</h2>
        <p className="text-sm text-cream-dim leading-relaxed whitespace-pre-line">{sub(t.privacy_security_text)}</p>
      </section>

      <section className="space-y-2">
        <h2 className="text-lg font-medium text-cream">{t.privacy_changes_title}</h2>
        <p className="text-sm text-cream-dim leading-relaxed whitespace-pre-line">{sub(t.privacy_changes_text)}</p>
      </section>

      <section className="space-y-2">
        <h2 className="text-lg font-medium text-cream">{t.privacy_contact_title}</h2>
        <p className="text-sm text-cream-dim leading-relaxed whitespace-pre-line">{sub(t.privacy_contact_text)}</p>
      </section>
    </div>
  );
}
