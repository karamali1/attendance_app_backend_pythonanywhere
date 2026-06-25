from datetime import date, time
from typing import Optional

from pydantic import BaseModel


class CreateCourseRequest(BaseModel):
    course_name: str
    year_of_study: int

class UpdateCourseRequest(BaseModel):
    course_name: str
    year_of_study: int


class CreateSectionRequest(BaseModel):
    section_name: str
    capacity: int
    classroom_id: int


class UpdateSectionRequest(BaseModel):
    section_name: str
    capacity: int
    classroom_id: int
    is_active: bool




# these classes are for the sections schedule

class CreateSectionScheduleRequest(BaseModel):
    weekday: int
    start_time: time
    end_time: time

    repeat_interval_weeks: int = 1

    start_date: date
    end_date: Optional[date] = None
    repeat_for_weeks: Optional[int] = None

    attendance_open_time: time
    attendance_close_time: time


class UpdateSectionScheduleRequest(BaseModel):
    weekday: int
    start_time: time
    end_time: time

    repeat_interval_weeks: int = 1

    start_date: date
    end_date: Optional[date] = None
    repeat_for_weeks: Optional[int] = None

    attendance_open_time: time
    attendance_close_time: time

    is_active: bool = True