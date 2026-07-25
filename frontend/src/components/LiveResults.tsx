import { Fragment, useEffect, useRef, useState } from "react";
import { getFrameUrl, updateJobFields } from "../api/client";
import { useTranslation } from "../i18n";
import type { Translations } from "../i18n/types";
import { SCENE_TYPE_COLORS } from "../constants/sceneTypes";
import type { LiveData } from "../hooks/useJobWebSocket";
import type { FrameAnalysis, ProgressUpdate } from "../types";
import { AdaptationSummary } from "./AdaptationSummary";
import { TelegramPromo } from "./TelegramPromo";

interface Props {
  jobId: string;
  liveData: LiveData;
  progress: ProgressUpdate | null;
}

function formatDuration(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

function formatNumber(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return n.toString();
}

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

function getPipelineSteps(t: Translations) {
  return [
    { key: "downloading", label: t.pipeline_download, icon: "↓" },
    { key: "extracting_audio", label: t.pipeline_audio, icon: "♪" },
    { key: "transcribing", label: t.pipeline_transcribe, icon: "T" },
    { key: "extracting_frames", label: t.pipeline_frames, icon: "▦" },
    { key: "analyzing_frames", label: t.pipeline_analyze, icon: "◉" },
    { key: "generating_summary", label: t.pipeline_summary, icon: "✎" },
  ];
}

/* ─── Animated wrapper: fades in when it mounts ─── */
function FadeIn({
  children,
  delay = 0,
  className = "",
}: {
  children: React.ReactNode;
  delay?: number;
  className?: string;
}) {
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    const t = setTimeout(() => setVisible(true), delay);
    return () => clearTimeout(t);
  }, [delay]);

  return (
    <div
      className={`transition-all duration-500 ${className} ${
        visible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-4"
      }`}
    >
      {children}
    </div>
  );
}

/* ─── Pulsing status badge ─── */
function StatusBadge({ progress }: { progress: ProgressUpdate }) {
  const { t } = useTranslation();
  const label = t[`status_${progress.status}` as keyof typeof t] || progress.status;
  const percent = Math.round(progress.progress * 100);
  const isFailed = progress.status === "failed";
  const isDone = progress.status === "completed";

  return (
    <div className="flex items-center justify-center gap-3">
      {!isDone && !isFailed && (
        <span className="relative flex h-3 w-3">
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cream opacity-75" />
          <span className="relative inline-flex rounded-full h-3 w-3 bg-cream-dim" />
        </span>
      )}
      <span className={`text-sm font-medium ${isFailed ? "text-red-400" : isDone ? "text-green-400" : "text-cream-dim"}`}>
        {label}
      </span>
      {!isDone && !isFailed && (
        <span className="text-xs text-cream-muted">{percent}%</span>
      )}
    </div>
  );
}

