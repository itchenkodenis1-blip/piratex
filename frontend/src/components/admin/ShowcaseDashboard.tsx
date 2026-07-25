import { useCallback, useEffect, useMemo, useRef, useState } from "react";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface ShowcaseDayStats {
  date: string;
  new_users: number;
  revenue_rub_kopecks: number;
  revenue_eur_cents: number;
  analyses: number;
}

interface ShowcasePlatformStat {
  platform: string;
  total: number;
  completed: number;
  failed: number;
  success_rate: number;
}

interface ShowcaseActiveJob {
  job_id: string;
  status: string;
  progress: number;
  video_platform: string | null;
  video_author: string | null;
  video_title: string | null;
  source: string | null;
  masked_email: string | null;
  created_at: string;
}

interface ShowcaseHeatmapCell {
  weekday: number;
  hour: number;
  count: number;
}

interface ShowcaseStats {
  total_registered: number;
  total_paid: number;
  conversion_pct: number;
  free_users: number;
  start_users: number;
  pro_users: number;
  unlimited_users: number;
  total_rub_kopecks: number;
  total_eur_cents: number;
  total_analyses: number;
  analyses_today: number;
  avg_rating: number | null;
  total_ratings: number;
  unread_ratings: number;
  unread_support: number;
  daily: ShowcaseDayStats[];
  launched_at: string | null;
  // Job stats
  jobs_completed: number;
  jobs_failed: number;
  jobs_running: number;
  jobs_success_rate: number;
  platform_stats: ShowcasePlatformStat[];
  avg_processing_seconds: number | null;
  fastest_today_seconds: number | null;
  jobs_per_hour: number;
  active_jobs: ShowcaseActiveJob[];
  activity_heatmap: ShowcaseHeatmapCell[];
  // Trend monitoring
  tracked_authors: number;
  total_trends_found: number;
  trends_currently_hot: number;
  avg_trends_per_author: number;
}

type ShowcaseEventType = "registration" | "analysis" | "payment" | "rating" | "job_status";

interface ShowcaseEvent {
  type: ShowcaseEventType;
  ts: string;
  tier?: string;
  rating?: string;
  has_comment?: string;
  user_id?: string;
  is_update?: string;
  masked_email?: string;
  // payment fields
  amount?: string;
  currency?: string;
  // job_status fields
  job_id?: string;
  old_status?: string;
  new_status?: string;
  progress?: string;
  video_platform?: string;
  video_author?: string;
  video_title?: string;
  source?: string;
  error?: string;
  id: string; // client-generated for React keys
}

// Pipeline job (tracked on frontend)
interface PipelineJob {
  job_id: string;
  status: string;
  progress: number;
  video_platform: string | null;
  video_author: string | null;
  video_title: string | null;
  source: string | null;
  masked_email: string | null;
  created_at: string;
  completedAt?: number; // timestamp for fade-out delay
  failed?: boolean;
}

// ---------------------------------------------------------------------------
// Job pipeline stages
// ---------------------------------------------------------------------------

const PIPELINE_STAGES = [
  { key: "pending", label: "Queue", icon: "⏳" },
  { key: "downloading", label: "Download", icon: "⬇" },
  { key: "extracting_audio", label: "Audio", icon: "♫" },
  { key: "transcribing", label: "Transcript", icon: "✍" },
  { key: "extracting_frames", label: "Frames", icon: "▣" },
  { key: "analyzing_frames", label: "AI Vision", icon: "\u{1F441}" },
  { key: "generating_summary", label: "Generate", icon: "✨" },
  { key: "completed", label: "Done", icon: "✔" },
] as const;

const STAGE_INDEX: Record<string, number> = {};
PIPELINE_STAGES.forEach((s, i) => (STAGE_INDEX[s.key] = i));

// ---------------------------------------------------------------------------
// Platform config
// ---------------------------------------------------------------------------

const PLATFORM_CONFIG: Record<string, { icon: string; color: string; label: string }> = {
  instagram: { icon: "\u{1F4F7}", color: "#E1306C", label: "Instagram" },
  tiktok: { icon: "\u{1F3B5}", color: "#00F2EA", label: "TikTok" },
  youtube: { icon: "\u{1F534}", color: "#FF0000", label: "YouTube" },
  unknown: { icon: "\u{1F30D}", color: "#6B7280", label: "Other" },
};

// ---------------------------------------------------------------------------
// Web Audio — synthesised sounds
// ---------------------------------------------------------------------------

let _audioCtx: AudioContext | null = null;
function getAudioCtx(): AudioContext {
  if (!_audioCtx) _audioCtx = new AudioContext();
  return _audioCtx;
}

function playChime() {
  const ctx = getAudioCtx();
  const now = ctx.currentTime;

  // Duolingo-style "pop welcome" — bouncy ascending triple note
  const notes = [440, 554.37, 659.25]; // A4 → C#5 → E5 (happy major triad)
  notes.forEach((freq, i) => {
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = "sine";
    osc.frequency.value = freq;
    const t = now + i * 0.08;
    gain.gain.setValueAtTime(0, t);
    gain.gain.linearRampToValueAtTime(0.2, t + 0.02); // quick attack (pop)
    gain.gain.exponentialRampToValueAtTime(0.001, t + 0.35);
    osc.connect(gain).connect(ctx.destination);
    osc.start(t);
    osc.stop(t + 0.35);
  });

  // Subtle "boop" percussion underneath
  const boop = ctx.createOscillator();
  const boopGain = ctx.createGain();
  boop.type = "sine";
  boop.frequency.setValueAtTime(300, now);
  boop.frequency.exponentialRampToValueAtTime(80, now + 0.08);
  boopGain.gain.setValueAtTime(0.12, now);
  boopGain.gain.exponentialRampToValueAtTime(0.001, now + 0.1);
  boop.connect(boopGain).connect(ctx.destination);
  boop.start(now);
  boop.stop(now + 0.1);
}

function playWhoosh() {
  const ctx = getAudioCtx();
  const now = ctx.currentTime;
  const duration = 0.35;

  // Filtered noise sweep
  const bufferSize = ctx.sampleRate * duration;
  const buffer = ctx.createBuffer(1, bufferSize, ctx.sampleRate);
  const data = buffer.getChannelData(0);
  for (let i = 0; i < bufferSize; i++) data[i] = Math.random() * 2 - 1;

  const source = ctx.createBufferSource();
  source.buffer = buffer;

  const filter = ctx.createBiquadFilter();
  filter.type = "bandpass";
  filter.frequency.setValueAtTime(400, now);
  filter.frequency.exponentialRampToValueAtTime(2000, now + duration * 0.4);
  filter.frequency.exponentialRampToValueAtTime(300, now + duration);
  filter.Q.value = 2;

  const gain = ctx.createGain();
  gain.gain.setValueAtTime(0, now);
  gain.gain.linearRampToValueAtTime(0.15, now + duration * 0.15);
  gain.gain.exponentialRampToValueAtTime(0.001, now + duration);

  source.connect(filter).connect(gain).connect(ctx.destination);
  source.start(now);
  source.stop(now + duration);
}

function playCashRegister() {
  const ctx = getAudioCtx();
  const now = ctx.currentTime;

  // Quick ascending "ka-ching" tones
  const freqs = [1200, 1500, 1800, 2400];
  freqs.forEach((freq, i) => {
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = "square";
    osc.frequency.value = freq;
    const t = now + i * 0.06;
    gain.gain.setValueAtTime(0.08, t);
    gain.gain.exponentialRampToValueAtTime(0.001, t + 0.12);
    osc.connect(gain).connect(ctx.destination);
    osc.start(t);
    osc.stop(t + 0.12);
  });

  // Final "ding" ring
  const ring = ctx.createOscillator();
  const ringGain = ctx.createGain();
  ring.type = "sine";
  ring.frequency.value = 3200;
  const ringStart = now + freqs.length * 0.06;
  ringGain.gain.setValueAtTime(0.12, ringStart);
  ringGain.gain.exponentialRampToValueAtTime(0.001, ringStart + 0.5);
  ring.connect(ringGain).connect(ctx.destination);
  ring.start(ringStart);
  ring.stop(ringStart + 0.5);
}

function playStarSound() {
  const ctx = getAudioCtx();
  const now = ctx.currentTime;

  // Short bright "ding" — two harmonics
  [1400, 2100].forEach((freq, i) => {
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = "sine";
    osc.frequency.value = freq;
    const t = now + i * 0.05;
    gain.gain.setValueAtTime(0.12, t);
    gain.gain.exponentialRampToValueAtTime(0.001, t + 0.4);
    osc.connect(gain).connect(ctx.destination);
    osc.start(t);
    osc.stop(t + 0.4);
  });
}

function playMilestoneSound() {
  const ctx = getAudioCtx();
  const now = ctx.currentTime;

  // Triumphant ascending arpeggio
  const notes = [523.25, 659.25, 783.99, 1046.5];
  notes.forEach((freq, i) => {
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = "sine";
    osc.frequency.value = freq;
    const t = now + i * 0.1;
    gain.gain.setValueAtTime(0.15, t);
    gain.gain.exponentialRampToValueAtTime(0.001, t + 0.8);
    osc.connect(gain).connect(ctx.destination);
    osc.start(t);
    osc.stop(t + 0.8);
  });
}

function playJobCompleteSound() {
  const ctx = getAudioCtx();
  const now = ctx.currentTime;
  // Soft "ping" — completed job
  const osc = ctx.createOscillator();
  const gain = ctx.createGain();
  osc.type = "sine";
  osc.frequency.value = 880;
  gain.gain.setValueAtTime(0.1, now);
  gain.gain.exponentialRampToValueAtTime(0.001, now + 0.3);
  osc.connect(gain).connect(ctx.destination);
  osc.start(now);
  osc.stop(now + 0.3);
}

const SOUND_MAP: Record<string, () => void> = {
  registration: playChime,
  analysis: playWhoosh,
  payment: playCashRegister,
  rating: playStarSound,
};

// ---------------------------------------------------------------------------
// Animated counter hook
// ---------------------------------------------------------------------------

