"""Tests for email sender functions."""

import pytest

from app.services.email_sender import send_support_reply_email


@pytest.mark.asyncio
async def test_send_support_reply_email_ru(monkeypatch):
    """Russian support reply email contains correct subject, preview, and button."""
    calls: list[dict] = []

    async def fake_send(to_email, subject, html, brand="ВидеоРентген"):
        calls.append({"to": to_email, "subject": subject, "html": html})
        return True

    monkeypatch.setattr("app.services.email_sender._send_email", fake_send)

    result = await send_support_reply_email(
        to_email="user@test.com",
        message_preview="Привет, мы разобрались с вашей проблемой.",
        chat_url="https://videorentgen.ru/settings?support=open",
        lang="ru",
    )

    assert result is True
    assert len(calls) == 1
    assert "поддержки" in calls[0]["subject"].lower()
    assert "Привет, мы разобрались" in calls[0]["html"]
    assert "https://videorentgen.ru/settings?support=open" in calls[0]["html"]


@pytest.mark.asyncio
async def test_send_support_reply_email_en(monkeypatch):
    """English support reply email contains correct subject and preview."""
    calls: list[dict] = []

    async def fake_send(to_email, subject, html, brand="ВидеоРентген"):
        calls.append({"to": to_email, "subject": subject, "html": html})
        return True

    monkeypatch.setattr("app.services.email_sender._send_email", fake_send)

    result = await send_support_reply_email(
        to_email="user@test.com",
        message_preview="Hello, we fixed your issue.",
        chat_url="https://videorentgen.ru/settings?support=open",
        lang="en",
    )

    assert result is True
    assert len(calls) == 1
    assert "support" in calls[0]["subject"].lower() or "reply" in calls[0]["subject"].lower()
    assert "Hello, we fixed your issue." in calls[0]["html"]


@pytest.mark.asyncio
async def test_send_support_reply_email_escapes_html(monkeypatch):
    """Message preview with HTML is escaped to prevent injection."""
    calls: list[dict] = []

    async def fake_send(to_email, subject, html, brand="ВидеоРентген"):
        calls.append({"html": html})
        return True

    monkeypatch.setattr("app.services.email_sender._send_email", fake_send)

    await send_support_reply_email(
        to_email="user@test.com",
        message_preview="<script>alert('xss')</script>",
        chat_url="https://videorentgen.ru/settings?support=open",
        lang="ru",
    )

    assert "<script>" not in calls[0]["html"]
    assert "&lt;script&gt;" in calls[0]["html"]


@pytest.mark.asyncio
async def test_send_support_reply_email_unknown_lang_falls_back_to_en(monkeypatch):
    """Unknown language falls back to English."""
    calls: list[dict] = []

    async def fake_send(to_email, subject, html, brand="ВидеоРентген"):
        calls.append({"subject": subject})
        return True

    monkeypatch.setattr("app.services.email_sender._send_email", fake_send)

    await send_support_reply_email(
        to_email="user@test.com",
        message_preview="Test",
        chat_url="https://videorentgen.ru/settings?support=open",
        lang="ja",
    )

    # Should use English fallback
    assert "support" in calls[0]["subject"].lower() or "reply" in calls[0]["subject"].lower()
