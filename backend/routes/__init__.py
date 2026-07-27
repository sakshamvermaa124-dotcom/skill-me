from .admin import router as admin_router
from .students import router as students_router
from .webhooks import router as webhooks_router

__all__ = ["admin_router", "students_router", "webhooks_router"]
