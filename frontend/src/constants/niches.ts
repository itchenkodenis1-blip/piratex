/**
 * Central niche definitions for the frontend.
 * Keep in sync with backend/app/core/niches.py
 */

export const NICHE_GROUPS = {
  tech_ai: ["ai", "vibe-coding", "software-dev", "tech", "saas", "no-code", "cybersecurity", "science", "data-science"],
  business_money: ["business", "startups", "ecommerce", "finance", "investing", "crypto", "real-estate", "freelance", "legal"],
  marketing_growth: ["marketing", "personal-brand", "copywriting", "seo", "smm"],
  creative: ["design", "photography", "video-production", "music", "art", "writing", "dance", "crafts"],
  education_career: ["education", "career", "coaching", "languages", "self-development", "philosophy"],
  health_wellness: ["health", "fitness", "mental-health", "psychology", "sexology", "nutrition", "yoga", "medicine", "biohacking"],
  beauty_fashion: ["beauty", "fashion", "hair", "nails"],
  lifestyle: ["lifestyle", "travel", "food", "home-decor", "sustainability", "gardening", "productivity", "automotive", "outdoor", "immigration", "fishing"],
  family_relationships: ["parenting", "relationships", "family", "pregnancy", "wedding"],
  spirituality_esoteric: ["astrology", "tarot", "numerology", "energy-practices", "human-design", "religion", "spirituality"],
  entertainment: ["entertainment", "comedy", "memes", "gaming", "anime", "true-crime", "asmr", "books", "cinema"],
  sports: ["sports", "martial-arts", "extreme-sports", "esports"],
  pets_animals: ["pets", "dogs", "cats", "wildlife"],
  news_society: ["news", "politics", "economics", "history", "military"],
  other: ["other"],
} as const;

/** i18n keys for group labels */
export const NICHE_GROUP_LABELS: Record<string, string> = {
  tech_ai: "niche_group_tech_ai",
  business_money: "niche_group_business_money",
  marketing_growth: "niche_group_marketing_growth",
  creative: "niche_group_creative",
  education_career: "niche_group_education_career",
  health_wellness: "niche_group_health_wellness",
  beauty_fashion: "niche_group_beauty_fashion",
  lifestyle: "niche_group_lifestyle",
  family_relationships: "niche_group_family_relationships",
  spirituality_esoteric: "niche_group_spirituality_esoteric",
  entertainment: "niche_group_entertainment",
  sports: "niche_group_sports",
  pets_animals: "niche_group_pets_animals",
  news_society: "niche_group_news_society",
  other: "niche_group_other",
};

/** Flat list of all niche slugs */
export const NICHES = Object.values(NICHE_GROUPS).flat();

export type NicheSlug = (typeof NICHES)[number];
