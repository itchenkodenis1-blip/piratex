"""Classify raw system errors into user-friendly messages.

Raw errors are kept in job.error for debugging.
User-facing messages are sent via WebSocket/Telegram.
"""

import re

# (pattern, user_message) — first match wins
_ERROR_RULES: list[tuple[re.Pattern, str]] = [
    # ── TikTok-specific (already human-readable from _tiktok.py) ──
    (
        re.compile(r"фото-слайдшоу", re.IGNORECASE),
        "Фото-слайдшоу пока не поддерживаются. Отправьте ссылку на видео.",
    ),
    (
        re.compile(r"видео приватное или удалено", re.IGNORECASE),
        "Не удалось получить видео. Возможно, оно приватное или удалено.",
    ),
    (
        re.compile(r"актор не вернул video URL", re.IGNORECASE),
        "Этот формат контента пока не поддерживается. Попробуйте ссылку на обычное видео.",
    ),

    # ── YouTube-specific ──
    (
        re.compile(r"только YouTube Shorts", re.IGNORECASE),
        "Мы анализируем только короткие видео (Shorts, Reels, TikTok). "
        "Обычные видео YouTube пока не поддерживаются.",
    ),
    (
        re.compile(r"не удалось распознать YouTube", re.IGNORECASE),
        "Не удалось распознать ссылку на YouTube. Проверьте URL и попробуйте снова.",
    ),

    # ── Instagram-specific ──
    (
        re.compile(r"Instagram actor returned no video URL", re.IGNORECASE),
        "Не удалось получить видео из Instagram. "
        "Возможно, это фото-пост, Stories или приватный аккаунт.",
    ),

    # ── Duration ──
    (
        re.compile(r"Video is \d+s, max allowed", re.IGNORECASE),
        "Видео слишком длинное. Максимальная длительность — 3 минуты.",
    ),

    # ── Apify empty dataset (the screenshot error) ──
    (
        re.compile(r"returned empty dataset"),
        "Не удалось получить данные о видео. "
        "Проверьте, что ссылка ведёт на публичное видео, и попробуйте снова.",
    ),

    # ── Apify actor failed / bad status ──
    (
        re.compile(r"Apify actor .* failed: status="),
        "Сервис временно недоступен. Попробуйте через несколько минут.",
    ),

    # ── Budget exhausted ──
    (
        re.compile(r"Баланс Apify критически", re.IGNORECASE),
        "Сервис временно перегружен. Попробуйте через несколько минут.",
    ),

    # ── Insufficient data ──
    (
        re.compile(r"кадры и транскрипт пустые", re.IGNORECASE),
        "Не удалось извлечь данные из видео. "
        "Попробуйте другое видео с более чётким контентом.",
    ),

    # ── AI content refusal ──
    (
        re.compile(r"AI отказал.*запрещённ|содержит запрещённые темы", re.IGNORECASE),
        "Контент затрагивает запрещённые темы — ИИ не может создать сценарий "
        "на основе этого видео. Попробуйте другое видео.",
    ),

    # ── AI provider overloaded ──
    (
        re.compile(r"(overloaded_error|529|Overloaded)", re.IGNORECASE),
        "Сервис временно перегружен. Повторная попытка через несколько секунд.",
    ),

    # ── Network / timeout ──
    (
        re.compile(r"(ConnectTimeout|ReadTimeout|ConnectError|httpx)", re.IGNORECASE),
        "Проблема с подключением к серверу. Попробуйте позже.",
    ),
]

# Patterns that indicate transient (retriable) errors — job should be
# requeued automatically instead of showing failure to the user.
_TRANSIENT_PATTERNS: list[re.Pattern] = [
    re.compile(r"overloaded_error|529|Overloaded", re.IGNORECASE),
    re.compile(r"InternalServerError|500", re.IGNORECASE),
    re.compile(r"RateLimitError|rate.limit|429", re.IGNORECASE),
    re.compile(r"ConnectTimeout|ReadTimeout|APITimeoutError|TimeoutError", re.IGNORECASE),
    re.compile(r"ConnectError|ConnectionResetError|BrokenPipeError", re.IGNORECASE),
]


_REFUSAL_PATTERNS: list[re.Pattern] = [
    re.compile(r"I('m| am) not able to (analyze|adapt|provide|process|create)", re.IGNORECASE),
    re.compile(r"I cannot (analyze|adapt|provide|process|create)", re.IGNORECASE),
    re.compile(r"(violates|against) my ethical", re.IGNORECASE),
    re.compile(r"(hate speech|antisemit|racist|extremis|terroris)", re.IGNORECASE),
    re.compile(r"harmful (content|stereotypes|material)", re.IGNORECASE),
    re.compile(r"(conspiracy theor|incitement|violence)", re.IGNORECASE),
]


def is_ai_refusal(raw_text: str) -> bool:
    """Return True if the AI response is a content policy refusal, not actual output."""
    # Only check first 500 chars — refusals are always at the start
    snippet = raw_text[:500]
    return any(p.search(snippet) for p in _REFUSAL_PATTERNS)


def is_transient_error(raw_error: str) -> bool:
    """Return True if the error is transient and the job should be retried."""
    return any(p.search(raw_error) for p in _TRANSIENT_PATTERNS)


def get_user_friendly_error(raw_error: str) -> str:
    """Return a user-friendly error message for the given raw error.

    If no specific rule matches, returns a generic message.
    """
    for pattern, friendly_msg in _ERROR_RULES:
        if pattern.search(raw_error):
            return friendly_msg

    return "Произошла ошибка при обработке видео. Попробуйте ещё раз или выберите другое видео."
