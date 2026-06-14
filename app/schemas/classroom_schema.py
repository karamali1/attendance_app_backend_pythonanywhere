from pydantic import BaseModel
from typing import Optional


class CreateClassroomRequest(BaseModel):
    name: str
    building: Optional[str] = None
    room_number: Optional[str] = None
    latitude: float
    longitude: float
    allowed_radius_meters: float = 30.0