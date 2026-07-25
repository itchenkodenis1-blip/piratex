import { useCallback, useEffect, useState } from "react";
import type {
  PipelineItem,
  PipelineAsset,
  PipelineComment,
  PipelineHistoryEntry,
  ProductionStatus,
} from "../../types";
import {
  getPipelineDetail,
  getPipelineAssets,
  deletePipelineAsset,
  getAssetDownloadUrl,
  addPipelineComment,
  getPipelineComments,
  changePipelineStatus,
  assignPipeline,
  schedulePipeline,
  setDueDate as apiSetDueDate,
} from "../../api/client";
import { COLUMN_CONFIG, VALID_TRANSITIONS, STATUS_COLORS } from "./constants";
import { FileUpload } from "./FileUpload";
import { CommentThread } from "./CommentThread";
import { RejectModal } from "./RejectModal";

type TabId = "details" | "files" | "comments" | "history";

interface PipelineSidePanelProps {
  item: PipelineItem;
  onClose: () => void;
  onStatusChanged: () => void;
}

export function PipelineSidePanel({ item, onClose, onStatusChanged }: PipelineSidePanelProps) {
  const [tab, setTab] = useState<TabId>("details");
  const [assets, setAssets] = useState<PipelineAsset[]>([]);
  const [comments, setComments] = useState<PipelineComment[]>([]);
  const [history, setHistory] = useState<PipelineHistoryEntry[]>([]);
  const [loadingDetail, setLoadingDetail] = useState(true);
  const [currentItem, setCurrentItem] = useState<PipelineItem>(item);

  // Local editable state
  const [assigneeId, setAssigneeId] = useState(item.assignee_id || "");
  const [dueDate, setDueDate] = useState(item.due_date?.slice(0, 10) || "");
  const [scheduledAt, setScheduledAt] = useState(
    item.scheduled_publish_at?.slice(0, 16) || "",
  );

  // Sync local state when item prop changes (e.g. via WebSocket after drag)
  useEffect(() => {
    setAssigneeId(item.assignee_id || "");
    setDueDate(item.due_date ? item.due_date.slice(0, 10) : "");
    setScheduledAt(item.scheduled_publish_at ? item.scheduled_publish_at.slice(0, 16) : "");
  }, [item.script_id, item.assignee_id, item.due_date, item.scheduled_publish_at]);

  const [loadError, setLoadError] = useState<string | null>(null);
  const [showRejectModal, setShowRejectModal] = useState(false);

  // Load full detail
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const detail = await getPipelineDetail(item.script_id);
        if (cancelled) return;
        setCurrentItem(detail.item);
        setAssets(detail.assets);
        setComments(detail.comments);
        setHistory(detail.history);
        setAssigneeId(detail.item.assignee_id || "");
        setDueDate(detail.item.due_date?.slice(0, 10) || "");
        setScheduledAt(detail.item.scheduled_publish_at?.slice(0, 16) || "");
      } catch {
        if (!cancelled) setLoadError("Failed to load details");
      } finally {
        if (!cancelled) setLoadingDetail(false);
      }
    })();
    return () => { cancelled = true; };
  }, [item.script_id]);

  // Close on Escape (skip if RejectModal is open — it handles its own Escape)
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !showRejectModal) onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose, showRejectModal]);

  // Lock body scroll while panel is open
  useEffect(() => {
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = ""; };
  }, []);

  // Next status action
  const nextStatuses = currentItem.production_status
    ? VALID_TRANSITIONS[currentItem.production_status] || []
    : [];

  const handleNextStatus = useCallback(
    async (targetStatus: ProductionStatus) => {
      if (targetStatus === "rejected") {
        setShowRejectModal(true);
        return;
      }
      try {
        await changePipelineStatus(item.script_id, targetStatus);
        onStatusChanged();
        onClose();
      } catch {
        // stay open
      }
    },
    [item.script_id, onStatusChanged, onClose],
  );

  const handleRejectConfirm = useCallback(
    async (comment: string) => {
      setShowRejectModal(false);
      try {
        await changePipelineStatus(item.script_id, "rejected", comment);
        onStatusChanged();
        onClose();
      } catch {
        // stay open
      }
    },
    [item.script_id, onStatusChanged, onClose],
  );

  // Assign
  const handleAssign = useCallback(async () => {
    try {
      await assignPipeline(item.script_id, assigneeId || null);
      onStatusChanged();
    } catch {
      // noop
    }
  }, [item.script_id, assigneeId, onStatusChanged]);

  // Schedule
  const handleSchedule = useCallback(async () => {
    try {
      await schedulePipeline(item.script_id, scheduledAt || null);
      onStatusChanged();
    } catch {
      // noop
    }
  }, [item.script_id, scheduledAt, onStatusChanged]);

  // Due date
  const handleDueDate = useCallback(async () => {
    try {
      await apiSetDueDate(item.script_id, dueDate || null);
      onStatusChanged();
    } catch {
      // noop
    }
  }, [item.script_id, dueDate, onStatusChanged]);

  // File uploaded
  const handleFileUploaded = useCallback((asset: PipelineAsset) => {
    setAssets((prev) => [asset, ...prev]);
  }, []);

  // File deleted
  const handleDeleteAsset = useCallback(
    async (assetId: string) => {
      try {
        await deletePipelineAsset(item.script_id, assetId);
        setAssets((prev) => prev.filter((a) => a.id !== assetId));
      } catch {
        // noop
      }
    },
    [item.script_id],
  );

  // Comment submitted
  const handleCommentSubmit = useCallback(
    async (text: string) => {
      try {
        const c = await addPipelineComment(item.script_id, text);
        setComments((prev) => [...prev, c]);
      } catch {
        // Error is swallowed — CommentThread keeps the text so user can retry
      }
    },
    [item.script_id],
  );

  // Refresh comments on tab switch
  useEffect(() => {
    if (tab === "comments") {
      getPipelineComments(item.script_id).then(setComments).catch(() => {});
    }
    if (tab === "files") {
      getPipelineAssets(item.script_id).then(setAssets).catch(() => {});
    }
  }, [tab, item.script_id]);

  const title = currentItem.video_title || currentItem.script?.slice(0, 60) || "Untitled";
  const status = currentItem.production_status;
  const statusConfig = status ? COLUMN_CONFIG[status] : null;
  const statusColor = status ? STATUS_COLORS[status] || "" : "";

  const tabs: { id: TabId; label: string }[] = [
    { id: "details", label: "Details" },
    { id: "files", label: "Files" },
    { id: "comments", label: "Comments" },
    { id: "history", label: "History" },
  ];

  const formatSize = (bytes: number | null) => {
    if (!bytes) return "";
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const formatDate = (dateStr: string) => {
    const d = new Date(dateStr);
    return (
      d.toLocaleDateString("ru-RU", { day: "numeric", month: "short" }) +
      " " +
      d.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" })
    );
  };

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/40 z-40"
        onClick={onClose}
      />

      {/* Panel */}
      <div className="fixed top-0 right-0 h-full w-full sm:w-[420px] bg-[#0f0f23] border-l border-white/10 z-50 shadow-2xl flex flex-col animate-in slide-in-from-right duration-200">
        {/* Header */}
        <div className="flex items-start gap-3 p-4 border-b border-white/5 shrink-0">
          <div className="flex-1 min-w-0">
            <h2 className="text-base font-medium text-cream leading-tight line-clamp-2">
              {title}
            </h2>
            {status && statusConfig && (
              <span
                className={`inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full mt-1.5 ${statusColor}`}
              >
                {statusConfig.emoji} {statusConfig.label}
              </span>
            )}
          </div>
          <button
            onClick={onClose}
            className="text-cream-muted hover:text-cream p-1 -mt-0.5 transition-colors"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M18 6L6 18M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-white/5 shrink-0">
          {tabs.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`flex-1 text-sm py-2.5 transition-colors relative ${
                tab === t.id
                  ? "text-cream"
                  : "text-cream-muted hover:text-cream/80"
              }`}
            >
              {t.label}
              {tab === t.id && (
                <div className="absolute bottom-0 left-2 right-2 h-0.5 bg-violet-500 rounded-full" />
              )}
            </button>
          ))}
        </div>

        {/* Tab content */}
        <div className="flex-1 overflow-y-auto p-4 min-h-0">
          {loadingDetail ? (
            <div className="flex items-center justify-center py-12 text-cream-muted text-sm">
              Loading...
            </div>
          ) : loadError ? (
            <div className="flex items-center justify-center py-12 text-red-400 text-sm">
              {loadError}
            </div>
          ) : (
            <>
              {tab === "details" && (
                <DetailsTab
                  item={currentItem}
                  assigneeId={assigneeId}
                  dueDate={dueDate}
                  scheduledAt={scheduledAt}
                  onAssigneeChange={setAssigneeId}
                  onDueDateChange={setDueDate}
                  onScheduledAtChange={setScheduledAt}
                  onAssign={handleAssign}
                  onDueDate={handleDueDate}
                  onSchedule={handleSchedule}
                  nextStatuses={nextStatuses}
                  onNextStatus={handleNextStatus}
                />
              )}

              {tab === "files" && (
                <FilesTab
                  scriptId={item.script_id}
                  assets={assets}
                  onUploaded={handleFileUploaded}
                  onDelete={handleDeleteAsset}
                  formatSize={formatSize}
                  formatDate={formatDate}
                />
              )}

              {tab === "comments" && (
                <CommentThread
                  comments={comments}
                  onSubmit={handleCommentSubmit}
                />
              )}

              {tab === "history" && (
                <HistoryTab history={history} formatDate={formatDate} />
              )}
            </>
          )}
        </div>
      </div>

      <RejectModal
        isOpen={showRejectModal}
        onConfirm={handleRejectConfirm}
        onCancel={() => setShowRejectModal(false)}
      />
    </>
  );
}

