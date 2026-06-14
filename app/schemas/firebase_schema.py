from pydantic import BaseModel


class FirebaseLoginRequest(BaseModel):
    firebase_token: str



class FirebaseStudentRegisterRequest(BaseModel):
    firebase_token: str
    full_name: str
    national_number: str
    university_number: str
    year_of_study: int