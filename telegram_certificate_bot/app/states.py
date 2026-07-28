from aiogram.fsm.state import State, StatesGroup


class CertificateFlow(StatesGroup):
    choosing_amount = State()
    waiting_for_comment = State()
    waiting_for_payment = State()


class UsernamePurchaseFlow(StatesGroup):
    choosing_answer = State()


class AdminFlow(StatesGroup):
    waiting_for_certificate_id = State()
    viewing_certificate = State()
    confirming_redeem = State()
