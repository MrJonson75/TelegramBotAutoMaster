from aiogram import Router
from .common import common_router
from .service_booking import service_booking_router
from .my_bookings import my_bookings_router
from .photo_diagnostic import photo_diagnostic_router
from .repair_booking import repair_booking_router
from .admin import admin_router

all_handlers = Router()
all_handlers.include_routers(
    common_router,
    photo_diagnostic_router,
    service_booking_router,
    my_bookings_router,
    repair_booking_router,
    admin_router,
)


__all__ = ['all_handlers']