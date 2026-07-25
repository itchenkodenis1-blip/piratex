import { useDroppable } from "@dnd-kit/core";
import { SortableContext, verticalListSortingStrategy } from "@dnd-kit/sortable";
import type { PipelineItem, ProductionStatus } from "../../types";
import { KanbanCard } from "./KanbanCard";
import { COLUMN_CONFIG } from "./constants";

interface KanbanColumnProps {
  status: ProductionStatus;
  items: PipelineItem[];
  onCardClick: (item: PipelineItem) => void;
}

export function KanbanColumn({ status, items, onCardClick }: KanbanColumnProps) {
  const { setNodeRef, isOver } = useDroppable({ id: status });
  const config = COLUMN_CONFIG[status];

  return (
    <div
      ref={setNodeRef}
      className={`flex flex-col min-w-[260px] w-[260px] shrink-0 rounded-xl transition-colors ${
        isOver
          ? "bg-white/[0.06] border-2 border-violet-500/50"
          : "bg-white/[0.03] border-2 border-transparent"
      }`}
    >
      {/* Header */}
      <div className="flex items-center gap-2 px-3 py-2.5 border-b border-white/5">
        <span className="text-base">{config.emoji}</span>
        <span className="text-sm font-medium text-cream">{config.label}</span>
        <span className="ml-auto text-xs text-cream-muted bg-white/5 px-1.5 py-0.5 rounded-full min-w-[20px] text-center">
          {items.length}
        </span>
      </div>

      {/* Cards */}
      <SortableContext
        items={items.map((i) => i.script_id)}
        strategy={verticalListSortingStrategy}
      >
        <div className="flex flex-col gap-2 p-2 overflow-y-auto max-h-[calc(100vh-220px)] min-h-[80px]">
          {items.length === 0 && (
            <div className="text-xs text-cream-muted/50 text-center py-6">
              No items
            </div>
          )}
          {items.map((item) => (
            <KanbanCard key={item.script_id} item={item} onClick={onCardClick} />
          ))}
        </div>
      </SortableContext>
    </div>
  );
}
