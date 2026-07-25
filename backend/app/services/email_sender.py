import html
import logging
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


def _is_seed_recipient(to_email: str) -> bool:
    """Block emails to seed/demo addresses to prevent bounces and noise."""
    if not to_email:
        return False
    addr = to_email.strip().lower()
    return addr.endswith("@piratex.local") or addr.startswith("seed-")


async def _send_email(to_email: str, subject: str, html: str, brand: str = "Piratex.ai") -> bool:
    """Send an email via Unisender Go. Returns True on success."""
    # Hard guard: never deliver to seed/demo accounts
    if _is_seed_recipient(to_email):
        logger.info("[email] skipped seed recipient: %s (subject=%s)", to_email, subject)
        return True

    if not settings.unisender_api_key:
        logger.info("[email] (dev) to=%s subject=%s", to_email, subject)
        return True

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                "https://go2.unisender.ru/ru/transactional/api/v1/email/send.json",
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "X-API-KEY": settings.unisender_api_key,
                },
                json={
                    "message": {
                        "recipients": [{"email": to_email}],
                        "subject": subject,
                        "from_email": f"noreply@{settings.email_from_domain}",
                        "from_name": brand,
                        "body": {"html": html},
                    }
                },
            )
            resp.raise_for_status()
        return True
    except Exception:
        logger.exception("Failed to send email to %s", to_email)
        return False


def _billing_email_html(title: str, body_lines: list[str], button_text: str | None = None, button_url: str | None = None, brand: str = "Piratex.ai") -> str:
    """Generate a styled billing email HTML."""
    body_html = "".join(
        f"<p style='margin:0 0 12px;font-size:15px;color:#374151;line-height:1.6'>{line}</p>"
        for line in body_lines
    )
    button_html = ""
    if button_text and button_url:
        safe_url = html.escape(button_url, quote=True)
        button_html = (
            "<tr><td align='center' style='padding:0 40px 32px'>"
            f"<a href='{safe_url}' style='"
            "display:inline-block;padding:14px 48px;"
            "background:#0C0C0C;color:#ffffff;text-decoration:none;"
            "border-radius:100px;font-weight:600;font-size:15px;"
            "letter-spacing:0.02em"
            f"'>{button_text}</a>"
            "</td></tr>"
        )
    return (
        "<!DOCTYPE html>"
        "<html><head><meta charset='utf-8'></head>"
        "<body style='margin:0;padding:0;background:#f4f4f5;font-family:-apple-system,BlinkMacSystemFont,\"Segoe UI\",Roboto,sans-serif'>"
        "<table width='100%' cellpadding='0' cellspacing='0' style='background:#f4f4f5;padding:40px 0'>"
        "<tr><td align='center'>"
        "<table width='480' cellpadding='0' cellspacing='0' style='background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.08)'>"
        "<tr><td style='padding:40px 40px 0;text-align:center'>"
        f"<img src='https://piratex.ai/logo.png' alt='{brand}' width='140' style='margin-bottom:24px'>"
        "</td></tr>"
        "<tr><td style='padding:24px 40px 0;text-align:center'>"
        f"<h1 style='margin:0 0 16px;font-size:22px;font-weight:700;color:#1a1a1a'>{title}</h1>"
        "</td></tr>"
        f"<tr><td style='padding:0 40px 24px'>{body_html}</td></tr>"
        f"{button_html}"
        "<tr><td style='padding:0 40px 32px;text-align:center'>"
        "<p style='margin:0;font-size:13px;color:#9ca3af;line-height:1.5'>"
        f"© {brand}</p>"
        "</td></tr>"
        "</table>"
        "</td></tr>"
        "</table>"
        "</body></html>"
    )

