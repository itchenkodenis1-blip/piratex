import { useCallback, useMemo, useState } from "react";
import type { PipelineItem, ProductionStatus } from "../../types";
import { schedulePipeline } from "../../api/client";

const WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"];

const MONTHS = [
  "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
  "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь",
];

const STATUS_COLORS: Record<string, string> = {
  scheduled: "bg-blue-400",
  published: "bg-emerald-400",
  script_ready: "bg-zinc-400",
  filming: "bg-amber-400",
  editing: "bg-orange-400",
  review: "bg-purple-400",
  rejected: "bg-red-400",
};

interface CalendarViewProps {
  items: PipelineItem[];
  onCardClick?: (item: PipelineItem) => void;
  onScheduleChanged?: () => void;
}

interface DayCell {
  date: Date;
  isCurrentMonth: boolean;
  isToday: boolean;
  items: PipelineItem[];
}

function isSameDay(a: Date, b: Date): boolean {
  return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
}

function getCalendarDays(year: number, month: number, items: PipelineItem[]): DayCell[] {
  const today = new Date();
  const firstDay = new Date(year, month, 1);
  // Monday-based: 0=Mon .. 6=Sun
  let startDow = firstDay.getDay() - 1;
  if (startDow < 0) startDow = 6;

  const lastDay = new Date(year, month + 1, 0);
  const daysInMonth = lastDay.getDate();

  // Build item map: dateKey -> items
  const itemMap = new Map<string, PipelineItem[]>();
  for (const item of items) {
    const dateStr = item.production_status === "published"
      ? item.published_at
      : item.scheduled_publish_at;
    if (!dateStr) continue;
    const d = new Date(dateStr);
    const key = `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
    if (!itemMap.has(key)) itemMap.set(key, []);
    itemMap.get(key)!.push(item);
  }

  const cells: DayCell[] = [];

  // Previous month padding
  for (let i = startDow - 1; i >= 0; i--) {
    const d = new Date(year, month, -i);
    const key = `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
    cells.push({
      date: d,
      isCurrentMonth: false,
      isToday: isSameDay(d, today),
      items: itemMap.get(key) || [],
    });
  }

  // Current month
  for (let day = 1; day <= daysInMonth; day++) {
    const d = new Date(year, month, day);
    const key = `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
    cells.push({
      date: d,
      isCurrentMonth: true,
      isToday: isSameDay(d, today),
      items: itemMap.get(key) || [],
    });
  }

  // Next month padding to fill 6 rows
  const remaining = 42 - cells.length;
  for (let i = 1; i <= remaining; i++) {
    const d = new Date(year, month + 1, i);
    const key = `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
    cells.push({
      date: d,
      isCurrentMonth: false,
      isToday: isSameDay(d, today),
      items: itemMap.get(key) || [],
    });
  }

  return cells;
}

