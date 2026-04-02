from pydantic import BaseModel, EmailStr


class UserCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: str | None = None
    career_interest: str | None = None
    role: str = "professional"


class UserResponse(BaseModel):
    id: str
    email: str
    full_name: str | None
    github_username: str | None
    career_interest: str | None
    role: str

    class Config:
        from_attributes = True


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
