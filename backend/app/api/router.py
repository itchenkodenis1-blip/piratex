from fastapi import APIRouter

from app.api.auth import router as auth_router
from app.api.billing import router as billing_router
from app.api.magic_link import router as magic_link_router
from app.api.oauth import router as oauth_router
from app.api.phone_auth import router as phone_auth_router
from app.api.jobs import router as jobs_router
from app.api.likes import likes_router
from app.api.library import library_router
from app.api.pipeline import router as pipeline_router
# DISABLED: referral program temporarily closed (abuse via bot farming)
# from app.api.referral import router as referral_router
from app.api.refine import router as refine_router
from app.api.settings import router as settings_router
from app.api.share import router as share_router
from app.api.support import router as support_router
from app.api.admin import router as admin_router
from app.api.admin_trends import router as admin_trends_router
from app.api.telegram import router as telegram_router
from app.api.niches import router as niches_router
from app.api.shooting_queue import router as shooting_queue_router
from app.api.trends import trends_router

api_router = APIRouter()
api_router.include_router(admin_router, prefix="/admin", tags=["admin"])
api_router.include_router(admin_trends_router, prefix="/admin/trend-watching", tags=["admin-trends"])
api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
api_router.include_router(billing_router, prefix="/billing", tags=["billing"])
api_router.include_router(jobs_router, prefix="/jobs", tags=["jobs"])
api_router.include_router(likes_router, prefix="/likes", tags=["likes"])
api_router.include_router(refine_router, prefix="/jobs", tags=["refine"])
# DISABLED: referral program temporarily closed (abuse via bot farming)
# api_router.include_router(referral_router, prefix="/referral", tags=["referral"])
api_router.include_router(settings_router, prefix="/settings", tags=["settings"])
api_router.include_router(library_router)
api_router.include_router(pipeline_router, prefix="/pipeline", tags=["pipeline"])
api_router.include_router(share_router, prefix="/share", tags=["share"])
api_router.include_router(support_router, prefix="/support", tags=["support"])
api_router.include_router(telegram_router, prefix="/telegram", tags=["telegram"])
api_router.include_router(oauth_router, prefix="/auth/oauth", tags=["oauth"])
api_router.include_router(magic_link_router, prefix="/auth/magic-link", tags=["magic-link"])
api_router.include_router(phone_auth_router, prefix="/auth/phone", tags=["phone-auth"])
api_router.include_router(niches_router, tags=["niches"])
api_router.include_router(shooting_queue_router, prefix="/shooting-queue", tags=["shooting-queue"])
api_router.include_router(trends_router)
