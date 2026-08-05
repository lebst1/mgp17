from .start import router as start_router
from .save_mode import router as savemode_router
from .admin import router as admin_router  # ✅ ДОЛЖНО БЫТЬ

__all__ = ["start_router", "savemode_router", "admin_router"]