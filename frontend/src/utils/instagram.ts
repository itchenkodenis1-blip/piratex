/**
 * Extracts an Instagram username from various input formats:
 * - "username" / "@username"
 * - "instagram.com/username"
 * - "https://www.instagram.com/username"
 * - "https://instagram.com/username/reels/"
 * - "https://www.instagram.com/reel/ABC123/" (no username — returns "")
 *
 * Returns the cleaned lowercase username, or empty string if unparseable.
 */

const RESERVED_PATHS = new Set([
  "reel", "reels", "stories", "p", "explore", "accounts",
  "direct", "tv", "live", "tags", "locations", "about",
]);

export function extractInstagramUsername(input: string): string {
  const trimmed = input.trim();
  if (!trimmed) return "";

  // Try to extract from URL-like patterns (with or without protocol)
  const urlMatch = trimmed.match(
    /(?:https?:\/\/)?(?:www\.)?instagram\.com\/([A-Za-z0-9_.]+)/i
  );
  if (urlMatch) {
    const segment = urlMatch[1].toLowerCase();
    // Skip reserved Instagram paths like /reel/, /p/, /stories/ — these aren't usernames
    if (RESERVED_PATHS.has(segment)) return "";
    return segment;
  }

  // Strip leading @ and return as username
  const cleaned = trimmed.replace(/^@/, "");

  // Instagram usernames: alphanumeric + dots + underscores, max 30 chars
  if (/^[A-Za-z0-9_.]{1,30}$/.test(cleaned)) {
    return cleaned.toLowerCase();
  }

  return "";
}
