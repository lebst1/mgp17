from .start import router as start_router
from .profile import router as profile_router
from .referral import router as referral_router
from .subscription import router as subscription_router
from .admin import router as admin_router
from .save_mode import router as save_mode_router  # 👈 ДОБАВЛЯЕМ
from .settings import router as settings_router

__all__ = [
    "start_router",
    "profile_router",
    "referral_router",
    "subscription_router",
    "admin_router",
    "save_mode_router",  # 👈 ДОБАВЛЯЕМ
    "settings_router",
]