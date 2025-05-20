from aiogram import Router

from .common import comm_router



all_handlers = Router()
all_handlers.include_routers(
    comm_router,
)


__all__ = [
    'all_handlers',
           ]