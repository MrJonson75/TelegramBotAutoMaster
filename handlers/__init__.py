from aiogram import Router

from .common import comm_router
from .services import serv_router



all_handlers = Router()
all_handlers.include_routers(
    comm_router,
    serv_router,
)


__all__ = [
    'all_handlers',
           ]