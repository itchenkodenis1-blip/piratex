import { useCallback, useEffect, useRef, useState } from "react";
import { Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { adminGetSupportUnreadCount, adminGetUnreadRatingsCount } from "../../api/client";
import { useAuth } from "../../hooks/useAuth";
import { AdminDashboard } from "./AdminDashboard";
import { AdminUsers } from "./AdminUsers";
import { AdminUserDetail } from "./AdminUserDetail";
import { AdminJobs } from "./AdminJobs";
import { AdminLibrary } from "./AdminLibrary";
import { AdminLibraryDetail } from "./AdminLibraryDetail";
import { AdminMessages } from "./AdminMessages";
import { AdminPayments } from "./AdminPayments";
import { AdminTiers } from "./AdminTiers";
import { AdminRatings } from "./AdminRatings";
import { AdminSupport } from "./AdminSupport";
import { AdminTrends } from "./AdminTrends";
import { AdminTrendingReels } from "./AdminTrendingReels";
import { AdminHiddenReels } from "./AdminHiddenReels";
import { AdminParsing } from "./AdminParsing";
import { AdminNiches } from "./AdminNiches";
import { AdminTrendWatching } from "./trend-watching";

interface NavItemProps {
  label: string;
  icon: React.ReactNode;
  path: string;
  active: boolean;
  badge?: number;
  onClick: () => void;
}

function NavItem({ label, icon, active, badge, onClick }: NavItemProps) {
  return (
    <button
      onClick={onClick}
      className={`w-full text-left px-3 py-2 rounded-lg text-sm transition-colors flex items-center gap-2.5 ${
        active
          ? "bg-zinc-800 text-zinc-100"
          : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/50"
      }`}
    >
      <span className="w-4 h-4 flex-shrink-0 flex items-center justify-center">{icon}</span>
      <span className="flex-1">{label}</span>
      {badge != null && badge > 0 && (
        <span className="min-w-[20px] h-5 px-1.5 bg-red-500 text-white text-[10px] font-bold rounded-full flex items-center justify-center animate-pulse">
          {badge > 99 ? "99+" : badge}
        </span>
      )}
    </button>
  );
}

// SVG icons for nav items
const icons = {
  home: <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>,
  pipeline: <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>,
  users: <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>,
  tiers: <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="1" y="4" width="22" height="16" rx="2" ry="2"/><line x1="1" y1="10" x2="23" y2="10"/></svg>,
  payments: <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="12" y1="1" x2="12" y2="23"/><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg>,
  jobs: <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>,
  trends: <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/><polyline points="17 6 23 6 23 12"/></svg>,
  moderation: <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>,
  library: <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></svg>,
  messages: <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>,
  analytics: <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M8 16V12"/><path d="M12 16V8"/><path d="M16 16v-6"/></svg>,
  star: <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>,
  support: <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"/></svg>,
  parsing: <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9"/></svg>,
  monitoring: <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/><path d="M16 16l2 2"/></svg>,
  fire: <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M8.5 14.5A2.5 2.5 0 0011 12c0-1.38-.5-2-1-3-1.072-2.143-.224-4.054 2-6 .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 11-14 0c0-1.153.433-2.294 1-3a2.5 2.5 0 002.5 2.5z"/></svg>,
  niches: <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M20.59 13.41l-7.17 7.17a2 2 0 01-2.83 0L2 12V2h10l8.59 8.59a2 2 0 010 2.82z"/><line x1="7" y1="7" x2="7.01" y2="7"/></svg>,
};

// Notification sound — short beep via Web Audio API
function playNotificationSound() {
  try {
    const ctx = new AudioContext();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.frequency.value = 880;
    osc.type = "sine";
    gain.gain.setValueAtTime(0.3, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.3);
    osc.start(ctx.currentTime);
    osc.stop(ctx.currentTime + 0.3);
  } catch { /* audio not available */ }
}

function showBrowserNotification(count: number) {
  if (Notification.permission !== "granted") return;
  const n = new Notification("ВидеоРентген — Поддержка", {
    body: `${count} новых сообщений`,
    icon: "/favicon.ico",
    tag: "piratex-support",
  });
  setTimeout(() => n.close(), 5000);
}

export function AdminPage() {
  const navigate = useNavigate();
  const location = useLocation();
  useAuth();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [supportUnread, setSupportUnread] = useState(0);
  const [ratingsUnread, setRatingsUnread] = useState(0);
  const prevUnreadRef = useRef<number | null>(null); // null = first load

  // Request notification permission on mount
  useEffect(() => {
    if ("Notification" in window && Notification.permission === "default") {
      Notification.requestPermission();
    }
  }, []);

  // Poll unread support + ratings counts
  const pollUnread = useCallback(() => {
    adminGetSupportUnreadCount()
      .then((count) => {
        setSupportUnread(count);
        // Notify only when count increases (skip first load)
        if (prevUnreadRef.current !== null && count > prevUnreadRef.current) {
          playNotificationSound();
          showBrowserNotification(count);
        }
        prevUnreadRef.current = count;
      })
      .catch(() => {});
    adminGetUnreadRatingsCount()
      .then((count) => setRatingsUnread(count))
      .catch(() => {});
  }, []);

  useEffect(() => {
    pollUnread();
    const interval = setInterval(pollUnread, 10_000);
    return () => clearInterval(interval);
  }, [pollUnread]);

  // Update page title with unread count
  useEffect(() => {
    const totalUnread = supportUnread + ratingsUnread;
    document.title = totalUnread > 0 ? `(${totalUnread}) Admin — ВидеоРентген` : "Admin — ВидеоРентген";
  }, [supportUnread, ratingsUnread]);

  const nav = [
    { label: "Аналитика", path: "/showcase", icon: icons.analytics },
    { label: "Главное", path: "/admin", icon: icons.home },
    { label: "Конвейер", path: "/pipeline", icon: icons.pipeline },
    { label: "Пользователи", path: "/admin/users", icon: icons.users },
    { label: "Тарифы", path: "/admin/tiers", icon: icons.tiers },
    { label: "Платежи", path: "/admin/payments", icon: icons.payments },
    { label: "Задачи", path: "/admin/jobs", icon: icons.jobs },
    { label: "Парсинг", path: "/admin/parsing", icon: icons.parsing },
    { label: "Авторы", path: "/admin/trends", icon: icons.trends },
    { label: "Тренды", path: "/admin/trending-reels", icon: icons.fire },
    { label: "Ниши", path: "/admin/niches", icon: icons.niches },
    { label: "Мониторинг", path: "/admin/monitoring", icon: icons.monitoring },
    { label: "Модерация", path: "/admin/moderation", icon: icons.moderation },
    { label: "Библиотека", path: "/admin/library", icon: icons.library },
    { label: "Сообщения", path: "/admin/messages", icon: icons.messages },
    { label: "Оценки", path: "/admin/ratings", icon: icons.star, badge: ratingsUnread },
    { label: "Поддержка", path: "/admin/support", icon: icons.support, badge: supportUnread },
  ];

  const isActive = (path: string) => {
    if (path === "/admin" || path === "/admin/trends") return location.pathname === path;
    return location.pathname.startsWith(path);
  };

  // Close sidebar on route change
  useEffect(() => {
    setSidebarOpen(false);
  }, [location.pathname]);

  return (
    <div className="min-h-screen bg-[#0C0C0C] flex">
      {/* Mobile overlay backdrop */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 bg-black/50 z-20 lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Sidebar */}
      <aside className={`
        w-[220px] min-h-screen bg-zinc-900 border-r border-zinc-800 flex flex-col fixed top-0 left-0 z-30
        transition-transform duration-300
        ${sidebarOpen ? "translate-x-0" : "-translate-x-full"}
        lg:translate-x-0
      `}>
        {/* Header */}
        <div className="px-4 py-5 border-b border-zinc-800">
          <div
            className="text-xs font-medium text-zinc-500 uppercase tracking-wider cursor-pointer hover:text-zinc-300 transition-colors"
            onClick={() => navigate("/")}
          >
            ← Админ панель
          </div>
        </div>

        {/* Navigation */}
        <nav className="flex-1 px-2 py-4 space-y-1">
          {nav.map((item) => (
            <NavItem
              key={item.path}
              label={item.label}
              icon={item.icon}
              path={item.path}
              active={isActive(item.path)}
              badge={"badge" in item ? item.badge : undefined}
              onClick={() => navigate(item.path)}
            />
          ))}
        </nav>

        {/* Footer */}
        <div className="px-4 py-4 border-t border-zinc-800">
          <button
            onClick={() => navigate("/")}
            className="text-xs text-zinc-500 hover:text-zinc-300 transition-colors"
          >
            ← На сайт
          </button>
        </div>
      </aside>

      {/* Main content */}
      <main className="lg:ml-[220px] flex-1 p-4 sm:p-6 lg:p-8">
        {/* Mobile hamburger */}
        <button
          onClick={() => setSidebarOpen(true)}
          className="lg:hidden mb-4 p-2 text-zinc-400 hover:text-zinc-200 transition-colors"
          aria-label="Open menu"
        >
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M3 12h18M3 6h18M3 18h18" />
          </svg>
        </button>

        <Routes>
          <Route index element={<AdminDashboard />} />
          <Route path="users" element={<AdminUsers />} />
          <Route path="users/:id" element={<AdminUserDetail />} />
          <Route path="tiers" element={<AdminTiers />} />
          <Route path="payments" element={<AdminPayments />} />
          <Route path="jobs" element={<AdminJobs />} />
          <Route path="parsing" element={<AdminParsing />} />
          <Route path="trends" element={<AdminTrends />} />
          <Route path="trending-reels" element={<AdminTrendingReels />} />
          <Route path="niches" element={<AdminNiches />} />
          <Route path="monitoring" element={<AdminTrendWatching />} />
          <Route path="moderation" element={<AdminHiddenReels />} />
          <Route path="library" element={<AdminLibrary />} />
          <Route path="library/:id" element={<AdminLibraryDetail />} />
          <Route path="messages" element={<AdminMessages />} />
          <Route path="ratings" element={<AdminRatings />} />
          <Route path="support" element={<AdminSupport />} />
        </Routes>
      </main>
    </div>
  );
}