function MiniCard({ item, onClick }: { item: PipelineItem; onClick: () => void }) {
  const statusColor = STATUS_COLORS[item.production_status || ""] || "bg-zinc-500";
  const title = item.video_title || item.script?.slice(0, 40) || "Untitled";

  return (
    <button
      onClick={(e) => { e.stopPropagation(); onClick(); }}
      className="w-full flex items-center gap-1.5 px-1.5 py-0.5 rounded text-left text-[10px] leading-tight bg-white/[0.06] hover:bg-white/[0.12] transition-colors group/card"
      title={title}
    >
      <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${statusColor}`} />
      <span className="truncate text-cream-dim group-hover/card:text-cream transition-colors">
        {title.length > 20 ? title.slice(0, 20) + "\u2026" : title}
      </span>
    </button>
  );
}

export function CalendarView({ items, onCardClick, onScheduleChanged }: CalendarViewProps) {
  const today = new Date();
  const [year, setYear] = useState(today.getFullYear());
  const [month, setMonth] = useState(today.getMonth());
  const [dragItem, setDragItem] = useState<PipelineItem | null>(null);
  const [dragOverDate, setDragOverDate] = useState<string | null>(null);

  // Filter items that have a date
  const calendarItems = useMemo(
    () => items.filter((i) => i.scheduled_publish_at || i.published_at),
    [items],
  );

  const days = useMemo(
    () => getCalendarDays(year, month, calendarItems),
    [year, month, calendarItems],
  );

  const goToday = useCallback(() => {
    const now = new Date();
    setYear(now.getFullYear());
    setMonth(now.getMonth());
  }, []);

  const prev = useCallback(() => {
    setMonth((m) => {
      if (m === 0) { setYear((y) => y - 1); return 11; }
      return m - 1;
    });
  }, []);

  const next = useCallback(() => {
    setMonth((m) => {
      if (m === 11) { setYear((y) => y + 1); return 0; }
      return m + 1;
    });
  }, []);

  // Drag handlers
  const handleDragStart = useCallback((e: React.DragEvent, item: PipelineItem) => {
    if (item.production_status === "published") {
      e.preventDefault();
      return;
    }
    e.dataTransfer.setData("text/plain", item.script_id); // required for Firefox
    e.dataTransfer.effectAllowed = "move";
    setDragItem(item);
  }, []);

  const handleDragOver = useCallback((e: React.DragEvent, dateKey: string) => {
    e.preventDefault();
    setDragOverDate(dateKey);
  }, []);

  const handleDragLeave = useCallback(() => {
    setDragOverDate(null);
  }, []);

  const handleDrop = useCallback(async (e: React.DragEvent, targetDate: Date) => {
    e.preventDefault();
    setDragOverDate(null);
    if (!dragItem) return;

    const iso = new Date(targetDate.getFullYear(), targetDate.getMonth(), targetDate.getDate(), 12, 0, 0).toISOString();
    try {
      await schedulePipeline(dragItem.script_id, iso);
      onScheduleChanged?.();
    } catch {
      // silent
    }
    setDragItem(null);
  }, [dragItem, onScheduleChanged]);

  const handleDragEnd = useCallback(() => {
    setDragItem(null);
    setDragOverDate(null);
  }, []);

  // Count items without dates (for info)
  const unscheduledCount = items.filter(
    (i) => !i.scheduled_publish_at && !i.published_at && i.production_status !== "published"
  ).length;

  return (
    <div className="space-y-4">
      {/* Navigation */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <button
            onClick={prev}
            className="w-8 h-8 flex items-center justify-center rounded-lg bg-white/[0.06] hover:bg-white/[0.12] text-cream-dim hover:text-cream transition-colors"
          >
            <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polyline points="15 18 9 12 15 6" />
            </svg>
          </button>
          <h2 className="text-sm font-medium text-cream min-w-[160px] text-center">
            {MONTHS[month]} {year}
          </h2>
          <button
            onClick={next}
            className="w-8 h-8 flex items-center justify-center rounded-lg bg-white/[0.06] hover:bg-white/[0.12] text-cream-dim hover:text-cream transition-colors"
          >
            <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polyline points="9 18 15 12 9 6" />
            </svg>
          </button>
        </div>

        <div className="flex items-center gap-3">
          {unscheduledCount > 0 && (
            <span className="text-xs text-cream-muted">
              {unscheduledCount} без даты
            </span>
          )}
          <button
            onClick={goToday}
            className="text-xs px-3 py-1.5 rounded-lg bg-white/[0.06] hover:bg-white/[0.12] text-cream-dim hover:text-cream transition-colors"
          >
            Сегодня
          </button>
        </div>
      </div>

      {/* Calendar grid */}
      <div className="border border-border-subtle rounded-xl overflow-hidden">
        {/* Weekday headers */}
        <div className="grid grid-cols-7 bg-white/[0.03]">
          {WEEKDAYS.map((d) => (
            <div key={d} className="px-2 py-2 text-center text-[11px] font-medium text-cream-muted uppercase tracking-wider border-b border-border-subtle">
              {d}
            </div>
          ))}
        </div>

        {/* Day cells */}
        <div className="grid grid-cols-7">
          {days.map((cell, idx) => {
            const dateKey = `${cell.date.getFullYear()}-${cell.date.getMonth()}-${cell.date.getDate()}`;
            const isDropTarget = dragOverDate === dateKey;
            const rows = Math.ceil(days.length / 7);
            const isLastRow = idx >= (rows - 1) * 7;

            return (
              <div
                key={dateKey}
                className={`min-h-[80px] sm:min-h-[100px] border-b border-r border-border-subtle p-1 transition-colors ${
                  isLastRow ? "border-b-0" : ""
                } ${(idx + 1) % 7 === 0 ? "border-r-0" : ""} ${
                  cell.isCurrentMonth ? "" : "bg-white/[0.01]"
                } ${cell.isToday ? "bg-blue-500/[0.08]" : ""} ${
                  isDropTarget ? "bg-blue-500/[0.15] ring-1 ring-inset ring-blue-500/40" : ""
                }`}
                onDragOver={(e) => handleDragOver(e, dateKey)}
                onDragLeave={handleDragLeave}
                onDrop={(e) => handleDrop(e, cell.date)}
              >
                {/* Day number */}
                <div className={`text-xs font-medium mb-1 px-0.5 ${
                  cell.isToday
                    ? "text-blue-400"
                    : cell.isCurrentMonth
                      ? "text-cream-dim"
                      : "text-cream-muted/40"
                }`}>
                  {cell.date.getDate()}
                </div>

                {/* Items */}
                <div className="space-y-0.5">
                  {cell.items.slice(0, 3).map((item) => (
                    <div
                      key={item.script_id}
                      draggable={item.production_status !== "published"}
                      onDragStart={(e) => handleDragStart(e, item)}
                      onDragEnd={handleDragEnd}
                    >
                      <MiniCard
                        item={item}
                        onClick={() => onCardClick?.(item)}
                      />
                    </div>
                  ))}
                  {cell.items.length > 3 && (
                    <div className="text-[10px] text-cream-muted pl-1">
                      +{cell.items.length - 3}
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Legend */}
      <div className="flex flex-wrap items-center gap-3 text-[11px] text-cream-muted">
        {(["scheduled", "published", "filming", "editing", "review", "rejected"] as ProductionStatus[]).map((status) => (
          <div key={status} className="flex items-center gap-1.5">
            <span className={`w-2 h-2 rounded-full ${STATUS_COLORS[status]}`} />
            <span>{status}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
