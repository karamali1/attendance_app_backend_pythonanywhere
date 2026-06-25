import os

from fastapi import FastAPI

from app.core.config import (
    ENROLLMENTS_DIR,
    UPLOAD_DIR,
    CLASSROOM_TEST_DIR,
    CLASSROOM_SESSION_DIR,
)

from app.routers import (
    student_router,
    teacher_router,
    attendance_router,
    session_router,
    classroom_router,
)

app = FastAPI(title="Attendance API")


os.makedirs(ENROLLMENTS_DIR, exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(CLASSROOM_TEST_DIR, exist_ok=True)
os.makedirs(CLASSROOM_SESSION_DIR, exist_ok=True)


@app.get("/")
def root():
    return {"message": "Attendance API is running"}


app.include_router(student_router.router)
app.include_router(teacher_router.router)
app.include_router(attendance_router.router)
app.include_router(session_router.router)
app.include_router(classroom_router.router)