EMAIL_STRINGS: dict[str, dict[str, str]] = {
    "ru": {
        "subject": "Код входа: {pin} — {brand}",
        "title": "Вход в {brand}",
        "description": "Введите этот код на сайте или нажмите кнопку ниже",
        "code_label": "Ваш код входа",
        "or_use_link": "Или нажмите кнопку",
        "button": "Войти по ссылке",
        "disclaimer": "Если вы не запрашивали вход, просто проигнорируйте это письмо.",
    },
    "en": {
        "subject": "Sign-in code: {pin} — {brand}",
        "title": "Sign in to {brand}",
        "description": "Enter this code on the website or click the button below",
        "code_label": "Your sign-in code",
        "or_use_link": "Or click the button",
        "button": "Sign in with link",
        "disclaimer": "If you didn't request this, you can safely ignore this email.",
    },
    "fr": {
        "subject": "Code de connexion : {pin} — {brand}",
        "title": "Connexion à {brand}",
        "description": "Entrez ce code sur le site ou cliquez sur le bouton ci-dessous",
        "code_label": "Votre code de connexion",
        "or_use_link": "Ou cliquez sur le bouton",
        "button": "Se connecter par lien",
        "disclaimer": "Si vous n'avez pas demandé cette connexion, ignorez simplement cet e-mail.",
    },
    "pt": {
        "subject": "Código de acesso: {pin} — {brand}",
        "title": "Entrar no {brand}",
        "description": "Digite este código no site ou clique no botão abaixo",
        "code_label": "Seu código de acesso",
        "or_use_link": "Ou clique no botão",
        "button": "Entrar pelo link",
        "disclaimer": "Se você não solicitou isso, ignore este e-mail.",
    },
    "de": {
        "subject": "Anmeldecode: {pin} — {brand}",
        "title": "Anmeldung bei {brand}",
        "description": "Geben Sie diesen Code auf der Website ein oder klicken Sie auf die Schaltfläche unten",
        "code_label": "Ihr Anmeldecode",
        "or_use_link": "Oder klicken Sie auf die Schaltfläche",
        "button": "Per Link anmelden",
        "disclaimer": "Wenn Sie dies nicht angefordert haben, ignorieren Sie diese E-Mail.",
    },
}


def _get_strings(lang: str, brand: str, pin: str = "") -> dict[str, str]:
    raw = EMAIL_STRINGS.get(lang, EMAIL_STRINGS["en"])
    safe_brand = html.escape(brand)
    return {k: v.format(brand=safe_brand, pin=pin) for k, v in raw.items()}


def _pin_digits_html(pin: str) -> str:
    """Render 6-digit PIN as individual styled digit boxes for email."""
    digits = "".join(
        f"<td style='width:44px;height:52px;background:#f4f4f5;border-radius:8px;"
        f"text-align:center;font-size:28px;font-weight:700;color:#1a1a1a;"
        f"font-family:monospace;letter-spacing:0.05em;border:1px solid #e5e7eb'>{d}</td>"
        for d in pin
    )
    return (
        f"<table cellpadding='0' cellspacing='6' style='margin:0 auto'>"
        f"<tr>{digits}</tr></table>"
    )


