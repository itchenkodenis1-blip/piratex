import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import MaskedPII from "./MaskedPII";
import { adminGetConversation, adminListConversations, adminSendMessage } from "../../api/client";
import type { AdminConversation, AdminMessage } from "../../types";

function formatTime(dt: string) {
  return new Date(dt).toLocaleString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatTimeShort(dt: string) {
  return new Date(dt).toLocaleTimeString("ru-RU", {
    hour: "2-digit",
    minute: "2-digit",
  });
}

function ConversationItem({
  conv,
  active,
  onClick,
}: {
  conv: AdminConversation;
  active: boolean;
  onClick: () => void;
}) {
  const name = conv.telegram_name || conv.telegram_username || conv.telegram_user_id;
  const initials = (conv.telegram_name || "U")[0].toUpperCase();

  return (
    <button
      onClick={onClick}
      className={`w-full text-left px-3 py-3 flex items-start gap-3 transition-colors border-b border-zinc-800/50 ${
        active ? "bg-zinc-800" : "hover:bg-zinc-800/30"
      }`}
    >
      {/* Avatar */}
      <div className="w-9 h-9 rounded-full bg-zinc-700 flex items-center justify-center flex-shrink-0">
        <span className="text-xs font-medium text-zinc-300">{initials}</span>
      </div>

      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between gap-2">
          <span className="text-sm text-zinc-200 truncate font-medium"><MaskedPII type="name" value={name} /></span>
          {conv.last_message_at && (
            <span className="text-[10px] text-zinc-500 flex-shrink-0">
              {formatTime(conv.last_message_at)}
            </span>
          )}
        </div>
        {conv.telegram_username && (
          <div className="text-[11px] text-zinc-500"><MaskedPII type="telegram" value={conv.telegram_username} /></div>
        )}
        {conv.last_message_text && (
          <div className="text-xs text-zinc-500 truncate mt-0.5">
            {conv.last_message_text.slice(0, 60)}
          </div>
        )}
        <div className="text-[10px] text-zinc-600 mt-0.5">
          {conv.message_count} сообщ.
        </div>
      </div>
    </button>
  );
}

function ChatBubble({ msg }: { msg: AdminMessage }) {
  const isIncoming = msg.direction === "in";

  return (
    <div className={`flex ${isIncoming ? "justify-start" : "justify-end"} mb-2`}>
      <div
        className={`max-w-[75%] rounded-2xl px-4 py-2.5 ${
          isIncoming
            ? "bg-zinc-800 text-zinc-200 rounded-bl-md"
            : "bg-blue-900/40 text-blue-100 rounded-br-md"
        }`}
      >
        <div className="text-sm whitespace-pre-wrap break-words">{msg.text}</div>
        <div
          className={`text-[10px] mt-1 ${
            isIncoming ? "text-zinc-500" : "text-blue-400/60"
          }`}
        >
          {formatTimeShort(msg.created_at)}
        </div>
      </div>
    </div>
  );
}

export function AdminMessages() {
  const [conversations, setConversations] = useState<AdminConversation[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [messages, setMessages] = useState<AdminMessage[]>([]);
  const [messagesLoading, setMessagesLoading] = useState(false);

  const [hidden, setHidden] = useState(() => {
    return localStorage.getItem("admin_messages_hidden") === "true";
  });

  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);

  const chatEndRef = useRef<HTMLDivElement>(null);
  const perPage = 50;
  const totalPages = Math.ceil(total / perPage);

  // Load conversations
  useEffect(() => {
    setLoading(true);
    adminListConversations({
      q: search || undefined,
      page,
      per_page: perPage,
    })
      .then((res) => {
        setConversations(res.items);
        setTotal(res.total);
      })
      .finally(() => setLoading(false));
  }, [search, page]);

  // Load messages when conversation selected
  useEffect(() => {
    if (!selectedId) {
      setMessages([]);
      return;
    }
    setMessagesLoading(true);
    adminGetConversation(selectedId)
      .then(setMessages)
      .finally(() => setMessagesLoading(false));
  }, [selectedId]);

  // Scroll to bottom when messages load
  useEffect(() => {
    if (messages.length > 0) {
      chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages]);

  function toggleHidden() {
    const next = !hidden;
    setHidden(next);
    localStorage.setItem("admin_messages_hidden", String(next));
  }

  async function handleSend() {
    if (!selectedId || !draft.trim() || sending) return;
    setSending(true);
    try {
      const newMsg = await adminSendMessage(selectedId, draft.trim());
      setMessages((prev) => [...prev, newMsg]);
      setDraft("");
    } catch {
      // silent
    } finally {
      setSending(false);
    }
  }

  const selectedConv = conversations.find((c) => c.telegram_user_id === selectedId);

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-serif font-medium text-zinc-100">Сообщения</h1>
        <button
          onClick={toggleHidden}
          className={`text-xs px-3 py-1.5 rounded-lg border transition-colors ${
            hidden
              ? "border-zinc-700 text-zinc-500 hover:text-zinc-300 hover:border-zinc-600"
              : "border-zinc-600 text-zinc-300 hover:bg-zinc-800"
          }`}
        >
          {hidden ? "Показать историю" : "Скрыть историю"}
        </button>
      </div>

      {hidden ? (
        <div className="text-zinc-500 text-sm py-12 text-center">
          История сообщений скрыта. Нажмите «Показать историю», чтобы увидеть переписки.
        </div>
      ) : (
        <div className="flex border border-zinc-800 rounded-xl overflow-hidden" style={{ height: "calc(100vh - 160px)" }}>
          {/* Left: Conversations list */}
          <div className="w-[320px] border-r border-zinc-800 flex flex-col bg-zinc-900/50">
            {/* Search */}
            <div className="p-3 border-b border-zinc-800">
              <input
                type="text"
                placeholder="Поиск по имени..."
                value={search}
                onChange={(e) => {
                  setSearch(e.target.value);
                  setPage(1);
                }}
                className="w-full bg-zinc-800 border border-zinc-700 text-zinc-300 text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-zinc-500 placeholder:text-zinc-600"
              />
              <div className="text-[10px] text-zinc-600 mt-1.5 px-1">
                {total} диалогов
              </div>
            </div>

            {/* List */}
            <div className="flex-1 overflow-y-auto">
              {loading ? (
                <div className="text-zinc-500 text-sm py-8 text-center">Загрузка...</div>
              ) : conversations.length === 0 ? (
                <div className="text-zinc-500 text-sm py-8 text-center">Нет диалогов</div>
              ) : (
                conversations.map((conv) => (
                  <ConversationItem
                    key={conv.telegram_user_id}
                    conv={conv}
                    active={conv.telegram_user_id === selectedId}
                    onClick={() => setSelectedId(conv.telegram_user_id)}
                  />
                ))
              )}
            </div>

            {/* Pagination */}
            {totalPages > 1 && (
              <div className="flex items-center justify-between px-3 py-2 border-t border-zinc-800 text-xs text-zinc-500">
                <button
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={page === 1}
                  className="hover:text-zinc-300 disabled:opacity-40 transition-colors"
                >
                  ←
                </button>
                <span>{page} / {totalPages}</span>
                <button
                  onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                  disabled={page === totalPages}
                  className="hover:text-zinc-300 disabled:opacity-40 transition-colors"
                >
                  →
                </button>
              </div>
            )}
          </div>

          {/* Right: Chat history */}
          <div className="flex-1 flex flex-col bg-[#0C0C0C]">
            {selectedId && selectedConv ? (
              <>
                {/* Chat header */}
                <div className="px-5 py-3 border-b border-zinc-800 flex items-center gap-3">
                  <div className="w-8 h-8 rounded-full bg-zinc-700 flex items-center justify-center">
                    <span className="text-xs font-medium text-zinc-300">
                      {(selectedConv.telegram_name || "U")[0].toUpperCase()}
                    </span>
                  </div>
                  <div>
                    <div className="text-sm font-medium text-zinc-200">
                      <MaskedPII type="name" value={selectedConv.telegram_name} fallback={selectedConv.telegram_user_id} />
                    </div>
                    {selectedConv.telegram_username && (
                      <div className="text-[11px] text-zinc-500"><MaskedPII type="telegram" value={selectedConv.telegram_username} /></div>
                    )}
                  </div>
                  <div className="ml-auto flex items-center gap-2">
                    {selectedConv.user_id && (
                      <Link
                        to={`/admin/users/${selectedConv.user_id}`}
                        className="text-xs px-2.5 py-0.5 bg-zinc-700/50 text-zinc-300 rounded-full hover:bg-zinc-600/50 transition-colors"
                      >
                        Профиль
                      </Link>
                    )}
                    <span className="text-[11px] text-zinc-600">
                      {selectedConv.message_count} сообщ.
                    </span>
                  </div>
                </div>

                {/* Messages */}
                <div className="flex-1 overflow-y-auto px-5 py-4">
                  {messagesLoading ? (
                    <div className="text-zinc-500 text-sm py-8 text-center">Загрузка...</div>
                  ) : messages.length === 0 ? (
                    <div className="text-zinc-500 text-sm py-8 text-center">Нет сообщений</div>
                  ) : (
                    <>
                      {messages.map((msg) => (
                        <ChatBubble key={msg.id} msg={msg} />
                      ))}
                      <div ref={chatEndRef} />
                    </>
                  )}
                </div>

                {/* Input */}
                <div className="px-4 py-3 border-t border-zinc-800 flex items-end gap-2">
                  <textarea
                    value={draft}
                    onChange={(e) => setDraft(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && !e.shiftKey) {
                        e.preventDefault();
                        handleSend();
                      }
                    }}
                    placeholder="Написать сообщение..."
                    rows={1}
                    className="flex-1 bg-zinc-800 border border-zinc-700 text-zinc-200 text-sm rounded-xl px-4 py-2.5 resize-none focus:outline-none focus:border-zinc-500 placeholder:text-zinc-600"
                  />
                  <button
                    onClick={handleSend}
                    disabled={!draft.trim() || sending}
                    className="px-4 py-2.5 bg-blue-600 hover:bg-blue-500 disabled:opacity-40 disabled:hover:bg-blue-600 text-white text-sm rounded-xl transition-colors flex-shrink-0"
                  >
                    {sending ? "..." : "→"}
                  </button>
                </div>
              </>
            ) : (
              <div className="flex-1 flex items-center justify-center">
                <div className="text-center">
                  <div className="text-zinc-600 text-3xl mb-3">💬</div>
                  <div className="text-zinc-500 text-sm">Выберите диалог</div>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
