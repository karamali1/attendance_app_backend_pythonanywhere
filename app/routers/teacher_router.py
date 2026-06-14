from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from sqlalchemy import func

from sqlalchemy import func
from app.schemas.course_schema import CreateCourseRequest, UpdateCourseRequest

from app.core.auth import verify_password, create_access_token
from app.database import get_db
from app.dependencies.auth_dependencies import get_current_teacher
from app.models import Teacher, Course, StudentCourse, Student, ClassSession



router = APIRouter(prefix="/teacher", tags=["Teacher"])

@router.post("/login")
def login_teacher(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    teacher = db.query(Teacher).filter(Teacher.email == form_data.username).first()

    if not teacher:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not verify_password(form_data.password, teacher.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not teacher.is_active:
        raise HTTPException(status_code=403, detail="Teacher account is inactive")

    access_token = create_access_token(
        data={
            "sub": str(teacher.teacher_id),
            "email": teacher.email,
            "role": "teacher"
        }
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "teacher_id": teacher.teacher_id,
        "full_name": teacher.full_name,
        "email": teacher.email
    }


@router.get("/me")
def get_my_teacher_profile(current_teacher: Teacher = Depends(get_current_teacher)):
    return {
        "teacher_id": current_teacher.teacher_id,
        "full_name": current_teacher.full_name,
        "email": current_teacher.email,
        "national_number": current_teacher.national_number,
        "is_active": current_teacher.is_active
    }

@router.get("/courses")
def get_teacher_courses(
    current_teacher: Teacher = Depends(get_current_teacher),
    db: Session = Depends(get_db)
):
    courses = (
        db.query(Course)
        .filter(Course.teacher_id == current_teacher.teacher_id)
        .all()
    )

    return [
        {
            "course_id": course.course_id,
            "course_name": course.course_name,
            "year_of_study": course.year_of_study,
            "teacher_id": course.teacher_id,
            "teacher_name": current_teacher.full_name
        }
        for course in courses
    ]


@router.post("/courses")
def create_teacher_course(
    request: CreateCourseRequest,
    current_teacher: Teacher = Depends(get_current_teacher),
    db: Session = Depends(get_db)
):
    clean_course_name = request.course_name.strip()

    if not clean_course_name:
        raise HTTPException(
            status_code=400,
            detail="Course name cannot be empty"
        )

    if request.year_of_study < 1 or request.year_of_study > 5:
        raise HTTPException(
            status_code=400,
            detail="Year of study must be between 1 and 5"
        )

    existing_course = (
        db.query(Course)
        .filter(
            Course.teacher_id == current_teacher.teacher_id,
            func.lower(Course.course_name) == clean_course_name.lower()
        )
        .first()
    )

    if existing_course:
        raise HTTPException(
            status_code=400,
            detail="You already have a course with this name"
        )

    new_course = Course(
        course_name=clean_course_name,
        year_of_study=request.year_of_study,
        teacher_id=current_teacher.teacher_id,
        is_active=True
    )

    db.add(new_course)
    db.commit()
    db.refresh(new_course)

    return {
        "message": "Course created successfully",
        "course": {
            "course_id": new_course.course_id,
            "course_name": new_course.course_name,
            "year_of_study": new_course.year_of_study,
            "teacher_id": new_course.teacher_id,
            "teacher_name": current_teacher.full_name
        }
    }

@router.put("/courses/{course_id}")
def update_teacher_course(
    course_id: int,
    request: UpdateCourseRequest,
    current_teacher: Teacher = Depends(get_current_teacher),
    db: Session = Depends(get_db)
):
    course = (
        db.query(Course)
        .filter(
            Course.course_id == course_id,
            Course.teacher_id == current_teacher.teacher_id
        )
        .first()
    )

    if not course:
        raise HTTPException(
            status_code=404,
            detail="Course not found or does not belong to this teacher"
        )

    clean_course_name = request.course_name.strip()

    if not clean_course_name:
        raise HTTPException(
            status_code=400,
            detail="Course name cannot be empty"
        )

    if request.year_of_study < 1 or request.year_of_study > 5:
        raise HTTPException(
            status_code=400,
            detail="Year of study must be between 1 and 5"
        )

    duplicate_course = (
        db.query(Course)
        .filter(
            Course.teacher_id == current_teacher.teacher_id,
            Course.course_id != course_id,
            func.lower(Course.course_name) == clean_course_name.lower()
        )
        .first()
    )

    if duplicate_course:
        raise HTTPException(
            status_code=400,
            detail="You already have another course with this name"
        )

    enrollment_count = (
        db.query(StudentCourse)
        .filter(StudentCourse.course_id == course_id)
        .count()
    )

    session_count = (
        db.query(ClassSession)
        .filter(ClassSession.course_id == course_id)
        .count()
    )

    year_changed = course.year_of_study != request.year_of_study

    if year_changed and (enrollment_count > 0 or session_count > 0):
        raise HTTPException(
            status_code=400,
            detail="Cannot change course year after students enrolled or sessions were created"
        )

    course.course_name = clean_course_name
    course.year_of_study = request.year_of_study

    db.commit()
    db.refresh(course)

    return {
        "message": "Course updated successfully",
        "course": {
            "course_id": course.course_id,
            "course_name": course.course_name,
            "year_of_study": course.year_of_study,
            "teacher_id": course.teacher_id,
            "teacher_name": current_teacher.full_name
        }
    }

@router.delete("/courses/{course_id}")
def delete_teacher_course(
    course_id: int,
    current_teacher: Teacher = Depends(get_current_teacher),
    db: Session = Depends(get_db)
):
    course = (
        db.query(Course)
        .filter(
            Course.course_id == course_id,
            Course.teacher_id == current_teacher.teacher_id
        )
        .first()
    )

    if not course:
        raise HTTPException(
            status_code=404,
            detail="Course not found or does not belong to this teacher"
        )

    enrollment_count = (
        db.query(StudentCourse)
        .filter(StudentCourse.course_id == course_id)
        .count()
    )

    session_count = (
        db.query(ClassSession)
        .filter(ClassSession.course_id == course_id)
        .count()
    )

    if enrollment_count > 0 or session_count > 0:
        raise HTTPException(
            status_code=400,
            detail="Cannot delete a course that has enrolled students or created sessions"
        )

    db.delete(course)
    db.commit()

    return {
        "message": "Course deleted successfully",
        "course_id": course_id
    }

@router.get("/courses/{course_id}/students")
def get_course_students(
    course_id: int,
    current_teacher: Teacher = Depends(get_current_teacher),
    db: Session = Depends(get_db)
):
    # 1) Check that the course exists and belongs to the logged-in teacher
    course = (
        db.query(Course)
        .filter(
            Course.course_id == course_id,
            Course.teacher_id == current_teacher.teacher_id
        )
        .first()
    )

    if not course:
        raise HTTPException(
            status_code=404,
            detail="Course not found or does not belong to this teacher"
        )

    # 2) Get enrolled students
    records = (
        db.query(StudentCourse, Student)
        .join(Student, StudentCourse.student_id == Student.student_id)
        .filter(StudentCourse.course_id == course_id)
        .all()
    )

    return {
        "course": {
            "course_id": course.course_id,
            "course_name": course.course_name,
            "year_of_study": course.year_of_study
        },
        "teacher": {
            "teacher_id": current_teacher.teacher_id,
            "full_name": current_teacher.full_name
        },
        "students": [
            {
                "student_id": student.student_id,
                "full_name": student.full_name,
                "email": student.email,
                "university_number": student.university_number,
                "year_of_study": student.year_of_study,
                "enrolled_at": str(student_course.enrolled_at)
            }
            for student_course, student in records
        ],
        "total_students": len(records)
    }





