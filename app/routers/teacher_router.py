from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from sqlalchemy import func

from sqlalchemy import func
from app.schemas.course_schema import (
    CreateCourseRequest,
    UpdateCourseRequest,
    CreateSectionRequest,
    UpdateSectionRequest,
    CreateSectionScheduleRequest,
    UpdateSectionScheduleRequest,
)

from app.core.auth import verify_password, create_access_token
from app.database import get_db
from app.dependencies.auth_dependencies import get_current_teacher
from app.models import (
    Teacher,
    Course,
    StudentCourse,
    Student,
    ClassSession,
    CourseSection,
    Classroom,
    SectionSchedule,
    Attendance,
)



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



# now we will add the section endpoints

@router.post("/courses/{course_id}/sections")
def create_course_section(
    course_id: int,
    request: CreateSectionRequest,
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

    clean_section_name = request.section_name.strip()

    if not clean_section_name:
        raise HTTPException(
            status_code=400,
            detail="Section name cannot be empty"
        )

    if request.capacity <= 0:
        raise HTTPException(
            status_code=400,
            detail="Section capacity must be greater than zero"
        )

    classroom = (
        db.query(Classroom)
        .filter(Classroom.classroom_id == request.classroom_id)
        .first()
    )

    if not classroom:
        raise HTTPException(
            status_code=404,
            detail="Selected classroom was not found"
        )

    duplicate_section = (
        db.query(CourseSection)
        .filter(
            CourseSection.course_id == course_id,
            func.lower(CourseSection.section_name) == clean_section_name.lower()
        )
        .first()
    )

    if duplicate_section:
        raise HTTPException(
            status_code=400,
            detail="This course already has a section with this name"
        )

    new_section = CourseSection(
        course_id=course_id,
        section_name=clean_section_name,
        capacity=request.capacity,
        classroom_id=request.classroom_id,
        is_active=True
    )

    db.add(new_section)
    db.commit()
    db.refresh(new_section)

    return {
        "message": "Practical section created successfully",
        "section": {
            "section_id": new_section.section_id,
            "course_id": new_section.course_id,
            "section_name": new_section.section_name,
            "capacity": new_section.capacity,
            "classroom_id": new_section.classroom_id,
            "classroom_name": classroom.name,
            "building": classroom.building,
            "room_number": classroom.room_number,
            "is_active": new_section.is_active,
            "enrolled_students_count": 0,
            "available_seats": new_section.capacity
        }
    }


@router.get("/courses/{course_id}/sections")
def get_course_sections(
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

    sections = (
        db.query(CourseSection)
        .filter(CourseSection.course_id == course_id)
        .order_by(CourseSection.section_name.asc())
        .all()
    )

    result = []

    for section in sections:
        enrolled_students_count = (
            db.query(StudentCourse)
            .filter(StudentCourse.section_id == section.section_id)
            .count()
        )

        practical_sessions_count = (
            db.query(ClassSession)
            .filter(
                ClassSession.section_id == section.section_id,
                ClassSession.session_type == "practical"
            )
            .count()
        )

        classroom = section.classroom

        result.append(
            {
                "section_id": section.section_id,
                "course_id": section.course_id,
                "section_name": section.section_name,
                "capacity": section.capacity,
                "classroom_id": section.classroom_id,
                "classroom_name": classroom.name,
                "building": classroom.building,
                "room_number": classroom.room_number,
                "is_active": section.is_active,
                "enrolled_students_count": enrolled_students_count,
                "available_seats": max(
                    section.capacity - enrolled_students_count,
                    0
                ),
                "practical_sessions_count": practical_sessions_count,
                "created_at": str(section.created_at)
            }
        )

    return {
        "course": {
            "course_id": course.course_id,
            "course_name": course.course_name,
            "year_of_study": course.year_of_study
        },
        "sections": result,
        "total_sections": len(result)
    }


@router.put("/courses/{course_id}/sections/{section_id}")
def update_course_section(
    course_id: int,
    section_id: int,
    request: UpdateSectionRequest,
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

    section = (
        db.query(CourseSection)
        .filter(
            CourseSection.section_id == section_id,
            CourseSection.course_id == course_id
        )
        .first()
    )

    if not section:
        raise HTTPException(
            status_code=404,
            detail="Section not found in this course"
        )

    clean_section_name = request.section_name.strip()

    if not clean_section_name:
        raise HTTPException(
            status_code=400,
            detail="Section name cannot be empty"
        )

    if request.capacity <= 0:
        raise HTTPException(
            status_code=400,
            detail="Section capacity must be greater than zero"
        )

    classroom = (
        db.query(Classroom)
        .filter(Classroom.classroom_id == request.classroom_id)
        .first()
    )

    if not classroom:
        raise HTTPException(
            status_code=404,
            detail="Selected classroom was not found"
        )

    duplicate_section = (
        db.query(CourseSection)
        .filter(
            CourseSection.course_id == course_id,
            CourseSection.section_id != section_id,
            func.lower(CourseSection.section_name) == clean_section_name.lower()
        )
        .first()
    )

    if duplicate_section:
        raise HTTPException(
            status_code=400,
            detail="This course already has another section with this name"
        )

    enrolled_students_count = (
        db.query(StudentCourse)
        .filter(StudentCourse.section_id == section_id)
        .count()
    )

    if request.capacity < enrolled_students_count:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Capacity cannot be lower than the "
                f"{enrolled_students_count} students already enrolled"
            )
        )

    section.section_name = clean_section_name
    section.capacity = request.capacity
    section.classroom_id = request.classroom_id
    section.is_active = request.is_active

    db.commit()
    db.refresh(section)

    return {
        "message": "Practical section updated successfully",
        "section": {
            "section_id": section.section_id,
            "course_id": section.course_id,
            "section_name": section.section_name,
            "capacity": section.capacity,
            "classroom_id": section.classroom_id,
            "classroom_name": classroom.name,
            "building": classroom.building,
            "room_number": classroom.room_number,
            "is_active": section.is_active,
            "enrolled_students_count": enrolled_students_count,
            "available_seats": max(
                section.capacity - enrolled_students_count,
                0
            )
        }
    }


@router.delete("/courses/{course_id}/sections/{section_id}")
def delete_course_section(
    course_id: int,
    section_id: int,
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

    section = (
        db.query(CourseSection)
        .filter(
            CourseSection.section_id == section_id,
            CourseSection.course_id == course_id
        )
        .first()
    )

    if not section:
        raise HTTPException(
            status_code=404,
            detail="Section not found in this course"
        )

    enrolled_students_count = (
        db.query(StudentCourse)
        .filter(StudentCourse.section_id == section_id)
        .count()
    )

    practical_sessions_count = (
        db.query(ClassSession)
        .filter(ClassSession.section_id == section_id)
        .count()
    )

    if enrolled_students_count > 0:
        raise HTTPException(
            status_code=400,
            detail=(
                "Cannot delete this section because students "
                "are already assigned to it"
            )
        )

    if practical_sessions_count > 0:
        raise HTTPException(
            status_code=400,
            detail=(
                "Cannot delete this section because practical sessions "
                "were already created for it"
            )
        )

    db.delete(section)
    db.commit()

    return {
        "message": "Practical section deleted successfully",
        "section_id": section_id
    }



# This is the sections endpoints

def _get_teacher_course_section(
    course_id: int,
    section_id: int,
    current_teacher: Teacher,
    db: Session
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

    section = (
        db.query(CourseSection)
        .filter(
            CourseSection.section_id == section_id,
            CourseSection.course_id == course_id
        )
        .first()
    )

    if not section:
        raise HTTPException(
            status_code=404,
            detail="Section not found in this course"
        )

    return course, section


@router.post("/courses/{course_id}/sections/{section_id}/schedules")
def create_section_schedule(
    course_id: int,
    section_id: int,
    request: CreateSectionScheduleRequest,
    current_teacher: Teacher = Depends(get_current_teacher),
    db: Session = Depends(get_db)
):
    course, section = _get_teacher_course_section(
        course_id=course_id,
        section_id=section_id,
        current_teacher=current_teacher,
        db=db
    )

    if not section.is_active:
        raise HTTPException(
            status_code=400,
            detail="Cannot create a schedule for an inactive section"
        )

    if request.weekday < 0 or request.weekday > 6:
        raise HTTPException(
            status_code=400,
            detail="Weekday must be between 0 and 6"
        )

    if request.start_time >= request.end_time:
        raise HTTPException(
            status_code=400,
            detail="Start time must be earlier than end time"
        )

    if request.repeat_interval_weeks not in [1, 2]:
        raise HTTPException(
            status_code=400,
            detail="Repeat interval must be 1 week or 2 weeks"
        )

    if (
        request.attendance_open_time < request.start_time
        or request.attendance_close_time > request.end_time
        or request.attendance_open_time >= request.attendance_close_time
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                "Attendance window must be inside the session time "
                "and open before it closes"
            )
        )

    if request.end_date is None and request.repeat_for_weeks is None:
        raise HTTPException(
            status_code=400,
            detail="Choose either an end date or number of weeks"
        )

    if request.end_date is not None and request.repeat_for_weeks is not None:
        raise HTTPException(
            status_code=400,
            detail="Choose only one ending rule: end date or number of weeks"
        )

    if request.repeat_for_weeks is not None and request.repeat_for_weeks <= 0:
        raise HTTPException(
            status_code=400,
            detail="Number of weeks must be greater than zero"
        )

    # Find the first selected weekday on or after the chosen start date.
    days_until_weekday = (
        request.weekday - request.start_date.weekday()
    ) % 7

    first_occurrence_date = request.start_date + timedelta(
        days=days_until_weekday
    )

    if (
        request.end_date is not None
        and first_occurrence_date > request.end_date
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                "The selected end date is before the first matching weekday"
            )
        )

    if request.end_date is not None:
        last_allowed_date = request.end_date
    else:
        # Example:
        # start date = Tuesday, repeat_for_weeks = 12
        # weekly -> 12 practical sessions
        # every 2 weeks -> 6 practical sessions
        last_allowed_date = first_occurrence_date + timedelta(
            weeks=request.repeat_for_weeks - 1
        )

    occurrence_dates = []
    current_date = first_occurrence_date

    while current_date <= last_allowed_date:
        occurrence_dates.append(current_date)

        current_date += timedelta(
            weeks=request.repeat_interval_weeks
        )

    if not occurrence_dates:
        raise HTTPException(
            status_code=400,
            detail="No practical sessions could be generated"
        )

    # Check every generated date before saving anything.
    # This prevents half-created schedules.
    for occurrence_date in occurrence_dates:
        existing_conflict = (
            db.query(ClassSession)
            .filter(
                ClassSession.classroom_id == section.classroom_id,
                ClassSession.session_date == occurrence_date,
                ClassSession.start_time < request.end_time,
                ClassSession.end_time > request.start_time
            )
            .first()
        )

        if existing_conflict:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Classroom conflict on {occurrence_date}. "
                    f"Existing session: "
                    f"{existing_conflict.start_time.strftime('%H:%M')} - "
                    f"{existing_conflict.end_time.strftime('%H:%M')}"
                )
            )

    try:
        new_schedule = SectionSchedule(
            section_id=section.section_id,
            weekday=request.weekday,
            start_time=request.start_time,
            end_time=request.end_time,
            repeat_interval_weeks=request.repeat_interval_weeks,
            start_date=first_occurrence_date,
            end_date=request.end_date,
            repeat_for_weeks=request.repeat_for_weeks,
            attendance_open_time=request.attendance_open_time,
            attendance_close_time=request.attendance_close_time,
            is_active=True
        )

        db.add(new_schedule)

        # Gets schedule_id before commit,
        # so every generated session can reference this schedule.
        db.flush()

        for occurrence_date in occurrence_dates:
            new_session = ClassSession(
                course_id=course.course_id,
                classroom_id=section.classroom_id,
                session_type="practical",
                section_id=section.section_id,
                schedule_id=new_schedule.schedule_id,
                session_date=occurrence_date,
                start_time=request.start_time,
                end_time=request.end_time,
                attendance_open_time=request.attendance_open_time,
                attendance_close_time=request.attendance_close_time
            )

            db.add(new_session)

        db.commit()
        db.refresh(new_schedule)

    except Exception:
        db.rollback()
        raise

    return {
        "message": "Practical schedule created successfully",
        "schedule": {
            "schedule_id": new_schedule.schedule_id,
            "section_id": section.section_id,
            "section_name": section.section_name,
            "weekday": new_schedule.weekday,
            "start_time": str(new_schedule.start_time),
            "end_time": str(new_schedule.end_time),
            "repeat_interval_weeks": new_schedule.repeat_interval_weeks,
            "start_date": str(new_schedule.start_date),
            "end_date": (
                str(new_schedule.end_date)
                if new_schedule.end_date
                else None
            ),
            "repeat_for_weeks": new_schedule.repeat_for_weeks,
            "generated_sessions_count": len(occurrence_dates)
        },
        "generated_session_dates": [
            str(occurrence_date)
            for occurrence_date in occurrence_dates
        ]
    }


