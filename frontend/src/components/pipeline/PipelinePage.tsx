import { useCallback, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useAuth } from "../../hooks/useAuth";
import { usePipeline } from "../../hooks/usePipeline";
import { KanbanBoard } from "./KanbanBoard";
import { CalendarView } from "./CalendarView";
import { PipelineSidePanel } from "./PipelineSidePanel";
import type { PipelineItem } from "../../types";

type ViewMode = "kanban" | "calendar";

export function PipelinePage() {
  const { user } = useAuth();
  const { items, loading, error, changeStatus, refetch } = usePipeline(user?.id ?? null);
  const [searchParams, setSearchParams] = useSearchParams();
  const [selectedItem, setSelectedItem] = useState<PipelineItem | null>(null);

  const view = (searchParams.get("view") as ViewMode) || "kanban";

  const setView = useCallback(
    (v: ViewMode) => {
      const next = new URLSearchParams(searchParams);
      if (v === "kanban") next.delete("view");
      else next.set("view", v);
      setSearchParams(next, { replace: true });
    },
    [searchParams, setSearchParams],
  );

  const handleCardClick = useCallback((item: PipelineItem) => {
    setSelectedItem(item);
  }, []);

  const handlePanelClose = useCallback(() => {
    setSelectedItem(null);
  }, []);

  const handleStatusChanged = useCallback(() => {
    refetch();
  }, [refetch]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="text-cream-muted text-sm">Loading pipeline...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="text-red-400 text-sm">{error}</div>
      </div>
    );
  }

  return (
    <div>
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
        <h1 className="text-xl font-serif font-medium text-cream">
          Production Pipeline
        </h1>

        {/* View switcher */}
        <div className="flex items-center bg-white/[0.04] rounded-lg p-0.5">
          <button
            onClick={() => setView("kanban")}
            className={`text-sm px-3 py-1.5 rounded-md transition-colors ${
              view === "kanban"
                ? "bg-white/10 text-cream"
                : "text-cream-muted hover:text-cream"
            }`}
          >
            Kanban
          </button>
          <button
            onClick={() => setView("calendar")}
            className={`text-sm px-3 py-1.5 rounded-md transition-colors ${
              view === "calendar"
                ? "bg-white/10 text-cream"
                : "text-cream-muted hover:text-cream"
            }`}
          >
            Calendar
          </button>
        </div>
      </div>

      {/* Content */}
      {view === "kanban" ? (
        <KanbanBoard
          items={items}
          onChangeStatus={changeStatus}
          onCardClick={handleCardClick}
        />
      ) : (
        <CalendarView
          items={items}
          onCardClick={handleCardClick}
          onScheduleChanged={refetch}
        />
      )}

      {/* Side Panel */}
      {selectedItem && (
        <PipelineSidePanel
          item={selectedItem}
          onClose={handlePanelClose}
          onStatusChanged={handleStatusChanged}
        />
      )}
    </div>
  );
}
