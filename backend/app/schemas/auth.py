from pydantic import BaseModel


class UserResponse(BaseModel):
    id: str
    email: str | None = None
    name: str | None = None
    is_anonymous: bool = False
    email_verified: bool = False
    auth_provider: str | None = None
    tier: str = "FREE"
    telegram_user_id: str | None = None
    telegram_subscribed: bool = False
    auth_providers: list[str] = []

    model_config = {"from_attributes": True}