@router.get("/courses/{course_id}/sections/{section_id}/schedules")
def get_section_schedules(
    course_id: int,
    section_id: int,
    current_teacher: Teacher = Depends(get_current_teacher),
    db: Session = Depends(get_db)
):
    _, section = _get_teacher_course_section(
        course_id=course_id,
        section_id=section_id,
        current_teacher=current_teacher,
        db=db
    )

    weekday_names = [
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
        "Sunday"
    ]

    schedules = (
        db.query(SectionSchedule)
        .filter(SectionSchedule.section_id == section.section_id)
        .order_by(
            SectionSchedule.weekday.asc(),
            SectionSchedule.start_time.asc()
        )
        .all()
    )

    result = []

    for schedule in schedules:
        generated_sessions_count = (
            db.query(ClassSession)
            .filter(ClassSession.schedule_id == schedule.schedule_id)
            .count()
        )

        result.append(
            {
                "schedule_id": schedule.schedule_id,
                "section_id": schedule.section_id,
                "weekday": schedule.weekday,
                "weekday_name": weekday_names[schedule.weekday],
                "start_time": str(schedule.start_time),
                "end_time": str(schedule.end_time),
                "repeat_interval_weeks": schedule.repeat_interval_weeks,
                "start_date": str(schedule.start_date),
                "end_date": (
                    str(schedule.end_date)
                    if schedule.end_date
                    else None
                ),
                "repeat_for_weeks": schedule.repeat_for_weeks,
                "attendance_open_time": str(schedule.attendance_open_time),
                "attendance_close_time": str(schedule.attendance_close_time),
                "is_active": schedule.is_active,
                "generated_sessions_count": generated_sessions_count,
                "created_at": str(schedule.created_at)
            }
        )

    return {
        "section": {
            "section_id": section.section_id,
            "section_name": section.section_name,
            "classroom_id": section.classroom_id,
            "classroom_name": section.classroom.name
        },
        "schedules": result,
        "total_schedules": len(result)
    }











