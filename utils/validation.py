from pydantic import BaseModel, constr, PositiveInt, validator, ValidationError
from datetime import datetime
from typing import Optional

class UserInput(BaseModel):
    first_name: constr(min_length=2, max_length=50)
    last_name: Optional[constr(min_length=2, max_length=50)] = None
    phone: Optional[constr(pattern=r"^\+\d{10,15}$")] = None

    @classmethod
    def validate_first_name(cls, value: str):
        """Валидация только имени."""
        try:
            cls(first_name=value, last_name=None, phone=None)
            return value
        except ValidationError as e:
            raise e

    @classmethod
    def validate_last_name(cls, value: str):
        """Валидация только фамилии."""
        try:
            cls(first_name="dummy", last_name=value, phone=None)
            return value
        except ValidationError as e:
            raise e

    @classmethod
    def validate_phone(cls, value: str):
        """Валидация только телефона."""
        try:
            cls(first_name="dummy", last_name=None, phone=value)
            return value
        except ValidationError as e:
            raise e

class AutoInput(BaseModel):
    brand: constr(min_length=2, max_length=50)
    year: PositiveInt
    vin: constr(min_length=17, max_length=17)
    license_plate: constr(min_length=5, max_length=20)

    @validator("year")
    def check_year(cls, v):
        current_year = datetime.today().year
        if v < 1900 or v > current_year:
            raise ValueError(f"Год должен быть между 1900 и {current_year}")
        return v

    @validator("vin")
    def check_vin(cls, v):
        if not v.isalnum():
            raise ValueError("VIN должен содержать только буквы и цифры")
        return v.upper()

    @classmethod
    def validate_brand(cls, value: str):
        """Валидация только марки."""
        try:
            cls(brand=value, year=2000, vin="1HGCM82633A004352", license_plate="A123BC")
            return value
        except ValidationError as e:
            raise e

    @classmethod
    def validate_year(cls, value: int):
        """Валидация только года."""
        try:
            cls(brand="dummy", year=value, vin="1HGCM82633A004352", license_plate="A123BC")
            return value
        except ValidationError as e:
            raise e

    @classmethod
    def validate_vin(cls, value: str):
        """Валидация только VIN."""
        try:
            cls(brand="dummy", year=2000, vin=value, license_plate="A123BC")
            return value
        except ValidationError as e:
            raise e

    @classmethod
    def validate_license_plate(cls, value: str):
        """Валидация только госномера."""
        try:
            cls(brand="dummy", year=2000, vin="1HGCM82633A004352", license_plate=value)
            return value
        except ValidationError as e:
            raise e