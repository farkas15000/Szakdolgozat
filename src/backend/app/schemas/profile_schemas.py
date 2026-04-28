# src/backend/app/schemas/profile.py
from pydantic import BaseModel, field_validator


class UpdateDisplayNameRequest(BaseModel):
    display_name: str

    @field_validator("display_name")
    @classmethod
    def not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("A megjelenítési név nem lehet üres.")
        return v.strip()


class UpdatePasswordRequest(BaseModel):
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Az új jelszónak legalább 8 karakter hosszúnak kell lennie.")
        return v


class DeleteAccountRequest(BaseModel):
    password: str  # Megerősítéshez kötelező megadni
