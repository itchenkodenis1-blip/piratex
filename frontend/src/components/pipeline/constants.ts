import type { ProductionStatus } from "../../types";

export const COLUMN_CONFIG: Record<
  ProductionStatus,
  { label: string; emoji: string }
> = {
  script_ready: { label: "Script Ready", emoji: "📝" },
  filming: { label: "Filming", emoji: "🎥" },
  editing: { label: "Editing", emoji: "✂️" },
  review: { label: "Review", emoji: "🔍" },
  rejected: { label: "Rejected", emoji: "❌" },
  scheduled: { label: "Scheduled", emoji: "📅" },
  published: { label: "Published", emoji: "✅" },
};

export const VALID_TRANSITIONS: Record<string, string[]> = {
  script_ready: ["filming"],
  filming: ["editing"],
  editing: ["review"],
  review: ["scheduled", "rejected"],
  rejected: ["filming", "editing"],
  scheduled: ["published"],
  published: [],
};

export const STATUS_COLORS: Record<string, string> = {
  script_ready: "bg-gray-500/20 text-gray-300",
  filming: "bg-blue-500/20 text-blue-300",
  editing: "bg-purple-500/20 text-purple-300",
  review: "bg-yellow-500/20 text-yellow-300",
  rejected: "bg-red-500/20 text-red-300",
  scheduled: "bg-cyan-500/20 text-cyan-300",
  published: "bg-green-500/20 text-green-300",
};
