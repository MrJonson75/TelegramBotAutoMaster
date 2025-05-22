from .photo_diagnostic import photo_diagnostic_router
from .common import common_router
from .service_booking import service_booking_router
from .my_bookings import my_bookings_router

all_handlers = photo_diagnostic_router
all_handlers.include_router(common_router)
all_handlers.include_router(service_booking_router)
all_handlers.include_router(my_bookings_router)

__all__ = ['all_handlers']