async def send_magic_link_email(
    to_email: str,
    magic_link_url: str,
    pin: str = "",
    lang: str = "en",
    brand: str = "Piratex.ai",
) -> bool:
    """Send a magic-link email via Unisender Go. Falls back to logging in dev."""
    if not settings.unisender_api_key:
        logger.info("[magic-link] (dev) link for %s: %s  pin=%s", to_email, magic_link_url, pin)
        return True

    s = _get_strings(lang, brand, pin)

    pin_block = ""
    if pin:
        pin_block = (
            "<tr><td style='padding:0 40px 8px;text-align:center'>"
            f"<p style='margin:0 0 12px;font-size:13px;color:#9ca3af;text-transform:uppercase;"
            f"letter-spacing:0.08em'>{s.get('code_label', 'Your code')}</p>"
            f"{_pin_digits_html(pin)}"
            "</td></tr>"
            "<tr><td style='padding:16px 40px 8px;text-align:center'>"
            "<div style='display:flex;align-items:center;justify-content:center;gap:12px'>"
            "<div style='flex:1;height:1px;background:#e5e7eb'></div>"
            f"<span style='font-size:12px;color:#9ca3af;white-space:nowrap'>{s.get('or_use_link', 'or')}</span>"
            "<div style='flex:1;height:1px;background:#e5e7eb'></div>"
            "</div>"
            "</td></tr>"
        )

    email_html = (
        "<!DOCTYPE html>"
        "<html><head><meta charset='utf-8'></head>"
        "<body style='margin:0;padding:0;background:#f4f4f5;font-family:-apple-system,BlinkMacSystemFont,\"Segoe UI\",Roboto,sans-serif'>"
        "<table width='100%' cellpadding='0' cellspacing='0' style='background:#f4f4f5;padding:40px 0'>"
        "<tr><td align='center'>"
        "<table width='480' cellpadding='0' cellspacing='0' style='background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.08)'>"
        "<tr><td style='padding:40px 40px 0;text-align:center'>"
        f"<img src='https://piratex.ai/logo.png' alt='{brand}' width='140' style='margin-bottom:24px'>"
        "</td></tr>"
        "<tr><td style='padding:24px 40px 0;text-align:center'>"
        f"<h1 style='margin:0 0 8px;font-size:22px;font-weight:700;color:#1a1a1a'>{s['title']}</h1>"
        f"<p style='margin:0 0 24px;font-size:15px;color:#6b7280;line-height:1.5'>{s['description']}</p>"
        "</td></tr>"
        f"{pin_block}"
        "<tr><td align='center' style='padding:12px 40px 32px'>"
        f"<a href='{magic_link_url}' style='"
        "display:inline-block;padding:14px 48px;"
        "background:#0C0C0C;color:#ffffff;text-decoration:none;"
        "border-radius:100px;font-weight:600;font-size:15px;"
        "letter-spacing:0.02em"
        f"'>{s['button']}</a>"
        "</td></tr>"
        "<tr><td style='padding:0 40px 32px;text-align:center'>"
        "<p style='margin:0;font-size:13px;color:#9ca3af;line-height:1.5'>"
        f"{s['disclaimer']}</p>"
        "</td></tr>"
        "</table>"
        "</td></tr>"
        "</table>"
        "</body></html>"
    )

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                "https://go2.unisender.ru/ru/transactional/api/v1/email/send.json",
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "X-API-KEY": settings.unisender_api_key,
                },
                json={
                    "message": {
                        "recipients": [{"email": to_email}],
                        "subject": s["subject"],
                        "from_email": f"noreply@{settings.email_from_domain}",
                        "from_name": brand,
                        "body": {"html": email_html},
                    }
                },
            )
            resp.raise_for_status()
        return True
    except Exception:
        logger.exception("Failed to send magic-link email to %s", to_email)
        return False


SUPPORT_REPLY_STRINGS: dict[str, dict[str, str]] = {
    "ru": {
        "subject": "Piratex — вам ответили из поддержки",
        "title": "Ответ от поддержки",
        "button": "Открыть чат",
    },
    "en": {
        "subject": "Piratex — you have a reply from support",
        "title": "Reply from support",
        "button": "Open chat",
    },
    "fr": {
        "subject": "Piratex — réponse du support",
        "title": "Réponse du support",
        "button": "Ouvrir le chat",
    },
    "pt": {
        "subject": "Piratex — resposta do suporte",
        "title": "Resposta do suporte",
        "button": "Abrir chat",
    },
    "de": {
        "subject": "Piratex — Antwort vom Support",
        "title": "Antwort vom Support",
        "button": "Chat öffnen",
    },
}


async def send_support_reply_email(
    to_email: str,
    message_preview: str,
    chat_url: str,
    lang: str = "ru",
) -> bool:
    """Send an email notifying the user that support has replied."""
    s = SUPPORT_REPLY_STRINGS.get(lang, SUPPORT_REPLY_STRINGS["en"])
    preview_escaped = html.escape(message_preview)
    body = [
        f"<em style='color:#6b7280'>«{preview_escaped}»</em>",
    ]
    email_html = _billing_email_html(s["title"], body, s["button"], chat_url)
    return await _send_email(to_email, s["subject"], email_html)


