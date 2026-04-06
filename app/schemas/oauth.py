from pydantic import BaseModel, Field, HttpUrl


class GitHubLanguageBreakdown(BaseModel):
    """Language usage for a repository."""

    name: str
    size: int


class GitHubRepositorySummary(BaseModel):
    """Normalized GitHub repository metadata used by the sync endpoint."""

    name: str
    description: str | None = None
    stargazer_count: int = 0
    fork_count: int = 0
    is_private: bool = False
    is_fork: bool = False
    pushed_at: str | None = None
    updated_at: str | None = None
    primary_language: str | None = None
    languages: list[GitHubLanguageBreakdown] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)


class GitHubContributionSummary(BaseModel):
    """Aggregated GitHub contribution data."""

    total_contributions: int = 0
    total_pull_requests: int = 0
    total_issue_contributions: int = 0
    total_repositories_with_contributed_commits: int = 0


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


class GitHubProfileSyncResponse(BaseModel):
    """Response for the GitHub profile sync endpoint."""

    status: str
    message: str
    github_connected: bool = False
    github_username: str | None = None
    full_name: str | None = None
    profile_picture_url: str | None = None
    required_scopes: list[str] = Field(default_factory=list)
    authorization_url: HttpUrl | None = None
    state: str | None = None
    repositories: list[GitHubRepositorySummary] = Field(default_factory=list)
    contributions: GitHubContributionSummary | None = None