function useAnimatedNumber(target: number, duration = 2000): number {
  const [current, setCurrent] = useState(0);
  const startTime = useRef<number | null>(null);
  const startValue = useRef(0);
  const raf = useRef(0);

  useEffect(() => {
    startValue.current = current;
    startTime.current = null;
    cancelAnimationFrame(raf.current);

    const step = (ts: number) => {
      if (!startTime.current) startTime.current = ts;
      const elapsed = ts - startTime.current;
      const progress = Math.min(elapsed / duration, 1);
      // Ease-out cubic
      const eased = 1 - Math.pow(1 - progress, 3);
      setCurrent(Math.round(startValue.current + (target - startValue.current) * eased));
      if (progress < 1) raf.current = requestAnimationFrame(step);
    };
    raf.current = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [target, duration]);

  return current;
}

// ---------------------------------------------------------------------------
// useShowcaseWebSocket hook
// ---------------------------------------------------------------------------

function useShowcaseWebSocket(
  onEvent: (evt: ShowcaseEvent) => void,
) {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const attempts = useRef(0);
  const onEventRef = useRef(onEvent);
  useEffect(() => { onEventRef.current = onEvent; }, [onEvent]);

  useEffect(() => {
    function connect() {
      const token = localStorage.getItem("token");
      if (!token) return;

      const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
      const ws = new WebSocket(
        `${protocol}//${window.location.host}/ws/admin/showcase?token=${encodeURIComponent(token)}`,
      );
      wsRef.current = ws;

      ws.onopen = () => {
        attempts.current = 0;
      };

      ws.onmessage = (e) => {
        try {
          const data = JSON.parse(e.data);
          const evt: ShowcaseEvent = {
            ...data,
            id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
          };
          onEventRef.current(evt);
        } catch {
          // ignore malformed
        }
      };

      ws.onclose = () => {
        if (attempts.current < 10) {
          const delay = Math.min(1000 * 2 ** attempts.current, 30000);
          attempts.current++;
          reconnectTimer.current = setTimeout(connect, delay);
        }
      };
    }

    connect();

    return () => {
      clearTimeout(reconnectTimer.current);
      if (wsRef.current) {
        wsRef.current.onclose = null;
        wsRef.current.close();
      }
    };
  }, []);
}

// ---------------------------------------------------------------------------
// Format helpers
// ---------------------------------------------------------------------------

function formatMoney(kopecks: number, currency: "RUB" | "EUR"): string {
  const amount = kopecks / 100;
  if (currency === "EUR") return `€${amount.toLocaleString("en-US", { minimumFractionDigits: 0 })}`;
  return `${amount.toLocaleString("ru-RU", { minimumFractionDigits: 0 })} ₽`;
}

function formatNumber(n: number): string {
  return n.toLocaleString("ru-RU");
}

function daysSinceLaunch(launched: string | null): number {
  if (!launched) return 0;
  const diff = Date.now() - new Date(launched).getTime();
  return Math.floor(diff / 86400000);
}

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return `${m}m ${s}s`;
}

// ---------------------------------------------------------------------------
// Confetti — lightweight canvas implementation
// ---------------------------------------------------------------------------

function launchConfetti(container: HTMLElement) {
  const canvas = document.createElement("canvas");
  canvas.style.cssText = "position:fixed;top:0;left:0;width:100vw;height:100vh;pointer-events:none;z-index:9999";
  container.appendChild(canvas);
  const ctx = canvas.getContext("2d")!;
  canvas.width = window.innerWidth;
  canvas.height = window.innerHeight;

  const colors = ["#A78BFA", "#7C3AED", "#34D399", "#FBBF24", "#F472B6", "#6366F1", "#E0E7FF"];
  const particles: {
    x: number; y: number; vx: number; vy: number;
    size: number; color: string; rotation: number; rotSpeed: number;
    life: number;
  }[] = [];

  for (let i = 0; i < 120; i++) {
    particles.push({
      x: canvas.width / 2 + (Math.random() - 0.5) * 200,
      y: canvas.height * 0.4,
      vx: (Math.random() - 0.5) * 12,
      vy: -Math.random() * 15 - 5,
      size: Math.random() * 6 + 3,
      color: colors[Math.floor(Math.random() * colors.length)],
      rotation: Math.random() * Math.PI * 2,
      rotSpeed: (Math.random() - 0.5) * 0.3,
      life: 1,
    });
  }

  let frame = 0;
  const maxFrames = 180;

  function animate() {
    if (frame >= maxFrames) {
      canvas.remove();
      return;
    }
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    for (const p of particles) {
      p.x += p.vx;
      p.y += p.vy;
      p.vy += 0.25; // gravity
      p.rotation += p.rotSpeed;
      p.life -= 0.008;
      if (p.life <= 0) continue;

      ctx.save();
      ctx.translate(p.x, p.y);
      ctx.rotate(p.rotation);
      ctx.globalAlpha = p.life;
      ctx.fillStyle = p.color;
      ctx.fillRect(-p.size / 2, -p.size / 2, p.size, p.size * 0.6);
      ctx.restore();
    }
    frame++;
    requestAnimationFrame(animate);
  }
  requestAnimationFrame(animate);
}

// ---------------------------------------------------------------------------
// Coin Rain — payment celebration animation
// ---------------------------------------------------------------------------

function launchCoinRain(container: HTMLElement, targetEl: HTMLElement | null) {
  const canvas = document.createElement("canvas");
  canvas.style.cssText = "position:fixed;top:0;left:0;width:100vw;height:100vh;pointer-events:none;z-index:9999";
  container.appendChild(canvas);
  const ctx = canvas.getContext("2d")!;
  canvas.width = window.innerWidth;
  canvas.height = window.innerHeight;

  // Target position (revenue number center)
  const targetRect = targetEl?.getBoundingClientRect();
  const targetX = targetRect ? targetRect.left + targetRect.width / 2 : canvas.width / 2;
  const targetY = targetRect ? targetRect.top + targetRect.height / 2 : canvas.height * 0.3;

  const COIN_COLORS = ["#FFD700", "#FFC107", "#F59E0B", "#FBBF24", "#EAB308", "#D4A017"];
  const COIN_COUNT = 35;
  const PHASE_RAIN = 60; // frames of freefall
  const PHASE_FLY = 50; // frames flying to target
  const TOTAL = PHASE_RAIN + PHASE_FLY + 15; // +15 for final pulse

  interface Coin {
    x: number; y: number; vx: number; vy: number;
    size: number; color: string; rotation: number; rotSpeed: number;
    phase: "rain" | "fly" | "done";
    flyStartX: number; flyStartY: number; flyFrame: number;
  }

  const coins: Coin[] = [];
  for (let i = 0; i < COIN_COUNT; i++) {
    coins.push({
      x: Math.random() * canvas.width,
      y: -20 - Math.random() * 200,
      vx: (Math.random() - 0.5) * 3,
      vy: Math.random() * 4 + 3,
      size: Math.random() * 10 + 8,
      color: COIN_COLORS[Math.floor(Math.random() * COIN_COLORS.length)],
      rotation: Math.random() * Math.PI * 2,
      rotSpeed: (Math.random() - 0.5) * 0.15,
      phase: "rain",
      flyStartX: 0, flyStartY: 0, flyFrame: 0,
    });
  }

  let frame = 0;
  let pulsed = false;

  function drawCoin(c: Coin, alpha: number) {
    ctx.save();
    ctx.translate(c.x, c.y);
    ctx.rotate(c.rotation);
    ctx.globalAlpha = alpha;

    // Coin body
    ctx.beginPath();
    ctx.ellipse(0, 0, c.size, c.size * 0.85, 0, 0, Math.PI * 2);
    ctx.fillStyle = c.color;
    ctx.fill();

    // Inner ring
    ctx.beginPath();
    ctx.ellipse(0, 0, c.size * 0.7, c.size * 0.6, 0, 0, Math.PI * 2);
    ctx.strokeStyle = "rgba(0,0,0,0.15)";
    ctx.lineWidth = 1;
    ctx.stroke();

    // Shine highlight
    ctx.beginPath();
    ctx.ellipse(-c.size * 0.2, -c.size * 0.2, c.size * 0.25, c.size * 0.2, -0.5, 0, Math.PI * 2);
    ctx.fillStyle = "rgba(255,255,255,0.4)";
    ctx.fill();

    // ₽ symbol
    ctx.fillStyle = "rgba(0,0,0,0.25)";
    ctx.font = `bold ${c.size * 0.8}px sans-serif`;
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText("₽", 0, 1);

    ctx.restore();
  }

  function animate() {
    if (frame >= TOTAL) {
      canvas.remove();
      return;
    }
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    for (const c of coins) {
      if (c.phase === "rain") {
        c.x += c.vx;
        c.y += c.vy;
        c.vy += 0.15; // gravity
        c.rotation += c.rotSpeed;

        // Transition to fly phase
        if (frame >= PHASE_RAIN) {
          c.phase = "fly";
          c.flyStartX = c.x;
          c.flyStartY = c.y;
          c.flyFrame = 0;
        }
        drawCoin(c, 1);
      } else if (c.phase === "fly") {
        c.flyFrame++;
        const t = Math.min(c.flyFrame / PHASE_FLY, 1);
        // Ease-in-out cubic
        const eased = t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
        c.x = c.flyStartX + (targetX - c.flyStartX) * eased;
        c.y = c.flyStartY + (targetY - c.flyStartY) * eased;
        c.rotation += c.rotSpeed * (1 - eased) * 3;
        // Shrink as approaching
        const scale = 1 - eased * 0.6;
        const oldSize = c.size;
        c.size = oldSize * scale;
        drawCoin(c, 1 - eased * 0.3);
        c.size = oldSize;

        if (t >= 1) {
          c.phase = "done";
        }
      }
      // "done" coins are invisible
    }

    // Pulse the target element when coins arrive
    if (!pulsed && frame >= PHASE_RAIN + PHASE_FLY - 5 && targetEl) {
      pulsed = true;
      targetEl.style.transition = "transform 0.15s ease-out, filter 0.15s ease-out";
      targetEl.style.transform = "scale(1.15)";
      targetEl.style.filter = "brightness(1.5) drop-shadow(0 0 20px rgba(52, 211, 153, 0.6))";
      setTimeout(() => {
        targetEl.style.transform = "scale(1)";
        targetEl.style.filter = "";
        setTimeout(() => {
          targetEl.style.transition = "";
        }, 200);
      }, 300);
    }

    frame++;
    requestAnimationFrame(animate);
  }
  requestAnimationFrame(animate);
}

