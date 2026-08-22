
export type Region = "ru" | "int";

export type AuthProvider = "yandex" | "google" | "magic_link";

export interface RegionConfig {
  region: Region;
  brand: string;
  legalEntity: string;
  legalDetails: string;
  legalAddress: string;
  termsUrl: string;
  privacyUrl: string;
  refundUrl: string;
  cookiePolicyUrl: string;
  supportEmail: string;
  telegramChannel: string;
  telegramBot: string;
  currency: "RUB" | "EUR";
  currencySymbol: string;
  paymentProvider: "yookassa" | "stripe" | "cloudpayments";
  authProviders: AuthProvider[];
}

// ⚠️ DEPLOYERS: replace the placeholder brand, legal entity, contact and
// Telegram values below with YOUR OWN before going live. Publishing another
// company's legal details (name, tax ID, address) on your site is illegal.
// telegramChannel / telegramBot can stay empty to hide those links.
const REGION_CONFIGS: Record<Region, RegionConfig> = {
  ru: {
    region: "ru",
    brand: "ВидеоРентген",
    legalEntity: "Your Company",
    legalDetails: "Your registration / tax ID",
    legalAddress: "Your registered address",
    termsUrl: "/terms-ru",
    privacyUrl: "/privacy-ru",
    refundUrl: "/refund-ru",
    cookiePolicyUrl: "/cookie-policy-ru",
    supportEmail: "support@example.com",
    telegramChannel: "",
    telegramBot: "",
    currency: "RUB",
    currencySymbol: "\u20BD",
    paymentProvider: "cloudpayments",
    authProviders: ["yandex", "magic_link"],
  },
  int: {
    region: "int",
    brand: "Viralex.ai",
    legalEntity: "Your Company",
    legalDetails: "Your registration / tax ID",
    legalAddress: "Your registered address",
    termsUrl: "/terms",
    privacyUrl: "/privacy",
    refundUrl: "/refund",
    cookiePolicyUrl: "/cookie-policy",
    supportEmail: "support@example.com",
    telegramChannel: "",
    telegramBot: "",
    currency: "EUR",
    currencySymbol: "\u20AC",
    paymentProvider: "stripe",
    authProviders: ["google", "magic_link"],
  },
};

/**
 * Region is determined by DOMAIN, not by language.
 * - viralex.ai → "int" (always, regardless of language)
 * - videorentgen.ru / localhost / anything else → "ru" (always, regardless of language)
 */
export function isViralexDomain(): boolean {
  return window.location.hostname.includes("viralex");
}

export function getRegion(): Region {
  return isViralexDomain() ? "int" : "ru";
}

export function getRegionConfig(): RegionConfig {
  return REGION_CONFIGS[getRegion()];
}

export function useRegion(): RegionConfig {
  return getRegionConfig();
}