/* ─── Dramatic scan overlay — shown while a frame is being analyzed ─── */
function ScanOverlay({ label }: { label: string }) {
  return (
    <>
      {/* Dark vignette makes the bright scan line pop */}
      <div className="absolute inset-0 bg-gradient-to-b from-black/20 via-transparent to-black/30 pointer-events-none" />

      {/* Corner brackets — scanner / viewfinder aesthetic */}
      <div className="absolute top-2.5 left-2.5 w-5 h-5 border-l-2 border-t-2 border-cream/80 pointer-events-none" />
      <div className="absolute top-2.5 right-2.5 w-5 h-5 border-r-2 border-t-2 border-cream/80 pointer-events-none" />
      <div className="absolute bottom-9 left-2.5 w-5 h-5 border-l-2 border-b-2 border-cream/80 pointer-events-none" />
      <div className="absolute bottom-9 right-2.5 w-5 h-5 border-r-2 border-b-2 border-cream/80 pointer-events-none" />

      {/* Wide glow aura that travels with the scan */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div
          className="absolute left-0 right-0 h-12"
          style={{
            background: "linear-gradient(to bottom, transparent 0%, rgba(235,235,235,0.14) 50%, transparent 100%)",
            animation: "scanLine 2s ease-in-out infinite",
          }}
        />
      </div>

      {/* Main bright scan line with glow bloom */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div
          className="absolute left-0 right-0 h-[3px]"
          style={{
            background: "linear-gradient(90deg, transparent 0%, rgba(255,255,255,0.85) 25%, #fff 50%, rgba(255,255,255,0.85) 75%, transparent 100%)",
            boxShadow: "0 0 8px 3px rgba(255,255,255,0.6), 0 0 22px 7px rgba(235,235,235,0.22)",
            animation: "scanLine 2s ease-in-out infinite",
          }}
        />
      </div>

      {/* Analyzing badge — bright and prominent */}
      <div className="absolute bottom-2 left-1/2 -translate-x-1/2 pointer-events-none">
        <div className="flex items-center gap-1.5 px-2.5 py-1 bg-black/70 border border-cream/30 rounded-full backdrop-blur-sm">
          <span className="relative flex h-2 w-2">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cream opacity-85" />
            <span className="relative inline-flex rounded-full h-2 w-2 bg-cream" />
          </span>
          <span className="text-[10px] text-cream font-semibold tracking-widest uppercase">{label}</span>
        </div>
      </div>
    </>
  );
}

/* ─── Frame card with cascade entrance + scan effect ─── */
function LiveFrameCard({
  jobId,
  stub,
  analysis,
  entranceDelay = 0,
}: {
  jobId: string;
  stub: { frame_index: number; timestamp: number; timecode: string };
  analysis?: FrameAnalysis;
  entranceDelay?: number;
}) {
  const { t } = useTranslation();
  const [entered, setEntered] = useState(false);
  const [imageLoaded, setImageLoaded] = useState(false);
  const [analysisRevealed, setAnalysisRevealed] = useState(false);

  // Cascade entrance with delay
  useEffect(() => {
    const timer = setTimeout(() => setEntered(true), entranceDelay);
    return () => clearTimeout(timer);
  }, [entranceDelay]);

  // Smooth analysis text reveal
  useEffect(() => {
    if (analysis) {
      const timer = setTimeout(() => setAnalysisRevealed(true), 100);
      return () => clearTimeout(timer);
    }
  }, [analysis]);

  return (
    <div
      className={`transition-all duration-700 ease-out h-full ${
        entered
          ? "opacity-100 translate-y-0 scale-100"
          : "opacity-0 translate-y-8 scale-95"
      }`}
    >
      <div className="bg-surface border border-border-subtle rounded-2xl overflow-hidden h-full flex flex-col group hover:border-cream-muted/20 transition-colors">
        {/* Frame image */}
        <div className="relative overflow-hidden">
          <img
            src={getFrameUrl(jobId, stub.frame_index)}
            alt={`Frame ${stub.frame_index}`}
            className={`w-full aspect-[9/16] object-contain bg-black transition-all duration-700 ${
              imageLoaded ? "opacity-100 scale-100" : "opacity-0 scale-105"
            }`}
            loading="lazy"
            onLoad={() => setImageLoaded(true)}
          />
          {/* Timecode + scene type badges */}
          <div className="absolute top-2 left-2 flex gap-2">
            <span className="px-2 py-0.5 bg-black/70 text-cream text-xs rounded-full font-mono backdrop-blur-sm">
              {stub.timecode}
            </span>
            {analysis && (
              <span
                className={`px-2 py-0.5 text-xs rounded backdrop-blur-sm transition-all duration-500 ${
                  analysisRevealed ? "opacity-100 translate-x-0" : "opacity-0 -translate-x-2"
                } ${SCENE_TYPE_COLORS[analysis.scene_type] || SCENE_TYPE_COLORS.b_roll}`}
              >
                {t[`scene_${analysis.scene_type}` as keyof typeof t] || analysis.scene_type}
              </span>
            )}
          </div>
          {/* Frame number badge */}
          <div className="absolute top-2 right-2">
            <span className="px-1.5 py-0.5 bg-black/50 text-cream-muted text-[10px] rounded font-mono backdrop-blur-sm">
              #{stub.frame_index + 1}
            </span>
          </div>
          {/* Scan animation while awaiting analysis */}
          {!analysis && imageLoaded && <ScanOverlay label={t.frame_analyzing} />}
          {/* Analysis complete flash */}
          {analysis && !analysisRevealed && (
            <div className="absolute inset-0 bg-cream/10 animate-pulse" />
          )}
        </div>

        {/* Analysis text with reveal animation */}
        <div
          className={`p-3 space-y-2 flex-1 transition-all duration-700 ${
            analysisRevealed ? "opacity-100 max-h-96" : "opacity-0 max-h-0"
          } overflow-hidden`}
        >
          {analysis?.transcript_segment && (
            <div className="animate-[textReveal_0.5s_ease-out]">
              <p className="text-[10px] text-cream-muted uppercase tracking-wider">
                {t.frame_speech}
              </p>
              <p className="text-xs text-cream italic leading-relaxed">
                &ldquo;{analysis.transcript_segment}&rdquo;
              </p>
            </div>
          )}
          {analysis && analysis.screen_text.length > 0 && (
            <div className="animate-[textReveal_0.5s_ease-out_0.15s_both]">
              <p className="text-[10px] text-cream-muted uppercase tracking-wider">
                {t.frame_text_on_screen}
              </p>
              <p className="text-xs text-cream-dim">
                {analysis.screen_text.join(" | ")}
              </p>
            </div>
          )}
          {analysis && (
            <div className="animate-[textReveal_0.5s_ease-out_0.3s_both]">
              <p className="text-[10px] text-cream-muted uppercase tracking-wider">
                {t.frame_visual}
              </p>
              <p className="text-xs text-cream-muted leading-relaxed">
                {analysis.visual_description}
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

/* ─── Pipeline steps visualizer — magical edition ─── */
function PipelineProgress({ currentStatus }: { currentStatus: string | null }) {
  const { t } = useTranslation();
  const steps = getPipelineSteps(t);
  const currentIndex = currentStatus
    ? steps.findIndex((s) => s.key === currentStatus)
    : -1;

  return (
    <div className="w-full max-w-3xl mx-auto px-2 sm:px-4 pb-10">
      <div className="flex items-center">
        {steps.map((step, i) => {
          const isDone = currentIndex > i;
          const isActive = currentIndex === i;

          return (
            <Fragment key={step.key}>
              {/* ── Step node ── */}
              <div className="relative shrink-0">
                {/* Active: breathing glow rings (hidden on mobile for space) */}
                {isActive && (
                  <>
                    <div
                      className="hidden sm:block absolute rounded-full pointer-events-none"
                      style={{
                        inset: "-16px",
                        border: "1px solid rgba(235,235,235,0.12)",
                        animation: "stepperBreathe 3s ease-in-out infinite",
                      }}
                    />
                    <div
                      className="hidden sm:block absolute rounded-full pointer-events-none"
                      style={{
                        inset: "-9px",
                        background: "rgba(235,235,235,0.06)",
                        animation: "stepperBreathe 2.5s ease-in-out infinite 0.8s",
                      }}
                    />
                  </>
                )}

                {/* Active: orbiting particle (hidden on mobile) */}
                {isActive && (
                  <div className="hidden sm:block">
                    <div
                      className="absolute z-20 pointer-events-none"
                      style={{
                        width: "44px",
                        height: "44px",
                        animation: "stepperOrbit 3.5s linear infinite",
                      }}
                    >
                      <div
                        className="absolute rounded-full bg-cream-dim"
                        style={{
                          width: "5px",
                          height: "5px",
                          top: "-4px",
                          left: "50%",
                          transform: "translateX(-50%)",
                          boxShadow:
                            "0 0 6px 2px rgba(163,163,163,0.6), 0 0 14px 4px rgba(235,235,235,0.3)",
                        }}
                      />
                    </div>
                  </div>
                )}

                {/* Active: sparkle particles (hidden on mobile) */}
                {isActive && (
                  <div className="hidden sm:block absolute inset-0 z-20 pointer-events-none">
                    {[0, 1, 2, 3, 4, 5].map((j) => (
                      <div
                        key={j}
                        className="absolute rounded-full"
                        style={{
                          width: j % 2 === 0 ? "3px" : "2px",
                          height: j % 2 === 0 ? "3px" : "2px",
                          background: j % 3 === 0
                            ? "rgba(235,235,235,0.9)"
                            : "rgba(163,163,163,0.7)",
                          left: `${8 + j * 16}%`,
                          bottom: "50%",
                          animation: `stepperSparkle ${1.4 + j * 0.25}s ease-out infinite ${j * 0.28}s`,
                        }}
                      />
                    ))}
                  </div>
                )}

                {/* Completed: subtle ambient glow */}
                {isDone && (
                  <div
                    className="absolute rounded-full pointer-events-none"
                    style={{
                      inset: "-4px",
                      background: "radial-gradient(circle, rgba(235,235,235,0.1) 0%, transparent 70%)",
                    }}
                  />
                )}

                {/* Main circle */}
                <div
                  className={`relative w-9 h-9 sm:w-11 sm:h-11 rounded-full flex items-center justify-center text-xs sm:text-sm font-medium z-10 transition-all duration-700 ${
                    isDone
                      ? "bg-gradient-to-br from-cream/20 to-cream/5 text-cream border-2 border-cream/20"
                      : isActive
                        ? "bg-gradient-to-br from-cream to-cream-dim text-[#0C0C0C] border-2 border-cream/50"
                        : "bg-surface/80 text-cream-muted border-2 border-border-subtle"
                  }`}
                  style={{
                    boxShadow: isDone
                      ? "0 0 20px rgba(235,235,235,0.12), inset 0 1px 0 rgba(255,255,255,0.05)"
                      : isActive
                        ? "0 0 30px rgba(235,235,235,0.4), 0 0 60px rgba(235,235,235,0.15), 0 0 100px rgba(235,235,235,0.05), inset 0 1px 0 rgba(255,255,255,0.1)"
                        : "inset 0 1px 0 rgba(255,255,255,0.02)",
                  }}
                >
                  {isDone ? (
                    <svg
                      className="w-4 h-4"
                      fill="none"
                      viewBox="0 0 24 24"
                      stroke="currentColor"
                      strokeWidth={3}
                      style={{ animation: "stepperCheckBounce 0.5s cubic-bezier(0.175,0.885,0.32,1.275)" }}
                    >
                      <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                    </svg>
                  ) : (
                    <span className={isActive ? "drop-shadow-[0_0_6px_rgba(255,255,255,0.5)]" : ""}>
                      {step.icon}
                    </span>
                  )}
                </div>

                {/* Label */}
                <div
                  className="absolute top-full mt-2 sm:mt-3 left-1/2 -translate-x-1/2 w-14 sm:w-[90px]"
                >
                  <span
                    className={`block text-[9px] sm:text-[10px] text-center leading-tight transition-all duration-500 ${
                      isDone
                        ? "text-cream/60"
                        : isActive
                          ? "text-cream font-semibold"
                          : "text-cream-muted"
                    }`}
                    style={
                      isActive
                        ? { textShadow: "0 0 10px rgba(235,235,235,0.5)" }
                        : undefined
                    }
                  >
                    {step.label}
                  </span>
                </div>
              </div>

              {/* ── Connecting segment ── */}
              {i < steps.length - 1 && (
                <div className="flex-1 relative mx-1" style={{ height: "3px" }}>
                  {/* Background track */}
                  <div
                    className="absolute inset-0 rounded-full"
                    style={{ background: "rgba(39,39,42,0.35)" }}
                  />

                  {/* Completed: glowing beam with shimmer */}
                  {isDone && (
                    <div className="absolute inset-0 rounded-full overflow-hidden">
                      <div
                        className="absolute inset-0 rounded-full"
                        style={{
                          background:
                            "linear-gradient(90deg, rgba(235,235,235,0.45), rgba(163,163,163,0.55), rgba(235,235,235,0.45))",
                          boxShadow:
                            "0 0 8px rgba(235,235,235,0.3), 0 0 2px rgba(163,163,163,0.5)",
                        }}
                      />
                      {/* Shimmer sweep */}
                      <div
                        style={{
                          position: "absolute",
                          inset: 0,
                          background:
                            "linear-gradient(90deg, transparent 0%, rgba(255,255,255,0.2) 50%, transparent 100%)",
                          animation: "stepperShimmer 3s ease-in-out infinite",
                        }}
                      />
                    </div>
                  )}

                  {/* Active→next: gradient fade with glowing tip */}
                  {isActive && (
                    <>
                      <div
                        className="absolute left-0 top-0 bottom-0 rounded-full"
                        style={{
                          width: "35%",
                          background:
                            "linear-gradient(90deg, rgba(235,235,235,0.4) 0%, rgba(235,235,235,0.08) 80%, transparent 100%)",
                          boxShadow: "0 0 6px rgba(235,235,235,0.15)",
                        }}
                      />
                      {/* Pulsing glow tip */}
                      <div
                        className="absolute rounded-full bg-cream/40"
                        style={{
                          width: "7px",
                          height: "7px",
                          left: "35%",
                          top: "50%",
                          animation: "stepperTipPulse 1.8s ease-in-out infinite",
                          boxShadow: "0 0 8px rgba(235,235,235,0.5), 0 0 4px rgba(163,163,163,0.4)",
                        }}
                      />
                    </>
                  )}
                </div>
              )}
            </Fragment>
          );
        })}
      </div>
    </div>
  );
}

/* ─── Waiting animation before WS connects ─── */
function WaitingState() {
  const { t } = useTranslation();
  const steps = getPipelineSteps(t);
  const [dots, setDots] = useState("");

  useEffect(() => {
    const timer = setInterval(() => {
      setDots((prev) => (prev.length >= 3 ? "" : prev + "."));
    }, 500);
    return () => clearInterval(timer);
  }, []);

  return (
    <div className="text-center py-16 space-y-8">
      {/* Animated logo/spinner */}
      <div className="flex items-center justify-center">
        <div className="relative w-16 h-16">
          <div className="absolute inset-0 rounded-full border-2 border-cream/20 animate-[spin_3s_linear_infinite]" />
          <div className="absolute inset-1 rounded-full border-2 border-transparent border-t-cream animate-[spin_1.5s_linear_infinite]" />
          <div className="absolute inset-3 rounded-full border-2 border-transparent border-t-cream-dim animate-[spin_1s_linear_infinite_reverse]" />
          <div className="absolute inset-0 flex items-center justify-center">
            <span className="text-lg text-cream font-serif">R</span>
          </div>
        </div>
      </div>

      <div className="space-y-2">
        <p className="text-lg text-cream font-medium">
          {t.waiting_connecting}{dots}
        </p>
        <p className="text-sm text-cream-muted">
          {t.waiting_subtitle}
        </p>
      </div>

      {/* Skeleton steps preview */}
      <div className="w-full max-w-2xl mx-auto">
        <div className="grid grid-cols-3 sm:flex sm:items-center sm:justify-between gap-2 sm:gap-1">
          {steps.map((step, i) => (
            <div key={step.key} className="flex-1 flex flex-col items-center gap-2">
              <div
                className="w-8 h-8 rounded-full flex items-center justify-center text-xs font-mono bg-surface-light text-cream-muted border border-border-subtle animate-pulse"
                style={{ animationDelay: `${i * 150}ms` }}
              >
                {step.icon}
              </div>
              <span className="text-[10px] text-center leading-tight text-cream-muted">
                {step.label}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

/* ─── Script writing animation — shows during generating_summary ─── */
function ScriptWritingAnimation({ t }: { t: Translations }) {
  const blocks = [
    { label: t.script_writing_script, lines: 6, delay: 0 },
    { label: t.script_writing_description, lines: 3, delay: 800 },
    { label: t.script_writing_editor, lines: 4, delay: 1600 },
    { label: t.script_writing_strategy, lines: 5, delay: 2400 },
  ];

  return (
    <FadeIn>
      <section className="space-y-5">
        <div className="flex items-center gap-3">
          <div className="h-px flex-1 bg-gradient-to-r from-transparent via-cream-muted/30 to-transparent" />
          <h2
            className="text-sm font-medium text-cream uppercase tracking-widest shrink-0"
            style={{ animation: "pulse 2s ease-in-out infinite" }}
          >
            {t.script_writing_title}
          </h2>
          <div className="h-px flex-1 bg-gradient-to-r from-transparent via-cream-muted/30 to-transparent" />
        </div>

        <div className="grid gap-3 sm:gap-4 grid-cols-1 sm:grid-cols-2 lg:grid-cols-4">
          {blocks.map((block, bi) => (
            <div
              key={bi}
              className="bg-surface/80 border border-border-subtle rounded-2xl p-4 space-y-3 overflow-hidden"
              style={{
                animation: `fadeSlideUp 600ms ${block.delay}ms both`,
              }}
            >
              {/* Block label */}
              <div className="flex items-center gap-2">
                <div
                  className="w-1.5 h-1.5 rounded-full bg-cream"
                  style={{ animation: "pulse 1.5s ease-in-out infinite" }}
                />
                <span className="text-xs font-medium text-cream uppercase tracking-wide">
                  {block.label}
                </span>
              </div>

              {/* Skeleton lines with typewriter cascade */}
              <div className="space-y-2">
                {Array.from({ length: block.lines }).map((_, li) => {
                  const lineDelay = block.delay + 300 + li * 200;
                  const width = li === block.lines - 1 ? "60%" : `${75 + Math.random() * 25}%`;
                  return (
                    <div
                      key={li}
                      className="h-2.5 rounded-full overflow-hidden"
                      style={{
                        width,
                        animation: `fadeSlideUp 400ms ${lineDelay}ms both`,
                      }}
                    >
                      <div
                        className="h-full rounded-full bg-gradient-to-r from-border-subtle via-cream-muted/30 to-border-subtle"
                        style={{
                          backgroundSize: "200% 100%",
                          animation: `shimmer 1.5s ease-in-out infinite ${li * 100}ms`,
                        }}
                      />
                    </div>
                  );
                })}
              </div>
            </div>
          ))}
        </div>

        {/* Inline keyframes */}
        <style>{`
          @keyframes fadeSlideUp {
            from { opacity: 0; transform: translateY(12px); }
            to { opacity: 1; transform: translateY(0); }
          }
          @keyframes shimmer {
            0%, 100% { background-position: -200% 0; }
            50% { background-position: 200% 0; }
          }
        `}</style>
      </section>
    </FadeIn>
  );
}

/* ─── Main component ─── */
export function LiveResults({ jobId, liveData, progress }: Props) {
  const { t } = useTranslation();
  const summaryRef = useRef<HTMLDivElement>(null);
  const isProcessing = progress && progress.status !== "completed" && progress.status !== "failed";
  const [liveActiveHook, setLiveActiveHook] = useState(0);
  const [liveScript, setLiveScript] = useState<string | null>(null);
  const [liveDescription, setLiveDescription] = useState<string | null>(null);
  const [liveEditorInstructions, setLiveEditorInstructions] = useState<string | null>(null);

  // Sync liveScript with incoming summary
  useEffect(() => {
    if (liveData.summary && !liveScript) {
      setLiveScript(liveData.summary.script);
    }
  }, [liveData.summary, liveScript]);

  const isWritingScript = !liveData.summary && progress?.status === "generating_summary";

  // Auto-scroll to summary block when writing animation appears or summary arrives
  useEffect(() => {
    if (liveData.summary || liveData.strategy || isWritingScript) {
      summaryRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [liveData.summary, liveData.strategy, isWritingScript]);

  return (
    <div className="w-full max-w-6xl mx-auto space-y-10">
      {/* No WS data yet — show waiting animation */}
      {!progress && <WaitingState />}

      {/* Status badge */}
      {progress && <StatusBadge progress={progress} />}

      {/* Pipeline steps */}
      {isProcessing && <PipelineProgress currentStatus={progress.status} />}

      {/* Telegram promo — while user is waiting */}
      {isProcessing && <TelegramPromo variant="processing" />}

      {/* Metadata */}
      {liveData.metadata && (
        <FadeIn>
          <div className="text-center space-y-2">
            <div className="flex flex-wrap items-center justify-center gap-3 text-sm text-cream-dim">
              {liveData.metadata.platform && (
                <span className="px-3 py-1 bg-surface-light border border-border-subtle text-cream-dim rounded-full text-xs font-medium uppercase tracking-wide">
                  {liveData.metadata.platform}
                </span>
              )}
              {liveData.metadata.author && (
                <span className="text-cream">{liveData.metadata.author}</span>
              )}
              {liveData.metadata.duration != null && (
                <span className="font-mono">
                  {formatDuration(liveData.metadata.duration)}
                </span>
              )}
              {liveData.metadata.views != null && liveData.metadata.views > 0 && (
                <span>{formatNumber(liveData.metadata.views)} {t.results_views}</span>
              )}
              {liveData.metadata.likes != null && liveData.metadata.likes > 0 && (
                <span>{formatNumber(liveData.metadata.likes)} {t.results_likes}</span>
              )}
              {liveData.metadata.comments != null && liveData.metadata.comments > 0 && (
                <span>{formatNumber(liveData.metadata.comments)} {t.results_comments}</span>
              )}
            </div>
          </div>
        </FadeIn>
      )}

      {/* Script writing animation — visible during generation, above frames */}
      {!liveData.summary && progress?.status === "generating_summary" && (
        <div ref={summaryRef}>
          <ScriptWritingAnimation t={t} />
        </div>
      )}

      {/* Summary — the final result, above frames for immediate value */}
      {liveData.summary && (
        <FadeIn>
          <div ref={!isWritingScript ? summaryRef : undefined}>
            <section className="space-y-5">
              <div className="flex items-center gap-3">
                <div className="h-px flex-1 bg-gradient-to-r from-transparent via-cream-muted/30 to-transparent" />
                <h2 className="text-sm font-medium text-cream uppercase tracking-widest shrink-0">
                  {t.results_final}
                </h2>
                <div className="h-px flex-1 bg-gradient-to-r from-transparent via-cream-muted/30 to-transparent" />
              </div>

              <AdaptationSummary
                summary={{
                  ...liveData.summary,
                  script: liveScript ?? liveData.summary.script,
                  description: liveDescription ?? liveData.summary.description,
                  editor_instructions: liveEditorInstructions ?? liveData.summary.editor_instructions,
                }}
                strategy={liveData.strategy}
                activeHookIndex={liveActiveHook}
                onHookSwap={(idx, newScript) => {
                  setLiveActiveHook(idx);
                  setLiveScript(newScript);
                  if (jobId) {
                    updateJobFields(jobId, { script: newScript }).catch(() => {});
                  }
                }}
                jobId={jobId}
                onFieldRefined={(field, text) => {
                  if (field === "script") setLiveScript(text);
                  else if (field === "description") setLiveDescription(text);
                  else if (field === "editor_instructions") setLiveEditorInstructions(text);
                  if (jobId) {
                    updateJobFields(jobId, { [field]: text }).catch(() => {});
                  }
                }}
                onFieldSave={async (field, value) => {
                  if (field === "script") setLiveScript(value);
                  else if (field === "description") setLiveDescription(value);
                  else if (field === "editor_instructions") setLiveEditorInstructions(value);
                  if (jobId) {
                    await updateJobFields(jobId, { [field]: value });
                  }
                }}
              />
            </section>
          </div>
        </FadeIn>
      )}

      {/* Thumbnail phase — metadata arrived, frames incoming.
          Show thumbnail as a real scanning frame + skeleton placeholders. */}
      {liveData.metadata?.thumbnail && !liveData.frameStubs?.length && (
        <section className="space-y-5">
          <FadeIn>
            <div className="flex items-center gap-3">
              <div className="h-px flex-1 bg-gradient-to-r from-transparent via-cream-muted/30 to-transparent" />
              <h2 className="text-sm font-medium text-cream-muted uppercase tracking-widest shrink-0">
                {t.results_frame_breakdown}
              </h2>
              <div className="h-px flex-1 bg-gradient-to-r from-transparent via-cream-muted/30 to-transparent" />
            </div>
          </FadeIn>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3 sm:gap-4">
            {/* Thumbnail as frame #1 — scanning immediately on metadata arrival */}
            <FadeIn delay={80}>
              <div className="bg-surface border border-border-subtle rounded-2xl overflow-hidden">
                <div className="relative overflow-hidden">
                  <img
                    src={liveData.metadata.thumbnail}
                    alt="Frame 1"
                    className="w-full aspect-[9/16] object-cover"
                  />
                  <div className="absolute top-2 left-2">
                    <span className="px-2 py-0.5 bg-black/70 text-cream text-xs rounded-full font-mono backdrop-blur-sm">
                      00:00
                    </span>
                  </div>
                  <div className="absolute top-2 right-2">
                    <span className="px-1.5 py-0.5 bg-black/50 text-cream-muted text-[10px] rounded font-mono backdrop-blur-sm">
                      #1
                    </span>
                  </div>
                  <ScanOverlay label={t.frame_analyzing} />
                </div>
              </div>
            </FadeIn>
            {/* Skeleton placeholders for remaining frames */}
            {Array.from({ length: 7 }).map((_, i) => (
              <FadeIn key={i} delay={140 + i * 90}>
                <div className="bg-surface/40 border border-border-subtle/30 rounded-2xl overflow-hidden">
                  <div
                    className="w-full aspect-[9/16] animate-pulse"
                    style={{
                      background: "linear-gradient(160deg, rgba(39,39,42,0.6) 0%, rgba(24,24,27,0.4) 100%)",
                      animationDelay: `${i * 180}ms`,
                    }}
                  />
                </div>
              </FadeIn>
            ))}
          </div>
        </section>
      )}

      {/* Storyboard — the hero section, appears with cascade effect */}
      {liveData.frameStubs && liveData.frameStubs.length > 0 && (
        <section className="space-y-5">
          <FadeIn>
            <div className="flex items-center gap-3">
              <div className="h-px flex-1 bg-gradient-to-r from-transparent via-cream-muted/30 to-transparent" />
              <h2 className="text-sm font-medium text-cream-muted uppercase tracking-widest shrink-0">
                {t.results_frame_breakdown} &middot; {liveData.frameStubs.length}
              </h2>
              <div className="h-px flex-1 bg-gradient-to-r from-transparent via-cream-muted/30 to-transparent" />
            </div>
          </FadeIn>

          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3 sm:gap-4">
            {liveData.frameStubs.map((stub, i) => (
              <LiveFrameCard
                key={stub.frame_index}
                jobId={jobId}
                stub={stub}
                analysis={liveData.analyzedFrames.get(stub.frame_index)}
                entranceDelay={Math.min(i * 40, 200)}
              />
            ))}
          </div>
        </section>
      )}

      {/* Transcript — appears after transcription */}
      {liveData.transcript && liveData.transcript.length > 0 && (
        <FadeIn>
          <section className="space-y-5">
            <div className="flex items-center gap-3">
              <div className="h-px flex-1 bg-gradient-to-r from-transparent via-border-subtle to-transparent" />
              <h2 className="text-sm font-medium text-cream-muted uppercase tracking-widest shrink-0">
                {t.results_transcript}
              </h2>
              <div className="h-px flex-1 bg-gradient-to-r from-transparent via-border-subtle to-transparent" />
            </div>

            <div className="bg-surface border border-border-subtle rounded-2xl p-3 sm:p-5 space-y-1.5 max-h-64 overflow-y-auto">
              {liveData.transcript.map((seg, i) => (
                <FadeIn key={i} delay={i * 60}>
                  <div className="flex gap-3 text-sm leading-relaxed">
                    <span className="text-cream-muted font-mono shrink-0 select-none w-10 text-right">
                      {formatTime(seg.start)}
                    </span>
                    <span className="text-cream-dim">{seg.text}</span>
                  </div>
                </FadeIn>
              ))}
            </div>
          </section>
        </FadeIn>
      )}

    </div>
  );
}
