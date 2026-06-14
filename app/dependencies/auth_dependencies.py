from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.core.auth import SECRET_KEY, ALGORITHM
from app.database import get_db
from app.models import Student, Teacher


student_oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="login",
    scheme_name="StudentAuth"
)

teacher_oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="teacher/login",
    scheme_name="TeacherAuth"
)



def get_current_student(
    token: str = Depends(student_oauth2_scheme),
    db: Session = Depends(get_db)
):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        student_id: str = payload.get("sub")

        if student_id is None:
            raise credentials_exception

    except JWTError:
        raise credentials_exception

    student = db.query(Student).filter(Student.student_id == int(student_id)).first()

    if student is None:
        raise credentials_exception

    return student


def get_current_teacher(
    token: str = Depends(teacher_oauth2_scheme),
    db: Session = Depends(get_db)
):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate teacher credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        teacher_id: str = payload.get("sub")
        role: str = payload.get("role")

        if teacher_id is None or role != "teacher":
            raise credentials_exception

    except JWTError:
        raise credentials_exception

    teacher = db.query(Teacher).filter(Teacher.teacher_id == int(teacher_id)).first()

    if teacher is None:
        raise credentials_exception

    return teacher