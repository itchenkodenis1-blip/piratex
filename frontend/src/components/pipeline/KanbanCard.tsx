import { useRef } from "react";
import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import type { PipelineItem } from "../../types";

interface KanbanCardProps {
  item: PipelineItem;
  onClick: (item: PipelineItem) => void;
}

export function KanbanCard({ item, onClick }: KanbanCardProps) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: item.script_id });

  // Track pointer movement to distinguish click from drag
  const pointerStart = useRef<{ x: number; y: number } | null>(null);

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  };

  const title = item.video_title || item.script?.slice(0, 60) || "Untitled";
  const scriptPreview = item.script
    ? item.script.length > 60
      ? item.script.slice(0, 60) + "..."
      : item.script
    : null;

  const isOverdue =
    item.due_date && new Date(item.due_date) < new Date();

  // Thumbnail via job frames endpoint (if available)
  const thumbnailUrl = item.job_id
    ? `/api/jobs/${item.job_id}/frames/0`
    : null;

  return (
    <div
      ref={setNodeRef}
      style={style}
      {...attributes}
      {...listeners}
      onPointerDown={(e) => {
        pointerStart.current = { x: e.clientX, y: e.clientY };
        listeners?.onPointerDown?.(e as never);
      }}
      onPointerUp={(e) => {
        if (pointerStart.current) {
          const dx = Math.abs(e.clientX - pointerStart.current.x);
          const dy = Math.abs(e.clientY - pointerStart.current.y);
          if (dx < 5 && dy < 5) {
            onClick(item);
          }
        }
        pointerStart.current = null;
      }}
      className="bg-[#1a1a2e] rounded-lg p-3 cursor-grab active:cursor-grabbing hover:bg-[#1f1f3a] transition-colors border border-white/5 hover:border-white/10"
    >
      {/* Thumbnail */}
      {thumbnailUrl && (
        <div className="w-full h-20 rounded-md overflow-hidden mb-2 bg-black/30">
          <img
            src={thumbnailUrl}
            alt=""
            className="w-full h-full object-cover"
            onError={(e) => {
              (e.target as HTMLImageElement).style.display = "none";
            }}
          />
        </div>
      )}

      {/* Title */}
      <p className="text-sm font-medium text-cream leading-tight line-clamp-2">
        {title}
      </p>

      {/* Script preview */}
      {scriptPreview && scriptPreview !== title && (
        <p className="text-xs text-cream-muted mt-1 line-clamp-1">
          {scriptPreview}
        </p>
      )}

      {/* Bottom row: assignee + due date */}
      <div className="flex items-center justify-between mt-2 gap-2">
        {item.assignee_id ? (
          <span className="text-[10px] text-cream-muted bg-white/5 px-1.5 py-0.5 rounded-full truncate max-w-[80px]">
            {item.assignee_id.slice(0, 8)}
          </span>
        ) : (
          <span />
        )}

        {item.due_date && (
          <span
            className={`text-[10px] px-1.5 py-0.5 rounded-full ${
              isOverdue
                ? "bg-red-500/20 text-red-400"
                : "bg-white/5 text-cream-muted"
            }`}
          >
            {new Date(item.due_date).toLocaleDateString("ru-RU", {
              day: "numeric",
              month: "short",
            })}
          </span>
        )}
      </div>
    </div>
  );
}

/** Presentational-only card for DragOverlay (no useSortable — avoids duplicate ID). */
export function KanbanCardOverlay({ item }: { item: PipelineItem }) {
  const title = item.video_title || item.script?.slice(0, 60) || "Untitled";
  const thumbnailUrl = item.job_id
    ? `/api/jobs/${item.job_id}/frames/0`
    : null;

  return (
    <div className="bg-[#1a1a2e] rounded-lg p-3 border border-violet-500/40 shadow-xl shadow-black/50 w-[244px]">
      {thumbnailUrl && (
        <div className="w-full h-20 rounded-md overflow-hidden mb-2 bg-black/30">
          <img src={thumbnailUrl} alt="" className="w-full h-full object-cover" />
        </div>
      )}
      <p className="text-sm font-medium text-cream leading-tight line-clamp-2">{title}</p>
    </div>
  );
}
