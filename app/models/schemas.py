from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field


class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    role: str = "operator"  # admin | operator | viewer (ajusta si quieres)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    _id: str
    email: EmailStr
    role: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