// ---------------------------------------------------------------------------
// Buddy Run — Duolingo-style character on registration
// ---------------------------------------------------------------------------

function launchBuddyRun(container: HTMLElement, targetEl: HTMLElement | null) {
  const canvas = document.createElement("canvas");
  canvas.style.cssText = "position:fixed;top:0;left:0;width:100vw;height:100vh;pointer-events:none;z-index:9999";
  container.appendChild(canvas);
  const ctx = canvas.getContext("2d")!;
  canvas.width = window.innerWidth;
  canvas.height = window.innerHeight;

  const targetRect = targetEl?.getBoundingClientRect();
  const targetX = targetRect ? targetRect.left + targetRect.width / 2 : canvas.width / 2;
  const targetY = targetRect ? targetRect.top + targetRect.height / 2 : canvas.height * 0.25;

  // Random spawn direction: left, right, top, bottom, or corners
  const BUDDY_SIZE = 44;
  const side = Math.floor(Math.random() * 5); // 0=left 1=right 2=top 3=bottom-left 4=bottom-right
  let bx: number, by: number, dirX: number, dirY: number;
  const jumpZoneX = canvas.width * (0.3 + Math.random() * 0.2); // randomize jump trigger point
  const jumpZoneY = canvas.height * (0.3 + Math.random() * 0.2);

  switch (side) {
    case 0: // from left
      bx = -60; by = canvas.height * (0.35 + Math.random() * 0.3); dirX = 1; dirY = 0; break;
    case 1: // from right
      bx = canvas.width + 60; by = canvas.height * (0.35 + Math.random() * 0.3); dirX = -1; dirY = 0; break;
    case 2: // from top
      bx = canvas.width * (0.2 + Math.random() * 0.6); by = -60; dirX = 0; dirY = 1; break;
    case 3: // from bottom-left
      bx = -60; by = canvas.height + 60; dirX = 1; dirY = -1; break;
    default: // from bottom-right
      bx = canvas.width + 60; by = canvas.height + 60; dirX = -1; dirY = -1; break;
  }

  const runSpeed = 7 + Math.random() * 3;
  let phase: "run" | "fly" | "impact" | "done" = "run";
  let runCycle = 0;
  let flyFrame = 0;
  let flyStartX = 0;
  let flyStartY = 0;
  let impactFrame = 0;
  let pulsed = false;
  const flipX = dirX < 0 ? -1 : (dirX === 0 ? (bx > targetX ? -1 : 1) : 1);

  const particles: { x: number; y: number; vx: number; vy: number; life: number; color: string; size: number }[] = [];

  function drawBuddy(x: number, y: number, scale: number, legOffset: number) {
    ctx.save();
    ctx.translate(x, y);
    ctx.scale(scale * flipX, scale); // flipX mirrors for right-to-left

    const s = BUDDY_SIZE;

    // Shadow
    ctx.beginPath(); ctx.ellipse(0, s * 0.48, s * 0.3, s * 0.06, 0, 0, Math.PI * 2);
    ctx.fillStyle = "rgba(0,0,0,0.15)"; ctx.fill();
    // Legs
    ctx.fillStyle = "#6D28D9";
    ctx.beginPath(); ctx.ellipse(-s * 0.12, s * 0.35 + legOffset * 3, s * 0.08, s * 0.14, 0, 0, Math.PI * 2); ctx.fill();
    ctx.beginPath(); ctx.ellipse(s * 0.12, s * 0.35 - legOffset * 3, s * 0.08, s * 0.14, 0, 0, Math.PI * 2); ctx.fill();
    // Body
    ctx.beginPath(); ctx.ellipse(0, 0, s * 0.28, s * 0.35, 0, 0, Math.PI * 2);
    const bodyGrad = ctx.createRadialGradient(-s * 0.08, -s * 0.1, 0, 0, 0, s * 0.35);
    bodyGrad.addColorStop(0, "#A78BFA"); bodyGrad.addColorStop(0.6, "#8B5CF6"); bodyGrad.addColorStop(1, "#7C3AED");
    ctx.fillStyle = bodyGrad; ctx.fill();
    // Belly highlight
    ctx.beginPath(); ctx.ellipse(-s * 0.04, -s * 0.02, s * 0.15, s * 0.2, -0.2, 0, Math.PI * 2);
    ctx.fillStyle = "rgba(255,255,255,0.12)"; ctx.fill();
    // Arms
    ctx.fillStyle = "#7C3AED";
    ctx.save(); ctx.translate(-s * 0.28, -s * 0.05); ctx.rotate(-0.4 + legOffset * 0.8);
    ctx.beginPath(); ctx.ellipse(0, s * 0.1, s * 0.065, s * 0.15, 0, 0, Math.PI * 2); ctx.fill(); ctx.restore();
    ctx.save(); ctx.translate(s * 0.28, -s * 0.05); ctx.rotate(0.4 - legOffset * 0.8);
    ctx.beginPath(); ctx.ellipse(0, s * 0.1, s * 0.065, s * 0.15, 0, 0, Math.PI * 2); ctx.fill(); ctx.restore();
    // Eyes
    const eyeY = -s * 0.1;
    ctx.fillStyle = "#fff";
    ctx.beginPath(); ctx.ellipse(-s * 0.09, eyeY, s * 0.08, s * 0.09, 0, 0, Math.PI * 2); ctx.fill();
    ctx.beginPath(); ctx.ellipse(s * 0.09, eyeY, s * 0.08, s * 0.09, 0, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = "#1E1B4B";
    ctx.beginPath(); ctx.ellipse(-s * 0.06, eyeY, s * 0.04, s * 0.05, 0, 0, Math.PI * 2); ctx.fill();
    ctx.beginPath(); ctx.ellipse(s * 0.12, eyeY, s * 0.04, s * 0.05, 0, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = "#fff";
    ctx.beginPath(); ctx.arc(-s * 0.05, eyeY - s * 0.02, s * 0.02, 0, Math.PI * 2); ctx.fill();
    ctx.beginPath(); ctx.arc(s * 0.13, eyeY - s * 0.02, s * 0.02, 0, Math.PI * 2); ctx.fill();
    // Mouth
    ctx.strokeStyle = "#1E1B4B"; ctx.lineWidth = 2; ctx.lineCap = "round";
    ctx.beginPath(); ctx.arc(0, s * 0.05, s * 0.1, 0.15, Math.PI - 0.15); ctx.stroke();
    // Blush
    ctx.fillStyle = "rgba(244, 114, 182, 0.3)";
    ctx.beginPath(); ctx.ellipse(-s * 0.18, s * 0.02, s * 0.05, s * 0.035, 0, 0, Math.PI * 2); ctx.fill();
    ctx.beginPath(); ctx.ellipse(s * 0.18, s * 0.02, s * 0.05, s * 0.035, 0, 0, Math.PI * 2); ctx.fill();

    ctx.restore();
  }

  // How close to jump trigger?
  function reachedJumpZone(): boolean {
    if (dirX !== 0 && dirY === 0) return Math.abs(bx - jumpZoneX) < 30;
    if (dirX === 0) return Math.abs(by - jumpZoneY) < 30;
    // Diagonal: check distance to center region
    const dist = Math.hypot(bx - canvas.width / 2, by - canvas.height / 2);
    return dist < canvas.height * 0.3;
  }

  function animate() {
    if (phase === "done" && impactFrame > 40) { canvas.remove(); return; }
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    if (phase === "run") {
      bx += dirX * runSpeed;
      by += dirY * runSpeed;
      runCycle += 0.25;
      // Bounce while running (perpendicular to direction)
      const bounce = Math.abs(Math.sin(runCycle * 2)) * -6;
      const drawX = bx + (dirY !== 0 ? bounce : 0);
      const drawY = by + (dirX !== 0 ? bounce : 0);
      drawBuddy(drawX, drawY, 1, Math.sin(runCycle));

      if (reachedJumpZone()) {
        phase = "fly";
        flyStartX = bx;
        flyStartY = by;
        flyFrame = 0;
      }
    } else if (phase === "fly") {
      flyFrame++;
      const duration = 35;
      const t = Math.min(flyFrame / duration, 1);
      // Ease-in-out cubic
      const eased = t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
      bx = flyStartX + (targetX - flyStartX) * eased;
      by = flyStartY + (targetY - flyStartY) * eased;
      const scale = 1 - eased * 0.4;
      const rotation = eased * Math.PI * 2 * flipX;

      ctx.save();
      ctx.translate(bx, by);
      ctx.rotate(rotation);
      ctx.translate(-bx, -by);
      drawBuddy(bx, by, scale, 0);
      ctx.restore();

      // Speed lines (from direction of travel)
      if (t < 0.8) {
        ctx.strokeStyle = `rgba(167, 139, 250, ${0.4 * (1 - t)})`;
        ctx.lineWidth = 2;
        for (let i = 0; i < 3; i++) {
          const lx = bx - (targetX - flyStartX) * 0.08 * (i + 1);
          const ly = by - (targetY - flyStartY) * 0.08 * (i + 1) + (Math.random() - 0.5) * 15;
          ctx.beginPath(); ctx.moveTo(lx, ly); ctx.lineTo(lx - (targetX - flyStartX) * 0.03, ly + 5); ctx.stroke();
        }
      }

      if (t >= 1) {
        phase = "impact";
        impactFrame = 0;
        for (let i = 0; i < 20; i++) {
          const angle = (Math.PI * 2 * i) / 20 + Math.random() * 0.3;
          const speed = 3 + Math.random() * 6;
          particles.push({
            x: targetX, y: targetY,
            vx: Math.cos(angle) * speed, vy: Math.sin(angle) * speed,
            life: 1,
            color: ["#A78BFA", "#7C3AED", "#E0E7FF", "#C4B5FD", "#DDD6FE"][Math.floor(Math.random() * 5)],
            size: 3 + Math.random() * 5,
          });
        }
      }
    } else if (phase === "impact") {
      impactFrame++;

      if (impactFrame < 20) {
        const ringR = impactFrame * 8;
        const ringAlpha = 1 - impactFrame / 20;
        ctx.beginPath(); ctx.arc(targetX, targetY, ringR, 0, Math.PI * 2);
        ctx.strokeStyle = `rgba(167, 139, 250, ${ringAlpha * 0.5})`; ctx.lineWidth = 3; ctx.stroke();
        const glowGrad = ctx.createRadialGradient(targetX, targetY, 0, targetX, targetY, ringR);
        glowGrad.addColorStop(0, `rgba(167, 139, 250, ${ringAlpha * 0.15})`);
        glowGrad.addColorStop(1, "rgba(167, 139, 250, 0)");
        ctx.fillStyle = glowGrad; ctx.fill();
      }

      if (impactFrame < 25) {
        for (let i = 0; i < 4; i++) {
          const angle = (Math.PI * 2 * i) / 4 + impactFrame * 0.1;
          const dist = 20 + impactFrame * 3;
          drawStar(ctx, targetX + Math.cos(angle) * dist, targetY + Math.sin(angle) * dist, 4, 8, 4, `rgba(224, 231, 255, ${1 - impactFrame / 25})`);
        }
      }

      for (const p of particles) {
        p.x += p.vx; p.y += p.vy; p.vy += 0.2; p.life -= 0.025;
        if (p.life <= 0) continue;
        ctx.globalAlpha = p.life; ctx.fillStyle = p.color;
        ctx.beginPath(); ctx.arc(p.x, p.y, p.size * p.life, 0, Math.PI * 2); ctx.fill();
      }
      ctx.globalAlpha = 1;

      if (!pulsed && targetEl) {
        pulsed = true;
        targetEl.style.transition = "transform 0.12s cubic-bezier(0.34, 1.56, 0.64, 1), filter 0.12s ease-out";
        targetEl.style.transform = "scale(1.2)";
        targetEl.style.filter = "brightness(1.6) drop-shadow(0 0 25px rgba(167, 139, 250, 0.7))";
        setTimeout(() => {
          targetEl.style.transform = "scale(0.95)";
          targetEl.style.filter = "brightness(1.2) drop-shadow(0 0 10px rgba(167, 139, 250, 0.3))";
          setTimeout(() => {
            targetEl.style.transform = "scale(1)"; targetEl.style.filter = "";
            setTimeout(() => { targetEl.style.transition = ""; }, 200);
          }, 120);
        }, 150);
      }

      if (impactFrame > 40) phase = "done";
    }

    requestAnimationFrame(animate);
  }

  requestAnimationFrame(animate);
}

// Mini star helper for sparkle effects
function drawStar(
  ctx: CanvasRenderingContext2D,
  cx: number, cy: number,
  innerR: number, outerR: number,
  points: number,
  color: string,
) {
  ctx.save();
  ctx.fillStyle = color;
  ctx.beginPath();
  for (let i = 0; i < points * 2; i++) {
    const r = i % 2 === 0 ? outerR : innerR;
    const angle = (Math.PI * i) / points - Math.PI / 2;
    const x = cx + Math.cos(angle) * r;
    const y = cy + Math.sin(angle) * r;
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  }
  ctx.closePath();
  ctx.fill();
  ctx.restore();
}

// ---------------------------------------------------------------------------
// Sparkline — tiny area chart
// ---------------------------------------------------------------------------

function Sparkline({
  data,
  color = "#A78BFA",
  height = 64,
}: {
  data: number[];
  color?: string;
  height?: number;
}) {
  if (data.length === 0 || data.every((v) => v === 0)) {
    return <div style={{ height }} className="w-full" />;
  }

  const max = Math.max(...data, 1);
  const w = 300;
  const h = height;
  const padding = 2;

  const points = data.map((v, i) => ({
    x: padding + (i / (data.length - 1)) * (w - padding * 2),
    y: h - padding - (v / max) * (h - padding * 2),
  }));

  const linePath = points.map((p, i) => `${i === 0 ? "M" : "L"} ${p.x} ${p.y}`).join(" ");
  const areaPath = `${linePath} L ${points[points.length - 1].x} ${h} L ${points[0].x} ${h} Z`;

  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="w-full" style={{ height }} preserveAspectRatio="none">
      <defs>
        <linearGradient id={`spark-${color.replace("#", "")}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.3" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={areaPath} fill={`url(#spark-${color.replace("#", "")})`} />
      <path d={linePath} fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      {/* Dot on last point */}
      <circle cx={points[points.length - 1].x} cy={points[points.length - 1].y} r="3" fill={color} />
    </svg>
  );
}

// ---------------------------------------------------------------------------
// Hero Metric — the big impressive number
// ---------------------------------------------------------------------------

function HeroMetric({
  label,
  value,
  suffix,
  gradient,
  numberRef,
}: {
  label: string;
  value: number;
  suffix?: string;
  gradient: string;
  numberRef?: React.Ref<HTMLSpanElement>;
}) {
  const animated = useAnimatedNumber(value, 2400);

  return (
    <div className="flex flex-col items-center text-center">
      <div className="text-[11px] uppercase tracking-[0.25em] text-cream-muted font-medium mb-3">
        {label}
      </div>
      <div className="relative">
        {/* Glow behind */}
        <div
          className="absolute inset-0 blur-3xl opacity-20 rounded-full"
          style={{ background: gradient, transform: "scale(1.5)" }}
        />
        <span
          ref={numberRef}
          className="relative font-serif tabular-nums leading-none showcase-hero-number"
          style={{
            fontSize: "clamp(4rem, 12vw, 9rem)",
            backgroundImage: gradient,
            WebkitBackgroundClip: "text",
            WebkitTextFillColor: "transparent",
            backgroundClip: "text",
          }}
        >
          {formatNumber(animated)}
        </span>
        {suffix && (
          <span className="text-cream-muted text-2xl font-sans ml-2">{suffix}</span>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Compact Metric Card — single-row secondary metrics
// ---------------------------------------------------------------------------

function MetricCardCompact({
  label,
  value,
  displayValue,
  accentColor,
}: {
  label: string;
  value: number;
  displayValue?: string;
  accentColor?: string;
}) {
  const animated = useAnimatedNumber(value, 1800);

  return (
    <div className="showcase-card relative overflow-hidden rounded-xl border border-border-subtle bg-surface px-4 py-3">
      <div
        className="absolute top-0 left-0 right-0 h-[1px] opacity-30"
        style={{ background: accentColor ? `linear-gradient(90deg, transparent, ${accentColor}, transparent)` : undefined }}
      />
      <div className="text-[9px] uppercase tracking-[0.15em] text-cream-muted font-medium mb-1">
        {label}
      </div>
      <div className="font-serif text-2xl text-cream tabular-nums leading-none">
        {displayValue ?? formatNumber(animated)}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Tier Distribution — horizontal bar
// ---------------------------------------------------------------------------

function TierBar({
  tiers,
  total,
}: {
  tiers: { name: string; count: number; color: string }[];
  total: number;
}) {
  if (total === 0) return null;

  return (
    <div className="mt-6">
      <div className="flex rounded-full overflow-hidden h-3 bg-surface-light">
        {tiers.map((t) => {
          const pct = (t.count / total) * 100;
          if (pct < 0.5) return null;
          return (
            <div
              key={t.name}
              className="transition-all duration-1000 ease-out"
              style={{ width: `${pct}%`, backgroundColor: t.color }}
              title={`${t.name}: ${t.count} (${pct.toFixed(1)}%)`}
            />
          );
        })}
      </div>
      <div className="flex flex-wrap gap-x-5 gap-y-1 mt-3">
        {tiers.map((t) => (
          <div key={t.name} className="flex items-center gap-1.5 text-xs text-cream-dim">
            <div className="w-2 h-2 rounded-full" style={{ backgroundColor: t.color }} />
            <span>{t.name}</span>
            <span className="tabular-nums text-cream-muted">{t.count}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Live clock + days counter
// ---------------------------------------------------------------------------

function LiveClock({ launchedAt }: { launchedAt: string | null }) {
  const [now, setNow] = useState(new Date());

  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  const days = daysSinceLaunch(launchedAt);

  return (
    <div className="flex items-center gap-6 text-xs text-cream-muted">
      <div className="flex items-center gap-2">
        <div className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse" />
        <span className="uppercase tracking-widest font-medium">Live</span>
      </div>
      <span className="tabular-nums">
        {now.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
      </span>
      {days > 0 && (
        <span className="text-cream-muted">
          Day <span className="text-cream tabular-nums">{days}</span>
        </span>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Live Feed — event stream with animations
// ---------------------------------------------------------------------------

const EVENT_CONFIG: Record<string, { label: string; icon: string; color: string }> = {
  registration: { label: "Новая регистрация", icon: "●", color: "#A78BFA" },
  analysis: { label: "Анализ запущен", icon: "▶", color: "#6366F1" },
  payment: { label: "Оплата", icon: "★", color: "#34D399" },
  rating: { label: "Оценка", icon: "★", color: "#FBBF24" },
};

function LiveFeed({ events }: { events: ShowcaseEvent[] }) {
  // Filter out job_status events from live feed (they go to pipeline)
  const feedEvents = events.filter((e) => e.type !== "job_status");

  return (
    <div className="showcase-card relative overflow-hidden rounded-2xl border border-border-subtle bg-surface p-6">
      <div className="absolute top-0 left-0 right-0 h-[1px] opacity-40"
        style={{ background: "linear-gradient(90deg, transparent, #A78BFA, transparent)" }}
      />
      <div className="flex items-center justify-between mb-4">
        <div className="text-[10px] uppercase tracking-[0.2em] text-cream-muted font-medium">
          Live Feed
        </div>
        <div className="flex items-center gap-2">
          <div className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse" />
          <span className="text-[10px] text-cream-muted uppercase tracking-wider">Realtime</span>
        </div>
      </div>

      <div className="space-y-2 max-h-72 overflow-y-auto scrollbar-hide">
        {feedEvents.length === 0 && (
          <div className="text-cream-muted text-xs text-center py-6">
            Ожидание событий...
          </div>
        )}
        {feedEvents.map((evt) => {
          const cfg = EVENT_CONFIG[evt.type];
          if (!cfg) return null;
          const time = new Date(evt.ts).toLocaleTimeString("ru-RU", {
            hour: "2-digit",
            minute: "2-digit",
            second: "2-digit",
          });

          return (
            <div
              key={evt.id}
              className="flex items-center gap-3 px-3 py-2 rounded-lg bg-surface-light/50 animate-[slideIn_0.3s_ease-out]"
            >
              <span className="text-sm" style={{ color: cfg.color }}>{cfg.icon}</span>
              <span className="text-sm text-cream flex-1">
                {evt.type === "rating"
                  ? (evt.masked_email || cfg.label)
                  : cfg.label}
                {evt.type === "rating" && evt.rating && (
                  <span className="ml-1.5 text-amber-400">{"★".repeat(Number(evt.rating))}</span>
                )}
              </span>
              {evt.tier && (
                <span className="text-[10px] uppercase tracking-wider text-cream-muted border border-border-subtle rounded-full px-2 py-0.5">
                  {evt.tier}
                </span>
              )}
              <span className="text-[10px] tabular-nums text-cream-muted">{time}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Live Job Pipeline — real-time job flow visualization
// ---------------------------------------------------------------------------

function JobPipeline({ jobs }: { jobs: PipelineJob[] }) {
  // Use a ticking timestamp to filter completed jobs (avoids impure Date.now() in render)
  const [tick, setTick] = useState(() => Date.now());
  useEffect(() => {
    const timer = setInterval(() => setTick(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);
  const visibleJobs = useMemo(
    () => jobs.filter((j) => !j.completedAt || tick - j.completedAt < 8000),
    [jobs, tick],
  );

  const runningCount = visibleJobs.filter((j) => !j.completedAt).length;

  // Human-readable stage label
  function stageLabel(status: string): string {
    const stage = PIPELINE_STAGES.find((s) => s.key === status);
    return stage?.label ?? status;
  }

  function stageIcon(status: string): string {
    const stage = PIPELINE_STAGES.find((s) => s.key === status);
    return stage?.icon ?? "⏳";
  }

  // Elapsed time since job started
  function elapsed(createdAt: string): string {
    const diff = Math.max(0, Math.floor((tick - new Date(createdAt).getTime()) / 1000));
    if (diff < 60) return `${diff}s`;
    const m = Math.floor(diff / 60);
    const s = diff % 60;
    return `${m}:${s.toString().padStart(2, "0")}`;
  }

  return (
    <div className="showcase-card relative overflow-hidden rounded-2xl border border-border-subtle bg-surface p-6 mb-8">
      <div className="absolute top-0 left-0 right-0 h-[1px] opacity-40"
        style={{ background: "linear-gradient(90deg, transparent, #6366F1, transparent)" }}
      />
      <div className="flex items-center justify-between mb-5">
        <div className="text-[10px] uppercase tracking-[0.2em] text-cream-muted font-medium">
          Active Jobs
        </div>
        <div className="flex items-center gap-2">
          {runningCount > 0 && (
            <div className="w-1.5 h-1.5 rounded-full bg-indigo-500 animate-pulse" />
          )}
          <span className="text-[10px] text-cream-muted tabular-nums">
            {runningCount > 0 ? `${runningCount} running` : "idle"}
          </span>
        </div>
      </div>

      <div className="space-y-1.5 max-h-[360px] overflow-y-auto scrollbar-hide">
        {visibleJobs.length === 0 && (
          <div className="text-cream-muted text-xs text-center py-8 opacity-60">
            Нет активных задач
          </div>
        )}
        {visibleJobs.map((job) => {
          const platform = PLATFORM_CONFIG[job.video_platform ?? "unknown"] ?? PLATFORM_CONFIG.unknown;
          const isCompleted = job.status === "completed";
          const isFailed = job.failed;
          const isRunning = !isCompleted && !isFailed;
          const stageIdx = STAGE_INDEX[job.status] ?? 0;
          const totalStages = PIPELINE_STAGES.length;
          const stagePct = isCompleted ? 100 : Math.round(((stageIdx + (job.progress > 0 ? job.progress : 0)) / totalStages) * 100);

          return (
            <div
              key={job.job_id}
              className="relative rounded-xl px-4 py-3 transition-all duration-500"
              style={{
                background: isFailed
                  ? "rgba(239, 68, 68, 0.06)"
                  : isCompleted
                    ? "rgba(52, 211, 153, 0.06)"
                    : "rgba(99, 102, 241, 0.04)",
                opacity: job.completedAt ? Math.max(0.3, 1 - (tick - job.completedAt) / 8000) : 1,
                animation: job.completedAt ? undefined : "slideIn 0.3s ease-out",
              }}
            >
              {/* Row 1: Email + Platform + Stage + Timer */}
              <div className="flex items-center gap-2 mb-2">
                {/* Status dot */}
                <div
                  className="w-2 h-2 rounded-full flex-shrink-0"
                  style={{
                    backgroundColor: isFailed ? "#EF4444" : isCompleted ? "#34D399" : platform.color,
                    boxShadow: isRunning ? `0 0 6px ${platform.color}60` : undefined,
                  }}
                />

                {/* Masked email */}
                <span className="text-xs text-cream truncate min-w-0 flex-1">
                  {job.masked_email || job.video_author || job.job_id.slice(0, 8)}
                </span>

                {/* Platform badge */}
                <span
                  className="text-[9px] uppercase tracking-wider px-1.5 py-0.5 rounded flex-shrink-0"
                  style={{
                    color: platform.color,
                    backgroundColor: `${platform.color}15`,
                    border: `1px solid ${platform.color}25`,
                  }}
                >
                  {platform.icon} {platform.label}
                </span>

                {/* Timer / result */}
                {isCompleted && (
                  <span className="text-[10px] text-green-400 flex-shrink-0 font-medium">
                    ✔ Done
                  </span>
                )}
                {isFailed && (
                  <span className="text-[10px] text-red-400 flex-shrink-0 font-medium">
                    ✘ Failed
                  </span>
                )}
                {isRunning && (
                  <span className="text-[10px] tabular-nums text-cream-dim flex-shrink-0">
                    {elapsed(job.created_at)}
                  </span>
                )}
              </div>

              {/* Row 2: Stage indicator + progress */}
              <div className="flex items-center gap-2">
                {/* Stage pill */}
                <div className="flex items-center gap-1.5 flex-shrink-0">
                  <span className="text-xs">{stageIcon(job.status)}</span>
                  <span
                    className="text-[10px] font-medium"
                    style={{
                      color: isFailed ? "#EF4444" : isCompleted ? "#34D399" : "#A78BFA",
                    }}
                  >
                    {stageLabel(job.status)}
                  </span>
                </div>

                {/* Progress bar — full width */}
                <div className="flex-1 h-1 rounded-full bg-surface-light overflow-hidden">
                  <div
                    className="h-full rounded-full transition-all duration-700 ease-out"
                    style={{
                      width: `${Math.min(stagePct, 100)}%`,
                      background: isFailed
                        ? "#EF4444"
                        : isCompleted
                          ? "#34D399"
                          : "linear-gradient(90deg, #6366F1, #A78BFA)",
                    }}
                  />
                </div>

                {/* Percentage */}
                {isRunning && (
                  <span className="text-[9px] tabular-nums text-cream-dim flex-shrink-0 w-7 text-right">
                    {stagePct}%
                  </span>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Job Stats Ring — SVG donut chart
// ---------------------------------------------------------------------------

function JobStatsRing({
  completed,
  failed,
  running,
  successRate,
}: {
  completed: number;
  failed: number;
  running: number;
  successRate: number;
}) {
  const animatedRate = useAnimatedNumber(Math.round(successRate * 10), 2000);
  const total = completed + failed + running;

  const radius = 52;
  const circumference = 2 * Math.PI * radius;

  // Calculate stroke segments
  const completedPct = total > 0 ? completed / total : 0;
  const failedPct = total > 0 ? failed / total : 0;
  const runningPct = total > 0 ? running / total : 0;

  const completedLen = circumference * completedPct;
  const failedLen = circumference * failedPct;
  const runningLen = circumference * runningPct;

  return (
    <div className="showcase-card relative overflow-hidden rounded-2xl border border-border-subtle bg-surface p-6">
      <div className="absolute top-0 left-0 right-0 h-[1px] opacity-40"
        style={{ background: "linear-gradient(90deg, transparent, #34D399, transparent)" }}
      />
      <div className="text-[10px] uppercase tracking-[0.2em] text-cream-muted font-medium mb-4">
        Success Rate
      </div>

      <div className="flex items-center gap-6">
        {/* Donut */}
        <div className="relative flex-shrink-0" style={{ width: 130, height: 130 }}>
          <svg viewBox="0 0 120 120" className="w-full h-full -rotate-90">
            {/* Background ring */}
            <circle cx="60" cy="60" r={radius} fill="none" stroke="rgba(255,255,255,0.05)" strokeWidth="10" />
            {/* Completed (green) */}
            <circle
              cx="60" cy="60" r={radius} fill="none"
              stroke="#34D399" strokeWidth="10" strokeLinecap="round"
              strokeDasharray={`${completedLen} ${circumference}`}
              strokeDashoffset="0"
              style={{ transition: "stroke-dasharray 1.5s ease-out" }}
            />
            {/* Failed (red) */}
            <circle
              cx="60" cy="60" r={radius} fill="none"
              stroke="#EF4444" strokeWidth="10" strokeLinecap="round"
              strokeDasharray={`${failedLen} ${circumference}`}
              strokeDashoffset={`${-completedLen}`}
              style={{ transition: "stroke-dasharray 1.5s ease-out" }}
            />
            {/* Running (blue) */}
            <circle
              cx="60" cy="60" r={radius} fill="none"
              stroke="#6366F1" strokeWidth="10" strokeLinecap="round"
              strokeDasharray={`${runningLen} ${circumference}`}
              strokeDashoffset={`${-(completedLen + failedLen)}`}
              style={{ transition: "stroke-dasharray 1.5s ease-out" }}
            />
          </svg>
          {/* Center text */}
          <div className="absolute inset-0 flex items-center justify-center">
            <span className="font-serif text-3xl text-cream tabular-nums">
              {(animatedRate / 10).toFixed(1)}%
            </span>
          </div>
        </div>

        {/* Legend */}
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <div className="w-2.5 h-2.5 rounded-full bg-green-400" />
            <span className="text-xs text-cream-muted">{formatNumber(completed)}</span>
            <span className="text-[10px] text-cream-dim">completed</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-2.5 h-2.5 rounded-full bg-red-400" />
            <span className="text-xs text-cream-muted">{formatNumber(failed)}</span>
            <span className="text-[10px] text-cream-dim">failed</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-2.5 h-2.5 rounded-full bg-indigo-400" />
            <span className="text-xs text-cream-muted">{formatNumber(running)}</span>
            <span className="text-[10px] text-cream-dim">running</span>
          </div>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Platform Mix — breakdown by platform
// ---------------------------------------------------------------------------

function PlatformMix({ platforms }: { platforms: ShowcasePlatformStat[] }) {
  const visible = platforms.filter((p) => p.platform !== "unknown").sort((a, b) => b.total - a.total);
  const maxTotal = Math.max(...visible.map((p) => p.total), 1);

  return (
    <div className="showcase-card relative overflow-hidden rounded-2xl border border-border-subtle bg-surface p-6">
      <div className="absolute top-0 left-0 right-0 h-[1px] opacity-40"
        style={{ background: "linear-gradient(90deg, transparent, #E1306C, #00F2EA, transparent)" }}
      />
      <div className="text-[10px] uppercase tracking-[0.2em] text-cream-muted font-medium mb-4">
        Platforms
      </div>

      <div className="space-y-3">
        {visible
          .map((p) => {
            const cfg = PLATFORM_CONFIG[p.platform] ?? PLATFORM_CONFIG.unknown;
            const barPct = (p.total / maxTotal) * 100;
            return (
              <div key={p.platform}>
                <div className="flex items-center gap-2 mb-1.5">
                  <span className="text-sm">{cfg.icon}</span>
                  <span className="text-xs text-cream flex-1">{cfg.label}</span>
                  <span className="text-xs tabular-nums text-cream-muted">{formatNumber(p.total)}</span>
                  <span className="text-[10px] tabular-nums" style={{ color: cfg.color }}>{p.success_rate}%</span>
                </div>
                <div className="h-1.5 rounded-full bg-surface-light overflow-hidden">
                  <div
                    className="h-full rounded-full transition-all duration-1000 ease-out"
                    style={{
                      width: `${barPct}%`,
                      background: `linear-gradient(90deg, ${cfg.color}CC, ${cfg.color})`,
                    }}
                  />
                </div>
              </div>
            );
          })}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Speed Metrics — processing time stats
// ---------------------------------------------------------------------------

function SpeedMetrics({
  avgSeconds,
  fastestSeconds,
  perHour,
}: {
  avgSeconds: number | null;
  fastestSeconds: number | null;
  perHour: number;
}) {
  return (
    <div className="showcase-card relative overflow-hidden rounded-2xl border border-border-subtle bg-surface p-6">
      <div className="absolute top-0 left-0 right-0 h-[1px] opacity-40"
        style={{ background: "linear-gradient(90deg, transparent, #F59E0B, transparent)" }}
      />
      <div className="text-[10px] uppercase tracking-[0.2em] text-cream-muted font-medium mb-4">
        Speed
      </div>

      <div className="space-y-4">
        <div>
          <div className="text-[9px] uppercase tracking-wider text-cream-dim mb-1">Avg time</div>
          <div className="font-serif text-2xl text-cream tabular-nums">
            {avgSeconds != null ? formatDuration(avgSeconds) : "—"}
          </div>
        </div>
        <div>
          <div className="text-[9px] uppercase tracking-wider text-cream-dim mb-1">Fastest today</div>
          <div className="font-serif text-xl text-amber-400 tabular-nums">
            {fastestSeconds != null ? formatDuration(fastestSeconds) : "—"}
          </div>
        </div>
        <div>
          <div className="text-[9px] uppercase tracking-wider text-cream-dim mb-1">Throughput</div>
          <div className="font-serif text-xl text-cream tabular-nums">
            {perHour}/hr
          </div>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Activity Heatmap — weekday x hour
// ---------------------------------------------------------------------------

const WEEKDAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

function ActivityHeatmap({ cells }: { cells: ShowcaseHeatmapCell[] }) {
  // Build lookup
  const lookup: Record<string, number> = {};
  let maxCount = 1;
  for (const c of cells) {
    const key = `${c.weekday}-${c.hour}`;
    lookup[key] = c.count;
    if (c.count > maxCount) maxCount = c.count;
  }

  return (
    <div className="showcase-card relative overflow-hidden rounded-2xl border border-border-subtle bg-surface p-6 mb-8">
      <div className="absolute top-0 left-0 right-0 h-[1px] opacity-40"
        style={{ background: "linear-gradient(90deg, transparent, #7C3AED, transparent)" }}
      />
      <div className="text-[10px] uppercase tracking-[0.2em] text-cream-muted font-medium mb-4">
        Activity Heatmap
      </div>

      <div className="overflow-x-auto">
        <div className="min-w-[600px]">
          {/* Hour labels */}
          <div className="flex ml-10 mb-1">
            {Array.from({ length: 24 }, (_, h) => (
              <div key={h} className="flex-1 text-center text-[8px] text-cream-dim tabular-nums">
                {h % 3 === 0 ? h : ""}
              </div>
            ))}
          </div>

          {/* Grid */}
          {WEEKDAY_LABELS.map((dayLabel, wd) => (
            <div key={dayLabel} className="flex items-center gap-1 mb-[3px]">
              <div className="w-8 text-right text-[9px] text-cream-dim">{dayLabel}</div>
              <div className="flex-1 flex gap-[2px]">
                {Array.from({ length: 24 }, (_, h) => {
                  const count = lookup[`${wd}-${h}`] ?? 0;
                  const intensity = count / maxCount;
                  return (
                    <div
                      key={h}
                      className="flex-1 rounded-[2px] transition-colors duration-300"
                      style={{
                        height: 14,
                        backgroundColor: count === 0
                          ? "rgba(255,255,255,0.03)"
                          : `rgba(124, 58, 237, ${0.15 + intensity * 0.85})`,
                      }}
                      title={`${dayLabel} ${h}:00 — ${count} analyses`}
                    />
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Scale */}
      <div className="flex items-center gap-2 mt-3 justify-end">
        <span className="text-[9px] text-cream-dim">Less</span>
        {[0, 0.25, 0.5, 0.75, 1].map((v) => (
          <div
            key={v}
            className="w-3 h-3 rounded-[2px]"
            style={{
              backgroundColor: v === 0
                ? "rgba(255,255,255,0.03)"
                : `rgba(124, 58, 237, ${0.15 + v * 0.85})`,
            }}
          />
        ))}
        <span className="text-[9px] text-cream-dim">More</span>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Milestone Toast
// ---------------------------------------------------------------------------

function MilestoneToast({ message, onDone }: { message: string; onDone: () => void }) {
  useEffect(() => {
    const timer = setTimeout(onDone, 5000);
    return () => clearTimeout(timer);
  }, [onDone]);

  return (
    <div
      className="fixed top-8 left-1/2 -translate-x-1/2 z-50 px-8 py-4 rounded-2xl border border-purple-500/30 bg-[#0C0C0C]/95 backdrop-blur-xl"
      style={{ animation: "milestoneIn 0.6s ease-out" }}
    >
      <div className="text-center">
        <div className="text-2xl mb-1">{"\u{1F3AF}"}</div>
        <div className="font-serif text-lg text-cream">{message}</div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main Component
// ---------------------------------------------------------------------------

const MAX_FEED_EVENTS = 50;
const MAX_PIPELINE_JOBS = 15;

// Milestone thresholds
function checkMilestone(prev: number, next: number): string | null {
  const thresholds = [10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000];
  for (const t of thresholds) {
    if (prev < t && next >= t) return `${formatNumber(t)}`;
  }
  return null;
}

export function ShowcaseDashboard() {
  const [stats, setStats] = useState<ShowcaseStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [events, setEvents] = useState<ShowcaseEvent[]>([]);
  const [soundEnabled, setSoundEnabled] = useState(true);
  const soundEnabledRef = useRef(true);
  const [todayOnly, setTodayOnly] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [pipelineJobs, setPipelineJobs] = useState<PipelineJob[]>([]);
  const [milestone, setMilestone] = useState<string | null>(null);
  const [demoMode, setDemoMode] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const revenueRef = useRef<HTMLSpanElement>(null);
  const usersRef = useRef<HTMLSpanElement>(null);

  // Periodically prune completed/failed jobs from pipeline state
  useEffect(() => {
    const timer = setInterval(() => {
      setPipelineJobs((prev) => {
        const now = Date.now();
        const filtered = prev.filter((j) => !j.completedAt || now - j.completedAt < 10000);
        return filtered.length === prev.length ? prev : filtered;
      });
    }, 3000);
    return () => clearInterval(timer);
  }, []);

  // Demo-mode indicator (synthetic analytics overlay) — re-poll so the badge
  // tracks toggles made from the admin panel while this view is already open.
  useEffect(() => {
    let cancelled = false;
    const poll = () =>
      import("../../api/client")
        .then((mod) => (mod.getDemoMode as () => Promise<{ enabled: boolean }>)())
        .then((r) => { if (!cancelled) setDemoMode(r.enabled); })
        .catch(() => {});
    poll();
    const timer = setInterval(poll, 30000);
    return () => { cancelled = true; clearInterval(timer); };
  }, []);

  // Fetch stats (initial + on todayOnly toggle)
  useEffect(() => {
    let cancelled = false;
    import("../../api/client")
      .then((mod) => (mod.getShowcaseStats as (t?: boolean) => Promise<ShowcaseStats>)(todayOnly))
      .then((data: ShowcaseStats) => {
        if (cancelled) return;
        setStats(data);
        // Initialize pipeline with active jobs from API
        if (data.active_jobs?.length) {
          setPipelineJobs(
            data.active_jobs.map((j) => ({
              job_id: j.job_id,
              status: j.status,
              progress: j.progress,
              video_platform: j.video_platform,
              video_author: j.video_author,
              video_title: j.video_title,
              source: j.source,
              masked_email: j.masked_email,
              created_at: j.created_at,
            })),
          );
        }
      })
      .catch((e: Error) => { if (!cancelled) setError(e?.message ?? "Failed to load"); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [todayOnly]);

  const handleEvent = useCallback((evt: ShowcaseEvent) => {
    // Handle job_status events → update pipeline
    if (evt.type === "job_status" && evt.job_id && evt.new_status) {
      setPipelineJobs((prev) => {
        const existing = prev.find((j) => j.job_id === evt.job_id);
        const isTerminal = evt.new_status === "completed" || evt.new_status === "failed";

        if (existing) {
          return prev.map((j) =>
            j.job_id === evt.job_id
              ? {
                  ...j,
                  status: evt.new_status!,
                  progress: Number(evt.progress ?? j.progress),
                  video_platform: evt.video_platform ?? j.video_platform,
                  video_author: evt.video_author ?? j.video_author,
                  video_title: evt.video_title ?? j.video_title,
                  masked_email: evt.masked_email ?? j.masked_email,
                  completedAt: isTerminal ? Date.now() : undefined,
                  failed: evt.new_status === "failed",
                }
              : j,
          );
        }

        // New job
        const newJob: PipelineJob = {
          job_id: evt.job_id!,
          status: evt.new_status!,
          progress: Number(evt.progress ?? 0),
          video_platform: evt.video_platform ?? null,
          video_author: evt.video_author ?? null,
          video_title: evt.video_title ?? null,
          source: evt.source ?? null,
          masked_email: evt.masked_email ?? null,
          created_at: evt.ts,
          completedAt: isTerminal ? Date.now() : undefined,
          failed: evt.new_status === "failed",
        };
        return [newJob, ...prev].slice(0, MAX_PIPELINE_JOBS);
      });

      // Sound for completed jobs (cleanup handled by periodic prune effect)
      if (evt.new_status === "completed" && soundEnabledRef.current) {
        try { playJobCompleteSound(); } catch { /* */ }
      }

      // Update running count + check milestones (side effects after state read)
      setStats((prev) => {
        if (!prev) return prev;
        if (evt.new_status === "completed") {
          const newCompleted = prev.jobs_completed + 1;
          const total = newCompleted + prev.jobs_failed;
          const ms = checkMilestone(prev.jobs_completed, newCompleted);
          if (ms) {
            setMilestone(`${ms} analyses completed!`);
            if (soundEnabledRef.current) try { playMilestoneSound(); } catch { /* */ }
            if (containerRef.current) launchConfetti(containerRef.current);
          }
          return {
            ...prev,
            jobs_completed: newCompleted,
            jobs_running: Math.max(0, prev.jobs_running - 1),
            jobs_success_rate: total > 0 ? Math.round((newCompleted / total) * 1000) / 10 : 0,
          };
        }
        if (evt.new_status === "failed") {
          const newFailed = prev.jobs_failed + 1;
          const total = prev.jobs_completed + newFailed;
          return {
            ...prev,
            jobs_failed: newFailed,
            jobs_running: Math.max(0, prev.jobs_running - 1),
            jobs_success_rate: total > 0 ? Math.round((prev.jobs_completed / total) * 1000) / 10 : 0,
          };
        }
        // New job entered the pipeline (first real status change)
        if (evt.old_status === "pending" || evt.old_status === "" || !evt.old_status) {
          return { ...prev, jobs_running: prev.jobs_running + 1 };
        }
        return prev;
      });

      return; // Don't add job_status to feed events
    }

    // For rating events with user_id, update existing entry instead of adding a new one
    setEvents((prev) => {
      if (evt.type === "rating" && evt.user_id) {
        const existingIdx = prev.findIndex(
          (e) => e.type === "rating" && e.user_id === evt.user_id
        );
        if (existingIdx !== -1) {
          const updated = [...prev];
          updated.splice(existingIdx, 1);
          return [evt, ...updated].slice(0, MAX_FEED_EVENTS);
        }
      }
      return [evt, ...prev].slice(0, MAX_FEED_EVENTS);
    });

    // Play sound
    if (soundEnabledRef.current) {
      const playFn = SOUND_MAP[evt.type];
      if (playFn) {
        try {
          playFn();
        } catch {
          // Audio playback can fail in restricted contexts
        }
      }
    }

    // Coin rain on payment
    if (evt.type === "payment" && containerRef.current) {
      launchCoinRain(containerRef.current, revenueRef.current);
    }

    // Buddy run on registration
    if (evt.type === "registration" && containerRef.current) {
      launchBuddyRun(containerRef.current, usersRef.current);
    }

    // Increment relevant metrics
    setStats((prev) => {
      if (!prev) return prev;
      switch (evt.type) {
        case "registration": {
          const newRegistered = prev.total_registered + 1;
          const ms = checkMilestone(prev.total_registered, newRegistered);
          if (ms) {
            setMilestone(`${ms} users registered!`);
            if (soundEnabledRef.current) try { playMilestoneSound(); } catch { /* */ }
            if (containerRef.current) launchConfetti(containerRef.current);
          }
          return { ...prev, total_registered: newRegistered };
        }
        case "analysis":
          return {
            ...prev,
            total_analyses: prev.total_analyses + 1,
            analyses_today: prev.analyses_today + 1,
          };
        case "payment": {
          const amt = evt.amount ? Number(evt.amount) : 0;
          const isEur = evt.currency?.toUpperCase() === "EUR";
          return {
            ...prev,
            total_paid: prev.total_paid + 1,
            total_rub_kopecks: prev.total_rub_kopecks + (isEur ? 0 : amt),
            total_eur_cents: prev.total_eur_cents + (isEur ? amt : 0),
          };
        }
        case "rating": {
          const isUpdate = evt.is_update === "True";
          if (isUpdate) {
            return prev;
          }
          const newTotal = prev.total_ratings + 1;
          const newRating = evt.rating ? Number(evt.rating) : 0;
          const newAvg = prev.avg_rating != null
            ? (prev.avg_rating * prev.total_ratings + newRating) / newTotal
            : newRating;
          return {
            ...prev,
            total_ratings: newTotal,
            unread_ratings: prev.unread_ratings + 1,
            avg_rating: Math.round(newAvg * 100) / 100,
          };
        }
        default:
          return prev;
      }
    });
  }, []);

  useShowcaseWebSocket(handleEvent);

  // Periodic re-sync from API every 60s to prevent drift from phantom WS events
  useEffect(() => {
    const timer = setInterval(async () => {
      try {
        const { getShowcaseStats } = await import("../../api/client");
        const fresh = await (getShowcaseStats as (t?: boolean) => Promise<ShowcaseStats>)(todayOnly);
        setStats(fresh);
      } catch {
        // Ignore — next tick will retry
      }
    }, 60_000);
    return () => clearInterval(timer);
  }, [todayOnly]);

  const handleResetBaseline = useCallback(async () => {
    if (resetting) return;
    setResetting(true);
    try {
      const { resetShowcaseBaseline } = await import("../../api/client");
      await resetShowcaseBaseline();
      window.location.reload();
    } catch {
      setResetting(false);
    }
  }, [resetting]);

  const toggleSound = useCallback(() => {
    setSoundEnabled((prev) => {
      const next = !prev;
      soundEnabledRef.current = next;
      // Resume AudioContext on user gesture
      if (next && _audioCtx?.state === "suspended") {
        _audioCtx.resume();
      }
      return next;
    });
  }, []);

  if (loading) {
    return (
      <div className="min-h-screen bg-[#0C0C0C] flex items-center justify-center">
        <div className="text-cream-muted text-sm animate-pulse">Loading showcase...</div>
      </div>
    );
  }

  if (error || !stats) {
    return (
      <div className="min-h-screen bg-[#0C0C0C] flex items-center justify-center">
        <div className="text-red-400 text-sm">{error ?? "No data"}</div>
      </div>
    );
  }

  // Safety defaults for fields that may be missing from older backend versions
  const safeStats = {
    ...stats,
    daily: stats.daily ?? [],
    jobs_completed: stats.jobs_completed ?? 0,
    jobs_failed: stats.jobs_failed ?? 0,
    jobs_running: stats.jobs_running ?? 0,
    jobs_success_rate: stats.jobs_success_rate ?? 0,
    platform_stats: stats.platform_stats ?? [],
    avg_processing_seconds: stats.avg_processing_seconds ?? null,
    fastest_today_seconds: stats.fastest_today_seconds ?? null,
    jobs_per_hour: stats.jobs_per_hour ?? 0,
    active_jobs: stats.active_jobs ?? [],
    activity_heatmap: stats.activity_heatmap ?? [],
  };

  // Backend already filters by period (today vs all-time), just use directly
  const revenueDisplay = formatMoney(safeStats.total_rub_kopecks, "RUB");

  const tiers = [
    { name: "FREE", count: safeStats.free_users, color: "#6EE7B7" },
    { name: "START", count: safeStats.start_users, color: "#A78BFA" },
    { name: "PRO", count: safeStats.pro_users, color: "#FBBF24" },
    { name: "UNLIMITED", count: safeStats.unlimited_users, color: "#F472B6" },
  ];

  const userSparkData = safeStats.daily.map((d) => d.new_users);
  const revenueSparkData = safeStats.daily.map((d) => d.revenue_rub_kopecks + d.revenue_eur_cents * 105);
  const analysesSparkData = safeStats.daily.map((d) => d.analyses);

  return (
    <div ref={containerRef} className="min-h-screen bg-[#0C0C0C] text-cream showcase-page">
      {/* Milestone toast */}
      {milestone && (
        <MilestoneToast message={milestone} onDone={() => setMilestone(null)} />
      )}

      {/* Top bar */}
      <div className="flex items-center justify-between px-8 pt-6 pb-4">
        <div className="flex items-center gap-3">
          <span className="font-serif text-xl tracking-tight text-cream">Piratex.ai</span>
          <span
            className="text-[10px] uppercase tracking-[0.2em] text-cream-muted border border-border-subtle rounded-full px-2.5 py-0.5 cursor-default select-none"
            onDoubleClick={handleResetBaseline}
            title=""
          >
            {resetting ? "..." : "Showcase"}
          </span>
          {demoMode && (
            <span
              className="text-[10px] uppercase tracking-[0.2em] text-amber-400 border border-amber-500/40 bg-amber-500/10 rounded-full px-2.5 py-0.5 select-none"
              title="Демо-режим: синтетические данные для презентации"
            >
              Demo
            </span>
          )}
        </div>
        <div className="flex items-center gap-4">
          <button
            onClick={() => setTodayOnly((p) => !p)}
            className="text-[10px] uppercase tracking-wider text-cream-muted hover:text-cream transition-colors border border-border-subtle rounded-full px-3 py-1"
            title={todayOnly ? "Показать всё время" : "Показать только сегодня"}
          >
            {todayOnly ? "Всегда" : "Сегодня"}
          </button>
          <button
            onClick={toggleSound}
            className="text-[10px] uppercase tracking-wider text-cream-muted hover:text-cream transition-colors border border-border-subtle rounded-full px-3 py-1"
            title={soundEnabled ? "Выключить звуки" : "Включить звуки"}
          >
            {soundEnabled ? "♫ ON" : "♫ OFF"}
          </button>
          <LiveClock launchedAt={safeStats.launched_at} />
        </div>
      </div>

      <div className="max-w-5xl mx-auto px-6 pb-16">
        {/* Hero — Two key metrics side by side */}
        <div className="grid grid-cols-2 gap-6 pt-8 pb-8">
          <HeroMetric
            label={todayOnly ? "Новых сегодня" : "Пользователей"}
            value={safeStats.total_registered}
            gradient="linear-gradient(135deg, #E0E7FF 0%, #A78BFA 40%, #7C3AED 100%)"
            numberRef={usersRef}
          />
          <div className="flex flex-col items-center text-center">
            <div className="text-[11px] uppercase tracking-[0.25em] text-cream-muted font-medium mb-3">
              {todayOnly ? "Выручка сегодня" : "Выручка"}
            </div>
            <div className="relative">
              <div
                className="absolute inset-0 blur-3xl opacity-20 rounded-full"
                style={{ background: "linear-gradient(135deg, #6EE7B7 0%, #34D399 40%, #059669 100%)", transform: "scale(1.5)" }}
              />
              <span
                ref={revenueRef}
                className="relative font-serif tabular-nums leading-none showcase-hero-number"
                style={{
                  fontSize: "clamp(2.5rem, 8vw, 5.5rem)",
                  backgroundImage: "linear-gradient(135deg, #6EE7B7 0%, #34D399 40%, #059669 100%)",
                  WebkitBackgroundClip: "text",
                  WebkitTextFillColor: "transparent",
                  backgroundClip: "text",
                }}
              >
                {revenueDisplay}
              </span>
            </div>
          </div>
        </div>

        {/* Key metrics — compact row */}
        <div className={`grid grid-cols-3 ${todayOnly ? "lg:grid-cols-5" : "lg:grid-cols-6"} gap-3 mb-3`}>
          <MetricCardCompact label="Платных" value={safeStats.total_paid} accentColor="#A78BFA" />
          <MetricCardCompact label="Конверсия" value={safeStats.conversion_pct} displayValue={`${safeStats.conversion_pct.toFixed(1)}%`} accentColor="#34D399" />
          <MetricCardCompact label={todayOnly ? "Транскрибировано сегодня" : "Транскрибировано"} value={safeStats.total_analyses} accentColor="#6366F1" />
          {!todayOnly && <MetricCardCompact label="Сегодня" value={safeStats.analyses_today} accentColor="#F59E0B" />}
          <MetricCardCompact label="Оценка" value={safeStats.avg_rating ?? 0} displayValue={safeStats.avg_rating != null ? `★ ${safeStats.avg_rating.toFixed(1)}` : "—"} accentColor="#FBBF24" />
          <MetricCardCompact label="Поддержка" value={safeStats.unread_support} displayValue={safeStats.unread_support > 0 ? `${safeStats.unread_support}` : "0"} accentColor={safeStats.unread_support > 0 ? "#F87171" : "#6B7280"} />
        </div>

        {/* Trend monitoring engine — second row */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-6">
          <MetricCardCompact label="Авторов отслеживается" value={safeStats.tracked_authors} accentColor="#22D3EE" />
          <MetricCardCompact label="Трендов найдено" value={safeStats.total_trends_found} accentColor="#F472B6" />
          <MetricCardCompact label="Сейчас в тренде" value={safeStats.trends_currently_hot} accentColor="#FB7185" />
          <MetricCardCompact label="Трендов на автора" value={safeStats.avg_trends_per_author} displayValue={safeStats.avg_trends_per_author.toFixed(1)} accentColor="#A3E635" />
        </div>

        {/* Live Job Pipeline */}
        <JobPipeline jobs={pipelineJobs} />

        {/* Job Stats + Platform + Speed */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-6">
          <JobStatsRing
            completed={safeStats.jobs_completed}
            failed={safeStats.jobs_failed}
            running={safeStats.jobs_running}
            successRate={safeStats.jobs_success_rate}
          />
          <PlatformMix platforms={safeStats.platform_stats} />
          <SpeedMetrics
            avgSeconds={safeStats.avg_processing_seconds}
            fastestSeconds={safeStats.fastest_today_seconds}
            perHour={safeStats.jobs_per_hour}
          />
        </div>

        {/* Live Feed + Sparklines side by side */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">
          <LiveFeed events={events} />

          {/* Sparklines summary */}
          <div className="showcase-card relative overflow-hidden rounded-2xl border border-border-subtle bg-surface p-6">
            <div className="absolute top-0 left-0 right-0 h-[1px] opacity-40"
              style={{ background: "linear-gradient(90deg, transparent, #34D399, transparent)" }}
            />
            <div className="space-y-4">
              <div>
                <div className="text-[10px] uppercase tracking-[0.15em] text-cream-muted font-medium mb-1">Выручка</div>
                <Sparkline data={revenueSparkData} color="#34D399" height={44} />
              </div>
              <div>
                <div className="text-[10px] uppercase tracking-[0.15em] text-cream-muted font-medium mb-1">Пользователи</div>
                <Sparkline data={userSparkData} color="#A78BFA" height={44} />
              </div>
              <div>
                <div className="text-[10px] uppercase tracking-[0.15em] text-cream-muted font-medium mb-1">Анализы</div>
                <Sparkline data={analysesSparkData} color="#6366F1" height={44} />
              </div>
            </div>
          </div>
        </div>

        {/* Tier distribution */}
        <div className="showcase-card relative overflow-hidden rounded-2xl border border-border-subtle bg-surface p-6 mb-6">
          <div className="text-[10px] uppercase tracking-[0.2em] text-cream-muted font-medium mb-2">
            {"Распределение по тарифам"}
          </div>
          <div className="flex gap-4 items-baseline">
            <span className="font-serif text-2xl text-cream tabular-nums">{safeStats.total_registered}</span>
            <span className="text-cream-muted text-xs">{"пользователей"}</span>
          </div>
          <TierBar tiers={tiers} total={safeStats.total_registered} />
        </div>

        {/* === NEW: Activity Heatmap === */}
        {safeStats.activity_heatmap.length > 0 && (
          <ActivityHeatmap cells={safeStats.activity_heatmap} />
        )}

        {/* Growth chart — full width */}
        <div className="showcase-card relative overflow-hidden rounded-2xl border border-border-subtle bg-surface p-8">
          <div className="text-[10px] uppercase tracking-[0.2em] text-cream-muted font-medium mb-6">
            {"Рост пользователей — 30 дней"}
          </div>
          <GrowthChart data={safeStats.daily} />
        </div>
      </div>

      {/* Animations */}
      <style>{`
        @keyframes slideIn {
          from { opacity: 0; transform: translateX(-12px); }
          to { opacity: 1; transform: translateX(0); }
        }
        @keyframes milestoneIn {
          from { opacity: 0; transform: translate(-50%, -20px) scale(0.9); }
          to { opacity: 1; transform: translate(-50%, 0) scale(1); }
        }
      `}</style>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Growth bar chart (30-day)
// ---------------------------------------------------------------------------

function GrowthChart({ data }: { data: ShowcaseDayStats[] }) {
  const maxUsers = Math.max(...data.map((d) => d.new_users), 1);

  return (
    <div className="flex items-end gap-[3px] h-32">
      {data.map((day, i) => {
        const h = (day.new_users / maxUsers) * 100;
        const isToday = i === data.length - 1;
        const label = day.date.slice(5); // "MM-DD"

        return (
          <div key={day.date} className="flex-1 flex flex-col items-center gap-1 group">
            <div
              className="w-full rounded-sm transition-all duration-500"
              style={{
                height: `${h}%`,
                minHeight: day.new_users > 0 ? "3px" : "1px",
                background: isToday
                  ? "linear-gradient(180deg, #A78BFA 0%, #7C3AED 100%)"
                  : day.new_users > 0
                    ? "rgba(167, 139, 250, 0.4)"
                    : "rgba(63, 63, 70, 0.3)",
              }}
              title={`${label}: ${day.new_users} new users`}
            />
            {/* Show labels for every 5th day + today */}
            {(i % 5 === 0 || isToday) && (
              <span className="text-[8px] text-cream-muted tabular-nums">{label}</span>
            )}
          </div>
        );
      })}
    </div>
  );
}
