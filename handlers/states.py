from aiogram.fsm.state import State, StatesGroup

class RepairBookingStates(StatesGroup):
    AwaitingAuto = State()
    AwaitingDescription = State()
    AwaitingPhotos = State()
    AwaitingDate = State()
    AwaitingTime = State()
    AwaitingAutoBrand = State()
    AwaitingAutoYear = State()
    AwaitingAutoVin = State()
    AwaitingAutoLicensePlate = State()
    AwaitingAddAnotherAuto = State()

REPAIR_PROGRESS_STEPS = {
    str(RepairBookingStates.AwaitingAuto): 1,
    str(RepairBookingStates.AwaitingDescription): 2,
    str(RepairBookingStates.AwaitingPhotos): 3,
    str(RepairBookingStates.AwaitingDate): 4,
    str(RepairBookingStates.AwaitingTime): 5,
    str(RepairBookingStates.AwaitingAutoBrand): 1,
    str(RepairBookingStates.AwaitingAutoYear): 1,
    str(RepairBookingStates.AwaitingAutoVin): 1,
    str(RepairBookingStates.AwaitingAutoLicensePlate): 1
}

class ServiceBookingStates(StatesGroup):
    AwaitingAuto = State()
    AwaitingService = State()
    AwaitingDate = State()
    AwaitingTime = State()
    AwaitingAutoBrand = State()
    AwaitingAutoYear = State()
    AwaitingAutoVin = State()
    AwaitingAutoLicensePlate = State()

SERVICE_PROGRESS_STEPS = {
    str(ServiceBookingStates.AwaitingAuto): 1,
    str(ServiceBookingStates.AwaitingService): 2,
    str(ServiceBookingStates.AwaitingDate): 3,
    str(ServiceBookingStates.AwaitingTime): 4,
    str(ServiceBookingStates.AwaitingAutoBrand): 1,
    str(ServiceBookingStates.AwaitingAutoYear): 1,
    str(ServiceBookingStates.AwaitingAutoVin): 1,
    str(ServiceBookingStates.AwaitingAutoLicensePlate): 1
}