// ── Details Tab ──────────────────────────────────────────────────

function DetailsTab({
  item,
  assigneeId,
  dueDate,
  scheduledAt,
  onAssigneeChange,
  onDueDateChange,
  onScheduledAtChange,
  onAssign,
  onDueDate,
  onSchedule,
  nextStatuses,
  onNextStatus,
}: {
  item: PipelineItem;
  assigneeId: string;
  dueDate: string;
  scheduledAt: string;
  onAssigneeChange: (v: string) => void;
  onDueDateChange: (v: string) => void;
  onScheduledAtChange: (v: string) => void;
  onAssign: () => void;
  onDueDate: () => void;
  onSchedule: () => void;
  nextStatuses: string[];
  onNextStatus: (s: ProductionStatus) => void;
}) {
  return (
    <div className="space-y-4">
      {/* Script */}
      {item.script && (
        <div>
          <label className="text-xs text-cream-muted mb-1 block">Script</label>
          <textarea
            readOnly
            value={item.script}
            rows={6}
            className="w-full bg-white/[0.03] border border-white/10 rounded-lg px-3 py-2 text-sm text-cream resize-none focus:outline-none"
          />
        </div>
      )}

      {/* Description */}
      {item.description && (
        <div>
          <label className="text-xs text-cream-muted mb-1 block">Description</label>
          <p className="text-sm text-cream/80 bg-white/[0.03] border border-white/10 rounded-lg px-3 py-2">
            {item.description}
          </p>
        </div>
      )}

      {/* Editor instructions */}
      {item.editor_instructions && (
        <div>
          <label className="text-xs text-cream-muted mb-1 block">Editor Instructions</label>
          <p className="text-sm text-cream/80 bg-white/[0.03] border border-white/10 rounded-lg px-3 py-2 whitespace-pre-wrap">
            {item.editor_instructions}
          </p>
        </div>
      )}

      {/* Assignee */}
      <div>
        <label className="text-xs text-cream-muted mb-1 block">Assignee</label>
        <div className="flex gap-2">
          <input
            type="text"
            value={assigneeId}
            onChange={(e) => onAssigneeChange(e.target.value)}
            placeholder="User ID"
            className="flex-1 bg-white/[0.04] border border-white/10 rounded-lg px-3 py-1.5 text-sm text-cream placeholder:text-cream-muted/40 focus:outline-none focus:border-violet-500/50"
          />
          <button
            onClick={onAssign}
            className="px-3 py-1.5 bg-white/[0.06] hover:bg-white/10 text-sm text-cream rounded-lg transition-colors"
          >
            Set
          </button>
        </div>
      </div>

      {/* Due date */}
      <div>
        <label className="text-xs text-cream-muted mb-1 block">Due Date</label>
        <div className="flex gap-2">
          <input
            type="date"
            value={dueDate}
            onChange={(e) => onDueDateChange(e.target.value)}
            className="flex-1 bg-white/[0.04] border border-white/10 rounded-lg px-3 py-1.5 text-sm text-cream focus:outline-none focus:border-violet-500/50 [color-scheme:dark]"
          />
          <button
            onClick={onDueDate}
            className="px-3 py-1.5 bg-white/[0.06] hover:bg-white/10 text-sm text-cream rounded-lg transition-colors"
          >
            Set
          </button>
        </div>
      </div>

      {/* Scheduled publish at (only for scheduled status) */}
      {item.production_status === "scheduled" && (
        <div>
          <label className="text-xs text-cream-muted mb-1 block">
            Scheduled Publish At
          </label>
          <div className="flex gap-2">
            <input
              type="datetime-local"
              value={scheduledAt}
              onChange={(e) => onScheduledAtChange(e.target.value)}
              className="flex-1 bg-white/[0.04] border border-white/10 rounded-lg px-3 py-1.5 text-sm text-cream focus:outline-none focus:border-violet-500/50 [color-scheme:dark]"
            />
            <button
              onClick={onSchedule}
              className="px-3 py-1.5 bg-white/[0.06] hover:bg-white/10 text-sm text-cream rounded-lg transition-colors"
            >
              Set
            </button>
          </div>
        </div>
      )}

      {/* Original reel link */}
      {item.url && (
        <div>
          <label className="text-xs text-cream-muted mb-1 block">Original Reel</label>
          <a
            href={item.url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-sm text-violet-400 hover:text-violet-300 underline truncate block"
          >
            {item.url}
          </a>
        </div>
      )}

      {/* Next status buttons */}
      {nextStatuses.length > 0 && (
        <div className="pt-2 border-t border-white/5">
          <label className="text-xs text-cream-muted mb-2 block">
            Move to Next Stage
          </label>
          <div className="flex gap-2 flex-wrap">
            {nextStatuses.map((s) => {
              const config = COLUMN_CONFIG[s as ProductionStatus];
              return (
                <button
                  key={s}
                  onClick={() => onNextStatus(s as ProductionStatus)}
                  className="px-3 py-1.5 bg-violet-600 hover:bg-violet-500 text-white text-sm rounded-lg transition-colors"
                >
                  {config?.emoji} {config?.label || s}
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Files Tab ────────────────────────────────────────────────────

function FilesTab({
  scriptId,
  assets,
  onUploaded,
  onDelete,
  formatSize,
  formatDate,
}: {
  scriptId: string;
  assets: PipelineAsset[];
  onUploaded: (a: PipelineAsset) => void;
  onDelete: (id: string) => void;
  formatSize: (b: number | null) => string;
  formatDate: (d: string) => string;
}) {
  const [previewUrls, setPreviewUrls] = useState<Record<string, string>>({});
  const [loadingDownload, setLoadingDownload] = useState<string | null>(null);

  const isVideo = (fileType?: string | null) =>
    fileType?.startsWith("video/") ?? false;

  const handleDownload = useCallback(
    async (assetId: string) => {
      setLoadingDownload(assetId);
      try {
        const { download_url } = await getAssetDownloadUrl(scriptId, assetId);
        window.open(download_url, "_blank");
      } catch {
        // noop
      } finally {
        setLoadingDownload(null);
      }
    },
    [scriptId],
  );

  const handleTogglePreview = useCallback(
    async (assetId: string) => {
      if (previewUrls[assetId]) {
        setPreviewUrls((prev) => {
          const next = { ...prev };
          delete next[assetId];
          return next;
        });
        return;
      }
      try {
        const { download_url } = await getAssetDownloadUrl(scriptId, assetId);
        setPreviewUrls((prev) => ({ ...prev, [assetId]: download_url }));
      } catch {
        // noop
      }
    },
    [scriptId, previewUrls],
  );

  return (
    <div className="space-y-4">
      <FileUpload scriptId={scriptId} onUploaded={onUploaded} />

      {assets.length === 0 ? (
        <p className="text-sm text-cream-muted/50 text-center py-4">
          No files uploaded yet
        </p>
      ) : (
        <div className="space-y-2">
          {assets.map((a) => (
            <div key={a.id} className="bg-white/[0.03] rounded-lg overflow-hidden">
              <div className="flex items-center gap-3 p-3 group">
                {/* File icon */}
                <div className="w-8 h-8 rounded bg-white/5 flex items-center justify-center text-cream-muted shrink-0">
                  {isVideo(a.file_type) ? (
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <polygon points="5 3 19 12 5 21 5 3" />
                    </svg>
                  ) : (
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z" />
                      <polyline points="14 2 14 8 20 8" />
                    </svg>
                  )}
                </div>

                <div className="flex-1 min-w-0">
                  <button
                    onClick={() => handleDownload(a.id)}
                    className="text-sm text-cream hover:text-violet-300 truncate block text-left transition-colors max-w-full"
                    title="Download file"
                  >
                    {a.file_name}
                  </button>
                  <p className="text-[10px] text-cream-muted">
                    {formatSize(a.file_size)}
                    {a.file_size ? " · " : ""}
                    {formatDate(a.created_at)}
                  </p>
                </div>

                <div className="flex items-center gap-1">
                  {/* Preview toggle for video */}
                  {isVideo(a.file_type) && (
                    <button
                      onClick={() => handleTogglePreview(a.id)}
                      className="text-cream-muted hover:text-violet-400 p-1 transition-colors"
                      title={previewUrls[a.id] ? "Hide preview" : "Preview video"}
                    >
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        {previewUrls[a.id] ? (
                          <>
                            <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94" />
                            <path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19" />
                            <line x1="1" y1="1" x2="23" y2="23" />
                          </>
                        ) : (
                          <>
                            <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
                            <circle cx="12" cy="12" r="3" />
                          </>
                        )}
                      </svg>
                    </button>
                  )}

                  {/* Download button */}
                  <button
                    onClick={() => handleDownload(a.id)}
                    disabled={loadingDownload === a.id}
                    className="text-cream-muted hover:text-violet-400 p-1 transition-colors disabled:opacity-50"
                    title="Download"
                  >
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                      <polyline points="7 10 12 15 17 10" />
                      <line x1="12" y1="15" x2="12" y2="3" />
                    </svg>
                  </button>

                  {/* Delete button */}
                  <button
                    onClick={() => onDelete(a.id)}
                    className="opacity-0 group-hover:opacity-100 text-red-400 hover:text-red-300 p-1 transition-opacity"
                    title="Delete file"
                  >
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <polyline points="3 6 5 6 21 6" />
                      <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                    </svg>
                  </button>
                </div>
              </div>

              {/* Inline video preview */}
              {isVideo(a.file_type) && previewUrls[a.id] && (
                <div className="px-3 pb-3">
                  <video
                    src={previewUrls[a.id]}
                    controls
                    className="w-full rounded-lg max-h-[240px] bg-black"
                  />
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── History Tab ──────────────────────────────────────────────────

function HistoryTab({
  history,
  formatDate,
}: {
  history: PipelineHistoryEntry[];
  formatDate: (d: string) => string;
}) {
  // Newest first
  const sorted = [...history].reverse();

  if (sorted.length === 0) {
    return (
      <p className="text-sm text-cream-muted/50 text-center py-8">
        No history yet
      </p>
    );
  }

  return (
    <div className="space-y-0">
      {sorted.map((h, i) => {
        const fromConfig = h.from_status
          ? COLUMN_CONFIG[h.from_status as ProductionStatus]
          : null;
        const toConfig = COLUMN_CONFIG[h.to_status as ProductionStatus];

        return (
          <div key={i} className="relative pl-6 pb-4">
            {/* Timeline line */}
            {i < sorted.length - 1 && (
              <div className="absolute left-[9px] top-4 bottom-0 w-px bg-white/10" />
            )}
            {/* Dot */}
            <div className="absolute left-0 top-1 w-[18px] h-[18px] rounded-full bg-white/10 flex items-center justify-center">
              <div className="w-2 h-2 rounded-full bg-violet-500" />
            </div>

            <div>
              <div className="flex items-center gap-1.5 flex-wrap">
                {fromConfig && (
                  <>
                    <span className="text-xs text-cream-muted">
                      {fromConfig.emoji} {fromConfig.label}
                    </span>
                    <span className="text-xs text-cream-muted/40">&rarr;</span>
                  </>
                )}
                {toConfig && (
                  <span className="text-xs text-cream font-medium">
                    {toConfig.emoji} {toConfig.label}
                  </span>
                )}
              </div>

              <p className="text-[10px] text-cream-muted/60 mt-0.5">
                {h.triggered_by_name || h.triggered_by?.slice(0, 8) || "Unknown"} &middot;{" "}
                {formatDate(h.created_at)}
              </p>

              {h.comment && (
                <p className="text-xs text-cream/60 mt-1 bg-white/[0.03] rounded px-2 py-1">
                  {h.comment}
                </p>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