def _build_schedule_occurrence_dates(request):
    if request.weekday < 0 or request.weekday > 6:
        raise HTTPException(
            status_code=400,
            detail="Weekday must be between 0 and 6"
        )

    if request.start_time >= request.end_time:
        raise HTTPException(
            status_code=400,
            detail="Start time must be earlier than end time"
        )

    if request.repeat_interval_weeks not in [1, 2]:
        raise HTTPException(
            status_code=400,
            detail="Repeat interval must be 1 week or 2 weeks"
        )

    if (
        request.attendance_open_time < request.start_time
        or request.attendance_close_time > request.end_time
        or request.attendance_open_time >= request.attendance_close_time
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                "Attendance window must be inside the session time "
                "and open before it closes"
            )
        )

    if request.end_date is None and request.repeat_for_weeks is None:
        raise HTTPException(
            status_code=400,
            detail="Choose either an end date or number of weeks"
        )

    if request.end_date is not None and request.repeat_for_weeks is not None:
        raise HTTPException(
            status_code=400,
            detail="Choose only one ending rule: end date or number of weeks"
        )

    if request.repeat_for_weeks is not None and request.repeat_for_weeks <= 0:
        raise HTTPException(
            status_code=400,
            detail="Number of weeks must be greater than zero"
        )

    days_until_weekday = (
        request.weekday - request.start_date.weekday()
    ) % 7

    first_occurrence_date = request.start_date + timedelta(
        days=days_until_weekday
    )

    if (
        request.end_date is not None
        and first_occurrence_date > request.end_date
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                "The selected end date is before the first matching weekday"
            )
        )

    if request.end_date is not None:
        last_allowed_date = request.end_date
    else:
        last_allowed_date = first_occurrence_date + timedelta(
            weeks=request.repeat_for_weeks - 1
        )

    occurrence_dates = []
    current_date = first_occurrence_date

    while current_date <= last_allowed_date:
        occurrence_dates.append(current_date)

        current_date += timedelta(
            weeks=request.repeat_interval_weeks
        )

    if not occurrence_dates:
        raise HTTPException(
            status_code=400,
            detail="No practical sessions could be generated"
        )

    return first_occurrence_date, occurrence_dates