async def send_renewal_reminder_email(
    to_email: str,
    tier_name: str,
    amount: str,
    charge_date: str,
    cancel_url: str,
    lang: str = "ru",
) -> bool:
    """Send a billing renewal reminder email (376-ФЗ: 3 days before charge)."""
    tier_name = html.escape(tier_name)
    amount = html.escape(amount)
    charge_date = html.escape(charge_date)
    if lang == "ru":
        subject = "Piratex.ai — напоминание о продлении подписки"
        title = "Напоминание о списании"
        body = [
            f"Через 3 дня ({charge_date}) произойдёт автоматическое продление вашей подписки <b>{tier_name}</b> на сумму <b>{amount}</b>.",
            "Если вы хотите продолжить пользоваться сервисом — ничего делать не нужно.",
            "Если вы хотите отменить подписку — нажмите кнопку ниже.",
        ]
        button = "Отменить подписку"
    else:
        subject = f"Piratex.ai — subscription renewal reminder"
        title = "Upcoming charge reminder"
        body = [
            f"In 3 days ({charge_date}), your <b>{tier_name}</b> subscription will auto-renew for <b>{amount}</b>.",
            "If you want to continue using the service — no action needed.",
            "If you want to cancel — click the button below.",
        ]
        button = "Cancel subscription"

    html = _billing_email_html(title, body, button, cancel_url)
    return await _send_email(to_email, subject, html)


async def send_renewal_confirmed_email(
    to_email: str,
    tier_name: str,
    amount: str,
    active_until: str,
    settings_url: str,
    lang: str = "ru",
) -> bool:
    """Send a billing confirmation email after successful auto-renewal."""
    tier_name = html.escape(tier_name)
    amount = html.escape(amount)
    active_until = html.escape(active_until)
    if lang == "ru":
        subject = "Piratex.ai — подписка продлена"
        title = "Подписка продлена"
        body = [
            f"Подписка <b>{tier_name}</b> успешно продлена.",
            f"Списано: <b>{amount}</b>",
            f"Активна до: <b>{active_until}</b>",
        ]
        button = "Управление подпиской"
    else:
        subject = f"Piratex.ai — subscription renewed"
        title = "Subscription renewed"
        body = [
            f"Your <b>{tier_name}</b> subscription has been renewed.",
            f"Charged: <b>{amount}</b>",
            f"Active until: <b>{active_until}</b>",
        ]
        button = "Manage subscription"

    html = _billing_email_html(title, body, button, settings_url)
    return await _send_email(to_email, subject, html)


async def send_dunning_email(
    to_email: str,
    tier_name: str,
    day: int,
    settings_url: str,
) -> bool:
    """Send dunning follow-up email for past_due subscriptions.

    day=1: gentle reminder.  day=2: final warning before expiry.
    Day 0 is handled by the existing _notify_user_payment_failed().
    """
    tier_name_esc = html.escape(tier_name)

    if day == 1:
        subject = "Piratex.ai — напоминание об оплате"
        title = "Оплата не прошла"
        body = [
            f"Напоминаем: не удалось списать оплату за подписку <b>{tier_name_esc}</b>.",
            "Обновите способ оплаты, чтобы сохранить доступ к сервису.",
        ]
        button = "Обновить способ оплаты"
    else:
        subject = "Piratex.ai — последний шанс сохранить подписку"
        title = "Подписка будет отменена завтра"
        body = [
            f"Завтра ваша подписка <b>{tier_name_esc}</b> будет отменена из-за проблем с оплатой.",
            "Обновите способ оплаты прямо сейчас, чтобы сохранить доступ.",
        ]
        button = "Обновить способ оплаты"

    email_html = _billing_email_html(title, body, button, settings_url)
    return await _send_email(to_email, subject, email_html)
