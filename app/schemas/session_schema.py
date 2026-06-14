from pydantic import BaseModel


class CreateSessionRequest(BaseModel):
    classroom_id: int
    session_date: str
    start_time: str
    end_time: str
    attendance_open_time: str
    attendance_close_time: str


class UpdateSessionRequest(BaseModel):
    classroom_id: int
    session_date: str
    start_time: str
    end_time: str
    attendance_open_time: str
    attendance_close_time: str