@router.put(
    "/courses/{course_id}/sections/{section_id}/schedules/{schedule_id}"
)
def update_section_schedule(
    course_id: int,
    section_id: int,
    schedule_id: int,
    request: UpdateSectionScheduleRequest,
    current_teacher: Teacher = Depends(get_current_teacher),
    db: Session = Depends(get_db)
):
    course, section = _get_teacher_course_section(
        course_id=course_id,
        section_id=section_id,
        current_teacher=current_teacher,
        db=db
    )

    schedule = (
        db.query(SectionSchedule)
        .filter(
            SectionSchedule.schedule_id == schedule_id,
            SectionSchedule.section_id == section.section_id
        )
        .first()
    )

    if not schedule:
        raise HTTPException(
            status_code=404,
            detail="Schedule not found in this section"
        )

    attendance_exists = (
        db.query(Attendance)
        .join(
            ClassSession,
            Attendance.session_id == ClassSession.session_id
        )
        .filter(ClassSession.schedule_id == schedule_id)
        .first()
    )

    if attendance_exists:
        raise HTTPException(
            status_code=400,
            detail=(
                "Cannot edit this schedule because one or more generated "
                "sessions already have attendance records"
            )
        )

    if not section.is_active:
        raise HTTPException(
            status_code=400,
            detail="Cannot update a schedule for an inactive section"
        )

    first_occurrence_date, occurrence_dates = (
        _build_schedule_occurrence_dates(request)
    )

    # Check conflicts against every OTHER schedule/session.
    for occurrence_date in occurrence_dates:
        existing_conflict = (
            db.query(ClassSession)
            .filter(
                ClassSession.classroom_id == section.classroom_id,
                ClassSession.session_date == occurrence_date,
                ClassSession.start_time < request.end_time,
                ClassSession.end_time > request.start_time,
                ClassSession.schedule_id != schedule_id
            )
            .first()
        )

        if existing_conflict:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Classroom conflict on {occurrence_date}. "
                    f"Existing session: "
                    f"{existing_conflict.start_time.strftime('%H:%M')} - "
                    f"{existing_conflict.end_time.strftime('%H:%M')}"
                )
            )

    try:
        # Remove old generated sessions only after all validations pass.
        db.query(ClassSession).filter(
            ClassSession.schedule_id == schedule_id
        ).delete(synchronize_session=False)

        schedule.weekday = request.weekday
        schedule.start_time = request.start_time
        schedule.end_time = request.end_time
        schedule.repeat_interval_weeks = request.repeat_interval_weeks
        schedule.start_date = first_occurrence_date
        schedule.end_date = request.end_date
        schedule.repeat_for_weeks = request.repeat_for_weeks
        schedule.attendance_open_time = request.attendance_open_time
        schedule.attendance_close_time = request.attendance_close_time
        schedule.is_active = request.is_active

        db.flush()

        if request.is_active:
            for occurrence_date in occurrence_dates:
                db.add(
                    ClassSession(
                        course_id=course.course_id,
                        classroom_id=section.classroom_id,
                        session_type="practical",
                        section_id=section.section_id,
                        schedule_id=schedule.schedule_id,
                        session_date=occurrence_date,
                        start_time=request.start_time,
                        end_time=request.end_time,
                        attendance_open_time=request.attendance_open_time,
                        attendance_close_time=request.attendance_close_time
                    )
                )

        db.commit()
        db.refresh(schedule)

    except Exception:
        db.rollback()
        raise

    return {
        "message": "Practical schedule updated successfully",
        "schedule": {
            "schedule_id": schedule.schedule_id,
            "section_id": section.section_id,
            "weekday": schedule.weekday,
            "start_time": str(schedule.start_time),
            "end_time": str(schedule.end_time),
            "repeat_interval_weeks": schedule.repeat_interval_weeks,
            "start_date": str(schedule.start_date),
            "end_date": (
                str(schedule.end_date)
                if schedule.end_date
                else None
            ),
            "repeat_for_weeks": schedule.repeat_for_weeks,
            "is_active": schedule.is_active,
            "generated_sessions_count": (
                len(occurrence_dates)
                if schedule.is_active
                else 0
            )
        }
    }


