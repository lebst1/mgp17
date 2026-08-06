from .start import router as start_router
from .save_mode import router as savemode_router
from .admin import router as admin_router
from .subscription import router as subscription_router
from .profile import router as profile_router
from .referral import router as referral_router

__all__ = [
    "start_router",
    "savemode_router",
    "admin_router",
    "subscription_router",
    "profile_router",
    "referral_router",
]
