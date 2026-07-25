import { useState, useMemo, useCallback, useRef } from "react";
import {
  DndContext,
  DragOverlay,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
  type DragStartEvent,
} from "@dnd-kit/core";
import type { PipelineItem, ProductionStatus } from "../../types";
import { KanbanColumn } from "./KanbanColumn";
import { KanbanCardOverlay } from "./KanbanCard";
import { RejectModal } from "./RejectModal";
import { VALID_TRANSITIONS } from "./constants";

const STATUSES: ProductionStatus[] = [
  "script_ready",
  "filming",
  "editing",
  "review",
  "rejected",
  "scheduled",
  "published",
];

interface KanbanBoardProps {
  items: PipelineItem[];
  onChangeStatus: (scriptId: string, newStatus: ProductionStatus, comment?: string) => Promise<void>;
  onCardClick?: (item: PipelineItem) => void;
}

export function KanbanBoard({ items, onChangeStatus, onCardClick }: KanbanBoardProps) {
  const [activeItem, setActiveItem] = useState<PipelineItem | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [rejectTarget, setRejectTarget] = useState<{ scriptId: string; fromStatus: string } | null>(null);

  const showToast = useCallback((msg: string) => {
    if (toastTimer.current) clearTimeout(toastTimer.current);
    setToast(msg);
    toastTimer.current = setTimeout(() => setToast(null), 3000);
  }, []);

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } })
  );

  const columns = useMemo(() => {
    const map: Record<ProductionStatus, PipelineItem[]> = {
      script_ready: [],
      filming: [],
      editing: [],
      review: [],
      rejected: [],
      scheduled: [],
      published: [],
    };
    for (const item of items) {
      if (item.production_status && map[item.production_status]) {
        map[item.production_status].push(item);
      }
    }
    return map;
  }, [items]);

  const handleDragStart = useCallback(
    (event: DragStartEvent) => {
      const item = items.find((i) => i.script_id === event.active.id);
      setActiveItem(item || null);
    },
    [items]
  );

  const handleDragEnd = useCallback(
    async (event: DragEndEvent) => {
      setActiveItem(null);
      const { active, over } = event;
      if (!over) return;

      const scriptId = active.id as string;

      // over.id can be a column status OR a card's script_id
      let targetStatus: ProductionStatus;
      if (STATUSES.includes(over.id as ProductionStatus)) {
        targetStatus = over.id as ProductionStatus;
      } else {
        // Dropped on a card — find which column that card belongs to
        const targetCard = items.find((i) => i.script_id === over.id);
        if (!targetCard?.production_status) return;
        targetStatus = targetCard.production_status;
      }

      const item = items.find((i) => i.script_id === scriptId);
      if (!item || !item.production_status) return;
      if (item.production_status === targetStatus) return;

      // Validate transition
      const allowed = VALID_TRANSITIONS[item.production_status] || [];
      if (!allowed.includes(targetStatus)) {
        showToast(
          `Cannot move from "${item.production_status}" to "${targetStatus}"`
        );
        return;
      }

      // Rejection requires a comment — open modal
      if (targetStatus === "rejected") {
        setRejectTarget({ scriptId, fromStatus: item.production_status });
        return;
      }

      try {
        await onChangeStatus(scriptId, targetStatus);
      } catch {
        showToast("Failed to change status");
      }
    },
    [items, onChangeStatus, showToast]
  );

  const handleRejectConfirm = useCallback(
    async (comment: string) => {
      if (!rejectTarget) return;
      try {
        await onChangeStatus(rejectTarget.scriptId, "rejected", comment);
      } catch {
        showToast("Failed to change status");
      }
      setRejectTarget(null);
    },
    [rejectTarget, onChangeStatus, showToast]
  );

  const handleRejectCancel = useCallback(() => {
    setRejectTarget(null);
  }, []);

  const handleDragCancel = useCallback(() => {
    setActiveItem(null);
  }, []);

  const handleCardClick = useCallback((item: PipelineItem) => {
    onCardClick?.(item);
  }, [onCardClick]);

  return (
    <div className="relative">
      <DndContext
        sensors={sensors}
        onDragStart={handleDragStart}
        onDragEnd={handleDragEnd}
        onDragCancel={handleDragCancel}
      >
        <div className="flex gap-3 overflow-x-auto pb-4 -mx-4 px-4 sm:-mx-0 sm:px-0">
          {STATUSES.map((status) => (
            <KanbanColumn
              key={status}
              status={status}
              items={columns[status]}
              onCardClick={handleCardClick}
            />
          ))}
        </div>

        <DragOverlay>
          {activeItem ? (
            <div className="rotate-2 scale-105">
              <KanbanCardOverlay item={activeItem} />
            </div>
          ) : null}
        </DragOverlay>
      </DndContext>

      {/* Toast notification */}
      {toast && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 bg-red-500/90 text-white text-sm px-4 py-2 rounded-lg shadow-lg backdrop-blur-sm animate-in fade-in slide-in-from-bottom-2">
          {toast}
        </div>
      )}

      <RejectModal
        isOpen={!!rejectTarget}
        onConfirm={handleRejectConfirm}
        onCancel={handleRejectCancel}
      />
    </div>
  );
}
