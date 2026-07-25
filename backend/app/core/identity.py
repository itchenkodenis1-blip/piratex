"""Core identity management: user lookup/creation, account merging, identity linking.

Provides provider-agnostic functions used by all OAuth and auth flows
(Telegram, Yandex, VK, Google, email magic-link, phone, etc.).
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.feedback import ScriptRating, SupportConversation, SupportMessage
from app.models.identity import AuthIdentity
from app.models.job import Job
from app.models.library import LibraryReel, UserBookmark, UserReelLike, UserScript
from app.models.message import TelegramMessage
from app.models.production import ProductionAsset, ProductionComment, ProductionHistory
from app.models.promo import PromoCodeUsage
from app.models.referral import BonusCredit, Partner, PartnerCommission, Referral
from app.models.subscription import ConsentLog, Payment, Subscription
from app.models.trends import UserTrackedProfile
from app.models.user import User, UserInterestSignal, UserSettings

logger = logging.getLogger(__name__)

# Tier ranking for merge: higher index = better tier
_TIER_RANK = {
    "ANONYMOUS": 0, "REGISTERED": 1, "FREE": 2,
    "START": 3, "PRO": 4, "UNLIMITED": 5,
}


# ---------------------------------------------------------------------------
# Account merging (ghost → real, or old-account → new-account)
# ---------------------------------------------------------------------------


async def merge_ghost_into_user(
    db: AsyncSession,
    ghost: User,
    target: User,
) -> None:
    """Transfer every owned record from *ghost* to *target*, then delete ghost.

    Works for both anonymous ghost merges and real account merges (e.g. old
    Telegram-only account merged into a new email account).

    Handles conflicts for unique-per-user resources by dropping the source's
    copy when the target already owns one for the same entity.
    """
    # Guard: never merge a user into itself
    if ghost.id == target.id:
        logger.warning("[merge] ghost.id == target.id (%s), skipping", ghost.id)
        return

    logger.info("[merge] merging user %s into %s", ghost.id, target.id)

    # -- Jobs --
    await db.execute(
        update(Job).where(Job.user_id == ghost.id).values(user_id=target.id)
    )
    # Flush so subsequent ScriptRating dedup sees reassigned jobs
    await db.flush()

    # -- LibraryReels ownership --
    await db.execute(
        update(LibraryReel)
        .where(LibraryReel.submitted_by == ghost.id)
        .values(submitted_by=target.id)
    )

    # -- UserScripts (unique user_id+library_reel_id — drop ghost's on conflict) --
    conflicting_scripts = select(UserScript.library_reel_id).where(
        UserScript.user_id == target.id,
    )
    await db.execute(
        delete(UserScript).where(
            UserScript.user_id == ghost.id,
            UserScript.library_reel_id.in_(conflicting_scripts),
        )
    )
    await db.execute(
        update(UserScript)
        .where(UserScript.user_id == ghost.id)
        .values(user_id=target.id)
    )
    # Also reassign assignee_id references
    await db.execute(
        update(UserScript)
        .where(UserScript.assignee_id == ghost.id)
        .values(assignee_id=target.id)
    )

    # -- UserBookmarks (unique user_id+library_reel_id) --
    conflicting_bookmarks = select(UserBookmark.library_reel_id).where(
        UserBookmark.user_id == target.id,
    )
    await db.execute(
        delete(UserBookmark).where(
            UserBookmark.user_id == ghost.id,
            UserBookmark.library_reel_id.in_(conflicting_bookmarks),
        )
    )
    await db.execute(
        update(UserBookmark)
        .where(UserBookmark.user_id == ghost.id)
        .values(user_id=target.id)
    )

    # -- UserReelLikes (unique user_id+url) --
    conflicting_likes = select(UserReelLike.url).where(
        UserReelLike.user_id == target.id,
    )
    await db.execute(
        delete(UserReelLike).where(
            UserReelLike.user_id == ghost.id,
            UserReelLike.url.in_(conflicting_likes),
        )
    )
    await db.execute(
        update(UserReelLike)
        .where(UserReelLike.user_id == ghost.id)
        .values(user_id=target.id)
    )

    # -- UserTrackedProfiles (unique user_id+profile_id) --
    conflicting_profiles = select(UserTrackedProfile.profile_id).where(
        UserTrackedProfile.user_id == target.id,
    )
    await db.execute(
        delete(UserTrackedProfile).where(
            UserTrackedProfile.user_id == ghost.id,
            UserTrackedProfile.profile_id.in_(conflicting_profiles),
        )
    )
    await db.execute(
        update(UserTrackedProfile)
        .where(UserTrackedProfile.user_id == ghost.id)
        .values(user_id=target.id)
    )

    # -- UserInterestSignals (no unique — just reassign) --
    await db.execute(
        update(UserInterestSignal)
        .where(UserInterestSignal.user_id == ghost.id)
        .values(user_id=target.id)
    )

    # -- ScriptRatings (unique user_id+job_id — jobs already flushed above) --
    conflicting_ratings = select(ScriptRating.job_id).where(
        ScriptRating.user_id == target.id,
    )
    await db.execute(
        delete(ScriptRating).where(
            ScriptRating.user_id == ghost.id,
            ScriptRating.job_id.in_(conflicting_ratings),
        )
    )
    await db.execute(
        update(ScriptRating)
        .where(ScriptRating.user_id == ghost.id)
        .values(user_id=target.id)
    )

    # -- SupportConversation (unique user_id) --
    target_conv = (await db.execute(
        select(SupportConversation.id).where(
            SupportConversation.user_id == target.id
        )
    )).scalar_one_or_none()
    ghost_conv = (await db.execute(
        select(SupportConversation.id).where(
            SupportConversation.user_id == ghost.id
        )
    )).scalar_one_or_none()
    if ghost_conv:
        if target_conv:
            # Move ghost's messages into target's conversation
            await db.execute(
                update(SupportMessage)
                .where(SupportMessage.conversation_id == ghost_conv)
                .values(conversation_id=target_conv)
            )
            await db.execute(
                delete(SupportConversation).where(
                    SupportConversation.id == ghost_conv
                )
            )
        else:
            await db.execute(
                update(SupportConversation)
                .where(SupportConversation.user_id == ghost.id)
                .values(user_id=target.id)
            )
    # Reassign sender_id on support messages
    await db.execute(
        update(SupportMessage)
        .where(SupportMessage.sender_id == ghost.id)
        .values(sender_id=target.id)
    )

    # -- Subscriptions (partial unique index on active/past_due per user) --
    # Expire ghost's active/past_due subs if target already has one
    target_has_active_sub = (await db.execute(
        select(Subscription.id).where(
            Subscription.user_id == target.id,
            Subscription.status.in_(("active", "past_due")),
        )
    )).scalar_one_or_none()
    if target_has_active_sub:
        await db.execute(
            update(Subscription)
            .where(
                Subscription.user_id == ghost.id,
                Subscription.status.in_(("active", "past_due")),
            )
            .values(status="expired")
        )
    await db.execute(
        update(Subscription)
        .where(Subscription.user_id == ghost.id)
        .values(user_id=target.id)
    )

    # -- Payments & ConsentLog --
    await db.execute(
        update(Payment)
        .where(Payment.user_id == ghost.id)
        .values(user_id=target.id)
    )
    await db.execute(
        update(ConsentLog)
        .where(ConsentLog.user_id == ghost.id)
        .values(user_id=target.id)
    )

    # -- Referrals --
    # referrer_id: ghost referred someone → target now gets credit
    await db.execute(
        update(Referral)
        .where(Referral.referrer_id == ghost.id)
        .values(referrer_id=target.id)
    )
    # referred_id: ghost was referred by someone (unique — drop if target also referred)
    target_referred = (await db.execute(
        select(Referral.id).where(Referral.referred_id == target.id)
    )).scalar_one_or_none()
    if target_referred:
        await db.execute(
            delete(Referral).where(Referral.referred_id == ghost.id)
        )
    else:
        await db.execute(
            update(Referral)
            .where(Referral.referred_id == ghost.id)
            .values(referred_id=target.id)
        )

    # -- Users who were referred BY ghost → now referred by target --
    await db.execute(
        update(User)
        .where(User.referred_by == ghost.id)
        .values(referred_by=target.id)
    )

    # -- BonusCredits --
    await db.execute(
        update(BonusCredit)
        .where(BonusCredit.user_id == ghost.id)
        .values(user_id=target.id)
    )

    # -- Partner (unique user_id) — accumulate totals on conflict --
    ghost_partner_row = (await db.execute(
        select(Partner).where(Partner.user_id == ghost.id)
    )).scalar_one_or_none()
    target_partner_row = (await db.execute(
        select(Partner).where(Partner.user_id == target.id)
    )).scalar_one_or_none()
    if ghost_partner_row:
        if target_partner_row:
            # Merge totals into target, reassign commissions, delete ghost's
            target_partner_row.total_referred += ghost_partner_row.total_referred
            target_partner_row.total_earned_kopecks += ghost_partner_row.total_earned_kopecks
            target_partner_row.total_paid_out_kopecks += ghost_partner_row.total_paid_out_kopecks
            await db.execute(
                update(PartnerCommission)
                .where(PartnerCommission.partner_id == ghost_partner_row.id)
                .values(partner_id=target_partner_row.id)
            )
            await db.execute(
                delete(Partner).where(Partner.id == ghost_partner_row.id)
            )
        else:
            await db.execute(
                update(Partner)
                .where(Partner.user_id == ghost.id)
                .values(user_id=target.id)
            )

    # -- PartnerCommission.referred_user_id (no FK, plain VARCHAR) --
    await db.execute(
        update(PartnerCommission)
        .where(PartnerCommission.referred_user_id == ghost.id)
        .values(referred_user_id=target.id)
    )

    # -- PromoCodeUsage (no FK, plain VARCHAR — delete on conflict) --
    target_promo_ids = select(PromoCodeUsage.promo_code_id).where(
        PromoCodeUsage.user_id == target.id,
    )
    await db.execute(
        delete(PromoCodeUsage).where(
            PromoCodeUsage.user_id == ghost.id,
            PromoCodeUsage.promo_code_id.in_(target_promo_ids),
        )
    )
    await db.execute(
        update(PromoCodeUsage)
        .where(PromoCodeUsage.user_id == ghost.id)
        .values(user_id=target.id)
    )

    # -- TelegramMessages --
    await db.execute(
        update(TelegramMessage)
        .where(TelegramMessage.user_id == ghost.id)
        .values(user_id=target.id)
    )

    # -- Production pipeline --
    await db.execute(
        update(ProductionAsset)
        .where(ProductionAsset.uploaded_by == ghost.id)
        .values(uploaded_by=target.id)
    )
    await db.execute(
        update(ProductionComment)
        .where(ProductionComment.author_id == ghost.id)
        .values(author_id=target.id)
    )
    await db.execute(
        update(ProductionHistory)
        .where(ProductionHistory.triggered_by == ghost.id)
        .values(triggered_by=target.id)
    )

    # -- AuthIdentity records (delete ghost's if same provider+id exists on target) --
    target_identities = (await db.execute(
        select(AuthIdentity.provider, AuthIdentity.provider_user_id).where(
            AuthIdentity.user_id == target.id
        )
    )).all()
    target_identity_keys = {(p, pid) for p, pid in target_identities}

    ghost_identities = (await db.execute(
        select(AuthIdentity).where(AuthIdentity.user_id == ghost.id)
    )).scalars().all()
    for gi in ghost_identities:
        if (gi.provider, gi.provider_user_id) in target_identity_keys:
            await db.execute(
                delete(AuthIdentity).where(AuthIdentity.id == gi.id)
            )
        else:
            gi.user_id = target.id

    # -- UserSettings (keep target's if it exists) --
    target_settings = await db.execute(
        select(UserSettings.id).where(UserSettings.user_id == target.id)
    )
    if target_settings.scalar_one_or_none() is None:
        await db.execute(
            update(UserSettings)
            .where(UserSettings.user_id == ghost.id)
            .values(user_id=target.id)
        )
    else:
        await db.execute(
            delete(UserSettings).where(UserSettings.user_id == ghost.id)
        )

    # -- Merge User-level fields: keep the better value --
    # Tier: take the higher one
    ghost_rank = _TIER_RANK.get(ghost.tier or "", 0)
    target_rank = _TIER_RANK.get(target.tier or "", 0)
    if ghost_rank > target_rank:
        target.tier = ghost.tier

    # Stripe customer: keep if target doesn't have one
    if not target.stripe_customer_id and ghost.stripe_customer_id:
        target.stripe_customer_id = ghost.stripe_customer_id

    # Referral code: keep if target doesn't have one
    if not target.referral_code and ghost.referral_code:
        target.referral_code = ghost.referral_code

    # Telegram fields: keep if target doesn't have them
    if not target.telegram_user_id and ghost.telegram_user_id:
        target.telegram_user_id = ghost.telegram_user_id
    if not target.telegram_username and ghost.telegram_username:
        target.telegram_username = ghost.telegram_username
    if ghost.telegram_subscribed and not target.telegram_subscribed:
        target.telegram_subscribed = True

    # Clear unique fields on ghost before delete to avoid constraint issues
    ghost.email = None
    ghost.telegram_user_id = None
    ghost.stripe_customer_id = None
    ghost.referral_code = None
    ghost.session_token = None
    await db.flush()

    # -- Delete ghost user --
    await db.execute(delete(User).where(User.id == ghost.id))
    logger.info("[merge] user %s merged into %s and deleted", ghost.id, target.id)


# ---------------------------------------------------------------------------
# Lookup / creation (used by every OAuth callback)
# ---------------------------------------------------------------------------


async def find_or_create_user(
    db: AsyncSession,
    *,
    provider: str,
    provider_user_id: str,
    email: str | None = None,
    display_name: str | None = None,
    avatar_url: str | None = None,
    ghost_user: User | None = None,
    raw_profile: dict[str, Any] | None = None,
    access_token: str | None = None,
    refresh_token: str | None = None,
    token_expires_at: datetime | None = None,
) -> tuple[User, AuthIdentity, bool]:
    """Find an existing user by provider identity or create a new one.

    Returns ``(user, identity, is_new)`` where *is_new* is ``True`` when a
    brand-new user was created or a ghost was upgraded in-place.
    """
    # 1. Look up existing identity ----------------------------------------
    result = await db.execute(
        select(AuthIdentity).where(
            AuthIdentity.provider == provider,
            AuthIdentity.provider_user_id == provider_user_id,
        )
    )
    identity: AuthIdentity | None = result.scalar_one_or_none()

    if identity is not None:
        # Update tokens / profile on every login
        identity.access_token = access_token
        identity.refresh_token = refresh_token
        identity.token_expires_at = token_expires_at
        if raw_profile is not None:
            identity.raw_profile = raw_profile
        if email is not None:
            identity.email = email
        if display_name is not None:
            identity.display_name = display_name
        if avatar_url is not None:
            identity.avatar_url = avatar_url
        identity.updated_at = datetime.utcnow()

        user_result = await db.execute(
            select(User).where(User.id == identity.user_id)
        )
        user = user_result.scalar_one()

        # If a ghost was provided, merge it into the existing user
        if ghost_user is not None and ghost_user.id != user.id:
            await merge_ghost_into_user(db, ghost=ghost_user, target=user)

        return user, identity, False

    # 2. No existing identity -- check if a user with this email exists ---
    is_new = True
    existing_user: User | None = None

    if email is not None:
        eu_result = await db.execute(
            select(User).where(User.email == email, User.is_anonymous == False)  # noqa: E712
        )
        existing_user = eu_result.scalar_one_or_none()

    if existing_user is not None:
        # User already exists (registered via another provider) — link new
        # identity to the existing account instead of creating a duplicate.
        user = existing_user
        is_new = False

        if ghost_user is not None and ghost_user.id != user.id:
            await merge_ghost_into_user(db, ghost=ghost_user, target=user)
    elif ghost_user is not None and ghost_user.is_anonymous:
        # Upgrade ghost in place
        ghost_user.is_anonymous = False
        ghost_user.tier = "REGISTERED"
        ghost_user.session_token = None
        if email is not None:
            ghost_user.email = email
        if display_name is not None:
            ghost_user.name = display_name
        user = ghost_user
    else:
        # Create a brand-new user
        user = User(
            is_anonymous=False,
            tier="REGISTERED",
            email=email,
            name=display_name,
        )
        db.add(user)
        await db.flush()  # populate user.id

        # If a non-anonymous ghost was provided, merge it
        if ghost_user is not None and ghost_user.id != user.id:
            await merge_ghost_into_user(db, ghost=ghost_user, target=user)

    # 3. Create the AuthIdentity record -----------------------------------
    identity = AuthIdentity(
        user_id=user.id,
        provider=provider,
        provider_user_id=provider_user_id,
        email=email,
        display_name=display_name,
        avatar_url=avatar_url,
        access_token=access_token,
        refresh_token=refresh_token,
        token_expires_at=token_expires_at,
        raw_profile=raw_profile,
    )
    db.add(identity)

    if is_new:
        try:
            from app.core.showcase_tracker import emit_showcase_event

            await emit_showcase_event("registration")
        except Exception:
            pass  # best-effort, never block auth flow

    return user, identity, is_new


# ---------------------------------------------------------------------------
# Linking an additional provider to an existing user
# ---------------------------------------------------------------------------


async def link_identity(
    db: AsyncSession,
    user: User,
    *,
    provider: str,
    provider_user_id: str,
    email: str | None = None,
    display_name: str | None = None,
    avatar_url: str | None = None,
    access_token: str | None = None,
    refresh_token: str | None = None,
    token_expires_at: datetime | None = None,
    raw_profile: dict[str, Any] | None = None,
) -> AuthIdentity:
    """Link an additional provider identity to *user*.

    Raises :class:`ValueError` if the provider identity already belongs to a
    different user.
    """
    # Check if this provider identity already exists
    result = await db.execute(
        select(AuthIdentity).where(
            AuthIdentity.provider == provider,
            AuthIdentity.provider_user_id == provider_user_id,
        )
    )
    existing: AuthIdentity | None = result.scalar_one_or_none()

    if existing is not None:
        if existing.user_id != user.id:
            raise ValueError(
                f"Identity {provider}:{provider_user_id} is already linked "
                f"to another user ({existing.user_id})"
            )
        # Already linked to this user -- update and return
        existing.email = email if email is not None else existing.email
        existing.display_name = display_name if display_name is not None else existing.display_name
        existing.avatar_url = avatar_url if avatar_url is not None else existing.avatar_url
        existing.access_token = access_token
        existing.refresh_token = refresh_token
        existing.token_expires_at = token_expires_at
        if raw_profile is not None:
            existing.raw_profile = raw_profile
        existing.updated_at = datetime.utcnow()
        return existing

    # Check if user already has this provider linked (different provider_user_id)
    result = await db.execute(
        select(AuthIdentity).where(
            AuthIdentity.user_id == user.id,
            AuthIdentity.provider == provider,
        )
    )
    same_provider: AuthIdentity | None = result.scalar_one_or_none()

    if same_provider is not None:
        # Update existing record with new provider_user_id
        same_provider.provider_user_id = provider_user_id
        same_provider.email = email if email is not None else same_provider.email
        same_provider.display_name = display_name if display_name is not None else same_provider.display_name
        same_provider.avatar_url = avatar_url if avatar_url is not None else same_provider.avatar_url
        same_provider.access_token = access_token
        same_provider.refresh_token = refresh_token
        same_provider.token_expires_at = token_expires_at
        if raw_profile is not None:
            same_provider.raw_profile = raw_profile
        same_provider.updated_at = datetime.utcnow()
        return same_provider

    # Create new identity
    identity = AuthIdentity(
        user_id=user.id,
        provider=provider,
        provider_user_id=provider_user_id,
        email=email,
        display_name=display_name,
        avatar_url=avatar_url,
        access_token=access_token,
        refresh_token=refresh_token,
        token_expires_at=token_expires_at,
        raw_profile=raw_profile,
    )
    db.add(identity)
    return identity
