import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import MaskedPII from "./MaskedPII";
import {
  adminBlockSupportUser,
  adminGetSupportMessages,
  adminListSupportConversations,
  adminResolveSupportConversation,
  adminSendSupportMessage,
} from "../../api/client";
import type { AdminSupportConversation, AdminSupportMessage } from "../../types";

function formatTime(dt: string): string {
  return new Date(dt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function formatDate(dt: string): string {
  return new Date(dt).toLocaleDateString("ru-RU", { day: "numeric", month: "short" });
}

function ChatBubble({ msg }: { msg: AdminSupportMessage }) {
  const isAdmin = msg.sender_type === "admin";
  return (
    <div className={`flex ${isAdmin ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[75%] px-3 py-2 rounded-2xl text-sm whitespace-pre-wrap break-words ${
          isAdmin
            ? "bg-blue-900/40 text-zinc-100 rounded-br-md"
            : "bg-zinc-800 text-zinc-100 rounded-bl-md"
        }`}
      >
        {msg.image_key && (
          <div className="mb-1">
            <img
              src={`/api/support/image/${msg.image_key}`}
              alt="attachment"
              className="max-w-full max-h-48 rounded-lg"
            />
          </div>
        )}
        {msg.text && <p>{msg.text}</p>}
        <p className={`text-[10px] mt-1 ${isAdmin ? "text-blue-300/50" : "text-zinc-500"}`}>
          {formatTime(msg.created_at)}
        </p>
      </div>
    </div>
  );
}

export function AdminSupport() {
  const [conversations, setConversations] = useState<AdminSupportConversation[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [messages, setMessages] = useState<AdminSupportMessage[]>([]);
  const [msgLoading, setMsgLoading] = useState(false);
  const [replyText, setReplyText] = useState("");
  const [sending, setSending] = useState(false);
  const [statusFilter, setStatusFilter] = useState("");
  const [search, setSearch] = useState("");
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const selectedConv = conversations.find((c) => c.id === selectedId);

  const loadConversations = useCallback(() => {
    adminListSupportConversations({
      status: statusFilter || undefined,
      q: search || undefined,
      per_page: 100,
    })
      .then((res) => {
        setConversations(res.items);
        setTotal(res.total);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [statusFilter, search]);

  useEffect(() => {
    loadConversations();
    const interval = setInterval(loadConversations, 15_000);
    return () => clearInterval(interval);
  }, [loadConversations]);

  // Load messages when selecting a conversation + poll every 5s
  useEffect(() => {
    if (!selectedId) return;
    let cancelled = false;
    const load = async () => {
      try {
        const msgs = await adminGetSupportMessages(selectedId);
        if (!cancelled) { setMessages(msgs); setMsgLoading(false); }
      } catch {
        if (!cancelled) setMsgLoading(false);
      }
    };
    load();
    const interval = setInterval(load, 5_000);
    return () => { cancelled = true; clearInterval(interval); };
  }, [selectedId]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSend = async () => {
    if (!replyText.trim() || !selectedId || sending) return;
    setSending(true);
    try {
      const msg = await adminSendSupportMessage(selectedId, replyText.trim());
      setMessages((prev) => [...prev, msg]);
      setReplyText("");
      // Update conversation in list
      setConversations((prev) =>
        prev.map((c) =>
          c.id === selectedId
            ? { ...c, last_message_text: msg.text, last_message_at: msg.created_at, unread_admin: 0 }
            : c,
        ),
      );
    } catch { /* ignore */ }
    setSending(false);
  };

  const handleResolve = async () => {
    if (!selectedId) return;
    await adminResolveSupportConversation(selectedId);
    setConversations((prev) =>
      prev.map((c) => (c.id === selectedId ? { ...c, status: "resolved" } : c)),
    );
  };

  const handleBlock = async () => {
    if (!selectedId || !confirm("Заблокировать этого пользователя в поддержке?")) return;
    await adminBlockSupportUser(selectedId);
    setConversations((prev) =>
      prev.map((c) => (c.id === selectedId ? { ...c, status: "resolved" } : c)),
    );
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <h1 className="text-xl font-semibold text-zinc-100">Поддержка ({total})</h1>
        <div className="flex gap-3 items-center">
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-1.5 text-sm text-zinc-200"
          >
            <option value="">Все</option>
            <option value="open">Открытые</option>
            <option value="resolved">Решённые</option>
          </select>
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Поиск по email..."
            className="bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-1.5 text-sm text-zinc-200 placeholder:text-zinc-500 w-48"
          />
        </div>
      </div>

      <div className="flex gap-4 h-[calc(100vh-200px)] min-h-[400px]">
        {/* Conversation list */}
        <div className="w-80 shrink-0 bg-zinc-900 rounded-xl border border-zinc-800 overflow-y-auto">
          {loading ? (
            <div className="text-center text-zinc-500 py-10">Загрузка...</div>
          ) : conversations.length === 0 ? (
            <div className="text-center text-zinc-500 py-10">Нет диалогов</div>
          ) : (
            conversations.map((conv) => (
              <button
                key={conv.id}
                onClick={() => setSelectedId(conv.id)}
                className={`w-full text-left px-4 py-3 border-b border-zinc-800/50 hover:bg-zinc-800/50 transition-colors ${
                  selectedId === conv.id ? "bg-zinc-800" : ""
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="text-sm text-zinc-200 font-medium truncate">
                    {conv.user_name ? <MaskedPII type="name" value={conv.user_name} /> : conv.user_email ? <MaskedPII type="email" value={conv.user_email} /> : conv.user_telegram ? <MaskedPII type="telegram" value={conv.user_telegram} /> : "User"}
                  </span>
                  <div className="flex items-center gap-2">
                    {conv.status === "resolved" && (
                      <span className="text-[10px] px-1.5 py-0.5 bg-green-900/30 text-green-400 rounded">
                        OK
                      </span>
                    )}
                    {conv.unread_admin > 0 && (
                      <span className="w-5 h-5 bg-red-500 text-white text-[10px] font-bold rounded-full flex items-center justify-center">
                        {conv.unread_admin}
                      </span>
                    )}
                  </div>
                </div>
                <p className="text-xs text-zinc-500 mt-1 truncate">
                  {conv.last_message_text || "Нет сообщений"}
                </p>
                {conv.last_message_at && (
                  <p className="text-[10px] text-zinc-600 mt-0.5">{formatDate(conv.last_message_at)}</p>
                )}
              </button>
            ))
          )}
        </div>

        {/* Chat area */}
        <div className="flex-1 bg-zinc-900 rounded-xl border border-zinc-800 flex flex-col">
          {!selectedId ? (
            <div className="flex-1 flex items-center justify-center text-zinc-600 text-sm">
              Выберите диалог
            </div>
          ) : (
            <>
              {/* Chat header */}
              <div className="px-4 py-3 border-b border-zinc-800 flex items-center justify-between">
                <div>
                  <span className="text-sm font-medium text-zinc-200">
                    {selectedConv?.user_name ? <MaskedPII type="name" value={selectedConv.user_name} /> : selectedConv?.user_email ? <MaskedPII type="email" value={selectedConv.user_email} /> : "User"}
                  </span>
                  {selectedConv?.user_email && selectedConv?.user_name && (
                    <span className="text-xs text-zinc-500 ml-2"><MaskedPII type="email" value={selectedConv.user_email} /></span>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  {selectedConv?.user_id && (
                    <Link
                      to={`/admin/users/${selectedConv.user_id}`}
                      className="text-xs px-3 py-1 bg-zinc-700/50 text-zinc-300 rounded-full hover:bg-zinc-600/50 transition-colors"
                    >
                      Профиль
                    </Link>
                  )}
                  {selectedConv?.status === "open" && (
                    <button
                      onClick={handleResolve}
                      className="text-xs px-3 py-1 bg-green-900/30 text-green-400 rounded-full hover:bg-green-900/50 transition-colors"
                    >
                      Решено
                    </button>
                  )}
                  <button
                    onClick={handleBlock}
                    className="text-xs px-3 py-1 bg-red-900/30 text-red-400 rounded-full hover:bg-red-900/50 transition-colors"
                    title="Заблокировать пользователя в поддержке"
                  >
                    Бан
                  </button>
                </div>
              </div>

              {/* Messages */}
              <div className="flex-1 overflow-y-auto px-4 py-3 space-y-2">
                {msgLoading ? (
                  <div className="text-center text-zinc-500 py-10">Загрузка...</div>
                ) : messages.length === 0 ? (
                  <div className="text-center text-zinc-600 py-10">Нет сообщений</div>
                ) : (
                  messages.map((msg) => <ChatBubble key={msg.id} msg={msg} />)
                )}
                <div ref={messagesEndRef} />
              </div>

              {/* Reply input */}
              <div className="px-4 py-3 border-t border-zinc-800 flex gap-2 items-end">
                <textarea
                  value={replyText}
                  onChange={(e) => setReplyText(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder="Ответить..."
                  rows={1}
                  className="flex-1 bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-200 placeholder:text-zinc-500 resize-none focus:outline-none focus:border-zinc-500 max-h-24"
                />
                <button
                  onClick={handleSend}
                  disabled={!replyText.trim() || sending}
                  className="px-4 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-500 transition-colors disabled:opacity-30"
                >
                  {sending ? "..." : "→"}
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
