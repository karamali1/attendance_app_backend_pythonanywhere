from pydantic import BaseModel


class CreateCourseRequest(BaseModel):
    course_name: str
    year_of_study: int

class UpdateCourseRequest(BaseModel):
    course_name: str
    year_of_study: int