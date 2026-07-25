import { useCallback, useEffect, useRef, useState } from "react";
import {
  getSupportConversation,
  getSupportUnreadCount,
  presignSupportUpload,
  sendSupportMessage,
  type SupportMessage,
} from "../../api/client";
import { useTranslation } from "../../i18n";

function formatTime(dt: string): string {
  return new Date(dt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

/** Founder avatar served from backend (S3) */
const FOUNDER_AVATAR = "/api/support/founder-avatar";

function FounderAvatar({ className = "" }: { className?: string }) {
  return (
    <img
      src={FOUNDER_AVATAR}
      alt="Support"
      className={`w-7 h-7 rounded-full object-cover shrink-0 ${className}`}
    />
  );
}

/** Typing indicator — three bouncing dots */
function TypingIndicator({ name }: { name: string }) {
  return (
    <div className="flex items-end gap-2">
      <FounderAvatar className="mb-0.5" />
      <div>
        <p className="text-[11px] text-cream-muted/60 mb-1 ml-1">{name}</p>
        <div className="bg-zinc-800 px-4 py-3 rounded-2xl rounded-bl-md inline-flex items-center gap-1">
          <span className="w-1.5 h-1.5 bg-cream-muted/50 rounded-full animate-bounce [animation-delay:0ms]" />
          <span className="w-1.5 h-1.5 bg-cream-muted/50 rounded-full animate-bounce [animation-delay:150ms]" />
          <span className="w-1.5 h-1.5 bg-cream-muted/50 rounded-full animate-bounce [animation-delay:300ms]" />
        </div>
      </div>
    </div>
  );
}

interface ChatBubbleProps {
  msg: SupportMessage;
  showAvatar?: boolean;
  founderName: string;
}

function ChatBubble({ msg, showAvatar, founderName }: ChatBubbleProps) {
  const isUser = msg.sender_type === "user";
  const isAdmin = msg.sender_type === "admin";

  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      {isAdmin && (
        <div className="shrink-0 mr-2 self-end mb-0.5">
          {showAvatar ? <FounderAvatar /> : <div className="w-7" />}
        </div>
      )}
      <div className="max-w-[75%]">
        {isAdmin && showAvatar && (
          <p className="text-[11px] text-cream-muted/60 mb-1 ml-1">{founderName}</p>
        )}
        <div
          className={`px-3 py-2 rounded-2xl text-sm whitespace-pre-wrap break-words ${
            isUser
              ? "bg-blue-600/30 text-cream rounded-br-md"
              : "bg-zinc-800 text-cream rounded-bl-md"
          }`}
        >
          {msg.image_key && (
            <img
              src={`/api/support/image/${msg.image_key}`}
              alt="screenshot"
              className="max-w-full rounded-lg mb-1 cursor-pointer"
              onClick={() => window.open(`/api/support/image/${msg.image_key}`, "_blank")}
            />
          )}
          {msg.text && <p>{msg.text}</p>}
          <p className={`text-[10px] mt-1 ${isUser ? "text-blue-300/60" : "text-zinc-500"}`}>
            {formatTime(msg.created_at)}
          </p>
        </div>
      </div>
    </div>
  );
}

/** Should we show avatar on this admin message? Show on first admin msg or when previous was from user */
function shouldShowAvatar(messages: SupportMessage[], index: number): boolean {
  const msg = messages[index];
  if (msg.sender_type !== "admin") return false;
  if (index === 0) return true;
  return messages[index - 1].sender_type !== "admin";
}

const WELCOME_SEEN_KEY = "piratex_support_welcome_seen";

export function ChatWidget() {
  const { t } = useTranslation();
  const [isOpen, setIsOpen] = useState(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get("support") === "open") {
      params.delete("support");
      const newUrl = params.toString()
        ? `${window.location.pathname}?${params}`
        : window.location.pathname;
      window.history.replaceState({}, "", newUrl);
      return true;
    }
    return false;
  });
  const [messages, setMessages] = useState<SupportMessage[]>([]);
  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);
  const [unread, setUnread] = useState(0);
  const [consentGiven, setConsentGiven] = useState(false);
  const [consentChecked, setConsentChecked] = useState(false);
  const [hasConversation, setHasConversation] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [showTyping, setShowTyping] = useState(false);
  const [typingDone, setTypingDone] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const pendingMessagesRef = useRef<SupportMessage[]>([]);

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  // Load conversation on open + poll every 5s while open
  useEffect(() => {
    if (!isOpen) return;
    let cancelled = false;
    const welcomeSeen = localStorage.getItem(WELCOME_SEEN_KEY) === "1";

    const load = () =>
      getSupportConversation().then((conv) => {
        if (cancelled) return;
        const isWelcomeOnly =
          conv.messages.length === 1 &&
          conv.messages[0].sender_type === "admin" &&
          !welcomeSeen;

        if (isWelcomeOnly && !typingDone) {
          // First time seeing the welcome — show typing animation
          pendingMessagesRef.current = conv.messages;
          setMessages([]);
          setShowTyping(true);
          setHasConversation(true);
          setConsentGiven(false); // Welcome from admin doesn't count as user consent
        } else {
          setMessages(conv.messages);
          setHasConversation(conv.id !== "");
          if (conv.id !== "" && conv.messages.some((m) => m.sender_type === "user")) {
            setConsentGiven(true);
          }
        }
      }).catch(() => {});
    load();
    const interval = setInterval(load, 5_000);
    return () => { cancelled = true; clearInterval(interval); };
  }, [isOpen, typingDone]);

  // Typing animation timer — show dots for 2.5s, then reveal message
  useEffect(() => {
    if (!showTyping) return;
    const timer = setTimeout(() => {
      setShowTyping(false);
      setTypingDone(true);
      setMessages(pendingMessagesRef.current);
      localStorage.setItem(WELCOME_SEEN_KEY, "1");
    }, 2500);
    return () => clearTimeout(timer);
  }, [showTyping]);

  // Scroll on new messages or typing state change
  useEffect(() => {
    scrollToBottom();
  }, [messages, showTyping, scrollToBottom]);

  // Poll unread count (only if authenticated)
  useEffect(() => {
    if (!localStorage.getItem("token")) return;
    const poll = () => getSupportUnreadCount().then(setUnread).catch(() => {});
    poll();
    const interval = setInterval(poll, 30_000);
    return () => clearInterval(interval);
  }, []);

  // WebSocket for real-time messages
  useEffect(() => {
    if (!isOpen) return;
    const token = localStorage.getItem("token");
    if (!token) return;

    // Decode user_id from JWT (simple base64 decode of payload)
    try {
      const payload = JSON.parse(atob(token.split(".")[1]));
      const userId = payload.sub;
      if (!userId) return;

      const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
      const ws = new WebSocket(`${protocol}//${window.location.host}/ws/support/${userId}?token=${token}`);
      wsRef.current = ws;

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.type === "new_message" && data.message) {
            setMessages((prev) => [...prev, data.message]);
            setUnread(0);
          }
        } catch { /* ignore */ }
      };

      return () => {
        ws.close();
        wsRef.current = null;
      };
    } catch { return; }
  }, [isOpen]);

  const handleSend = async () => {
    const trimmed = text.trim();
    if (!trimmed || sending) return;
    if (!hasConversation && !consentChecked) return;

    setSending(true);
    try {
      const msg = await sendSupportMessage(trimmed);
      setMessages((prev) => [...prev, msg]);
      setText("");
      if (textareaRef.current) textareaRef.current.style.height = "auto";
      setHasConversation(true);
      setConsentGiven(true);
    } catch { /* ignore */ }
    setSending(false);
  };

  const autoResize = useCallback(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = `${ta.scrollHeight}px`;
  }, []);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (!file.type.startsWith("image/")) return;

    setUploading(true);
    try {
      const { upload_url, image_key } = await presignSupportUpload(file.name, file.type);
      await fetch(upload_url, { method: "PUT", body: file, headers: { "Content-Type": file.type } });
      const msg = await sendSupportMessage(undefined, image_key);
      setMessages((prev) => [...prev, msg]);
      setHasConversation(true);
      setConsentGiven(true);
    } catch { /* ignore */ }
    setUploading(false);
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  // Determine if consent is needed: user hasn't sent any messages yet
  const userHasSentMessage = consentGiven || messages.some((m) => m.sender_type === "user");

  return (
    <>
      {/* Floating button */}
      <button
        onClick={() => { setIsOpen(!isOpen); if (!isOpen) setUnread(0); }}
        className="fixed bottom-5 right-5 z-50 w-14 h-14 rounded-full bg-cream text-[#0C0C0C] shadow-lg hover:bg-cream-dim transition-all flex items-center justify-center"
      >
        {isOpen ? (
          <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
          </svg>
        ) : (
          <>
            <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
            </svg>
            {unread > 0 && (
              <span className="absolute -top-1 -right-1 w-5 h-5 bg-red-500 text-white text-[10px] font-bold rounded-full flex items-center justify-center">
                {unread > 9 ? "9+" : unread}
              </span>
            )}
          </>
        )}
      </button>

      {/* Chat panel */}
      {isOpen && (
        <div className="fixed bottom-24 right-5 z-50 w-[360px] h-[500px] max-h-[70vh] bg-[#0C0C0C] border border-border-subtle rounded-2xl shadow-2xl flex flex-col overflow-hidden">
          {/* Header */}
          <div className="px-4 py-3 border-b border-border-subtle flex items-center gap-2">
            <FounderAvatar className="w-6 h-6" />
            <div>
              <h3 className="text-sm font-medium text-cream">{t.support_welcome_name}</h3>
              <p className="text-[10px] text-cream-muted/50">{t.support_chat_title}</p>
            </div>
            <div className="w-2 h-2 rounded-full bg-green-500 ml-auto" />
          </div>

          {/* Messages */}
          <div className="flex-1 overflow-y-auto px-3 py-3 space-y-2 scrollbar-hide">
            {messages.length === 0 && !showTyping && (
              <p className="text-center text-cream-muted/50 text-sm py-10">
                {t.support_empty}
              </p>
            )}
            {messages.map((msg, i) => (
              <ChatBubble
                key={msg.id}
                msg={msg}
                showAvatar={shouldShowAvatar(messages, i)}
                founderName={t.support_welcome_name}
              />
            ))}
            {showTyping && <TypingIndicator name={t.support_welcome_name} />}
            <div ref={messagesEndRef} />
          </div>

          {/* Consent checkbox (only before user sends first message) */}
          {!userHasSentMessage && (
            <div className="px-3 pb-1">
              <label className="flex items-start gap-2 text-[11px] text-cream-muted cursor-pointer">
                <input
                  type="checkbox"
                  checked={consentChecked}
                  onChange={(e) => setConsentChecked(e.target.checked)}
                  className="mt-0.5 accent-cream"
                />
                <span>
                  {t.support_consent}{" "}
                  <a href="/privacy" target="_blank" className="underline hover:text-cream">
                    {t.support_consent_link}
                  </a>
                </span>
              </label>
            </div>
          )}

          {/* Input */}
          <div className="px-3 py-2 border-t border-border-subtle flex items-end gap-2">
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              className="hidden"
              onChange={handleFileUpload}
            />
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              disabled={uploading || (!userHasSentMessage && !consentChecked)}
              className="text-cream-muted hover:text-cream transition-colors disabled:opacity-30 shrink-0 pb-1"
              title="Attach screenshot"
            >
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M18.375 12.739l-7.693 7.693a4.5 4.5 0 01-6.364-6.364l10.94-10.94A3 3 0 1119.5 7.372L8.552 18.32m.009-.01l-.01.01m5.699-9.941l-7.81 7.81a1.5 1.5 0 002.112 2.13" />
              </svg>
            </button>
            <textarea
              ref={textareaRef}
              value={text}
              onChange={(e) => { setText(e.target.value); autoResize(); }}
              onKeyDown={handleKeyDown}
              placeholder={t.support_placeholder}
              rows={2}
              className="flex-1 bg-white/[0.03] border border-border-subtle rounded-lg px-3 py-2 text-sm text-cream placeholder:text-cream-muted/50 resize-none focus:outline-none focus:border-cream-muted/40 max-h-32"
            />
            <button
              type="button"
              onClick={handleSend}
              disabled={!text.trim() || sending || (!userHasSentMessage && !consentChecked)}
              className="text-cream hover:text-white transition-colors disabled:opacity-30 shrink-0 pb-1"
            >
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 12L3.269 3.126A59.768 59.768 0 0121.485 12 59.77 59.77 0 013.27 20.876L5.999 12zm0 0h7.5" />
              </svg>
            </button>
          </div>
        </div>
      )}
    </>
  );
}
