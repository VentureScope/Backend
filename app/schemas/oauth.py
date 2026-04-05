from pydantic import BaseModel, HttpUrl


class OAuthLoginResponse(BaseModel):
    """Response for OAuth login initiation."""

    authorization_url: HttpUrl
    state: str


class OAuthCallbackRequest(BaseModel):
    """Request schema for OAuth callback."""

    code: str
    state: str


class OAuthCallbackResponse(BaseModel):
    """Response for successful OAuth callback."""

    access_token: str
    token_type: str = "bearer"
    user: dict  # UserResponse data


class OAuthErrorResponse(BaseModel):
    """Response for OAuth errors."""

    error: str
    error_description: str | None = None
    state: str | None = None


class OAuthAccountResponse(BaseModel):
    """OAuth account information."""

    provider: str
    provider_user_id: str
    created_at: str

    class Config:
        from_attributes = True
