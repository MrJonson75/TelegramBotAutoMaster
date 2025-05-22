from aiogram import Router
from .common import common_router
from .photo_diagnostic import photo_diagnostic_router

all_handlers = Router()

all_handlers.include_routers(
    common_router,
    photo_diagnostic_router
)

__all__ = [
    "all_handlers",
]