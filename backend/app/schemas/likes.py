from pydantic import BaseModel


class LikeRequest(BaseModel):
    url: str


class LikedUrlsResponse(BaseModel):
    urls: list[str]
