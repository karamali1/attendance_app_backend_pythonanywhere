from pydantic import BaseModel


class EnrollCourseRequest(BaseModel):
    course_id: int