@router.delete(
    "/courses/{course_id}/sections/{section_id}/schedules/{schedule_id}"
)
def delete_section_schedule(
    course_id: int,
    section_id: int,
    schedule_id: int,
    current_teacher: Teacher = Depends(get_current_teacher),
    db: Session = Depends(get_db)
):
    _, section = _get_teacher_course_section(
        course_id=course_id,
        section_id=section_id,
        current_teacher=current_teacher,
        db=db
    )

    schedule = (
        db.query(SectionSchedule)
        .filter(
            SectionSchedule.schedule_id == schedule_id,
            SectionSchedule.section_id == section.section_id
        )
        .first()
    )

    if not schedule:
        raise HTTPException(
            status_code=404,
            detail="Schedule not found in this section"
        )

    attendance_exists = (
        db.query(Attendance)
        .join(
            ClassSession,
            Attendance.session_id == ClassSession.session_id
        )
        .filter(ClassSession.schedule_id == schedule_id)
        .first()
    )

    if attendance_exists:
        raise HTTPException(
            status_code=400,
            detail=(
                "Cannot delete this schedule because one or more generated "
                "sessions already have attendance records"
            )
        )

    generated_sessions_count = (
        db.query(ClassSession)
        .filter(ClassSession.schedule_id == schedule_id)
        .count()
    )

    try:
        db.query(ClassSession).filter(
            ClassSession.schedule_id == schedule_id
        ).delete(synchronize_session=False)

        db.delete(schedule)
        db.commit()

    except Exception:
        db.rollback()
        raise

    return {
        "message": "Practical schedule deleted successfully",
        "schedule_id": schedule_id,
        "deleted_generated_sessions_count": generated_sessions_count
    }

