from aiogram import Router
from .admin import admin_router
from .common import common_router
from .my_bookings import my_bookings_router
from .photo_diagnostic import photo_diagnostic_router
from .repair_booking import repair_booking_router
from .service_booking import service_booking_router
from .profile import profile_router

all_handlers = Router()

all_handlers.include_router(admin_router)
all_handlers.include_router(common_router)
all_handlers.include_router(my_bookings_router)
all_handlers.include_router(photo_diagnostic_router)
all_handlers.include_router(repair_booking_router)
all_handlers.include_router(service_booking_router)
all_handlers.include_router(profile_router)