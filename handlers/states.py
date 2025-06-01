from aiogram.fsm.state import State, StatesGroup

class ServiceBookingStates(StatesGroup):
    AwaitingAuto = State()
    AwaitingService = State()
    AwaitingDate = State()
    AwaitingTime = State()
    AwaitingMasterTime = State()
    AwaitingMasterResponse = State()
    AwaitingUserConfirmation = State()

class RepairBookingStates(StatesGroup):
    AwaitingAuto = State()
    AwaitingProblemDescription = State()
    AwaitingPhotos = State()
    AwaitingDate = State()
    AwaitingTime = State()
    AwaitingMasterEvaluation = State()
    AwaitingMasterRejectionReason = State()
    AwaitingMasterTime = State()
    AwaitingMasterTimeSelection = State()  # Новое состояние для выбора времени мастером
    AwaitingUserConfirmation = State()

SERVICE_PROGRESS_STEPS = {
    ServiceBookingStates.AwaitingAuto: 1,
    ServiceBookingStates.AwaitingService: 2,
    ServiceBookingStates.AwaitingDate: 3,
    ServiceBookingStates.AwaitingTime: 4,
}

REPAIR_PROGRESS_STEPS = {
    RepairBookingStates.AwaitingAuto: 1,
    RepairBookingStates.AwaitingProblemDescription: 2,
    RepairBookingStates.AwaitingPhotos: 3,
    RepairBookingStates.AwaitingDate: 4,
    RepairBookingStates.AwaitingTime: 5,
}