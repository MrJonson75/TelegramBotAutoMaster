import re

def validate_phone(phone: str) -> bool:
    """Проверяет корректность номера телефона"""
    pattern = r"^(\+7|7|8)?[\s\-]?\(?[489][0-9]{2}\)?[\s\-]?[0-9]{3}[\s\-]?[0-9]{2}[\s\-]?[0-9]{2}$"
    return bool(re.match(pattern, phone))

def validate_vin(vin: str) -> bool:
    """Проверяет корректность VIN-номера"""
    return len(vin) == 17 and all(c.isalnum() for c in vin)