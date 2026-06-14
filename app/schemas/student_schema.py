from pydantic import BaseModel, EmailStr


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    national_number: str
    university_number: str
    full_name: str
    year_of_study: int


class LoginRequest(BaseModel):
    email: EmailStr
    password: str