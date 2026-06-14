from pydantic import BaseModel


class SaveFcmTokenRequest(BaseModel):
    fcm_token: str
    platform: str | None = None