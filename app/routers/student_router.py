import os
import shutil
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from app.core.time_utils import now_syria

from fastapi.responses import FileResponse
from fastapi import APIRouter, Body, Depends, HTTPException, UploadFile, File
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.utils.firebase_utils import verify_firebase_token, verify_firebase_token_for_registration
from app.services.antispoofing_instance import anti_spoofing_service

from app.core.auth import (
    hash_password,
    verify_password,
    create_access_token,
    generate_verification_token,
)

from app.core.config import ENROLLMENTS_DIR
from app.database import get_db
from app.dependencies.auth_dependencies import get_current_student
from app.models import (
    Student,
    StudentCourse,
    Attendance,
    ClassSession,
    Course,
    Classroom,
    StudentFaceEmbedding,
    Teacher,
    StudentNotification,
    StudentDeviceToken,
    CourseSection,
)
from app.schemas.student_schema import RegisterRequest

from app.services.face_service_instance import insightface_service

from app.schemas.firebase_schema import FirebaseLoginRequest, FirebaseStudentRegisterRequest

from app.schemas.enrollment_schema import EnrollCourseRequest

from app.schemas.notification_schema import SaveFcmTokenRequest

from app.services.fcm_service import send_push_notification_to_token


router = APIRouter(tags=["Student"])

@router.get("/students")
def get_students(db: Session = Depends(get_db)):
    students = db.query(Student).all()

    return [
        {
            "student_id": student.student_id,
            "full_name": student.full_name,
            "email": student.email,
            "university_number": student.university_number,
            "year_of_study": student.year_of_study
        }
        for student in students
    ]



@router.get("/sessions")
def get_sessions(
    current_student: Student = Depends(get_current_student),
    db: Session = Depends(get_db)
):
    enrollments = (
        db.query(StudentCourse)
        .filter(StudentCourse.student_id == current_student.student_id)
        .all()
    )

    if not enrollments:
        return []

    enrollment_by_course = {
        enrollment.course_id: enrollment
        for enrollment in enrollments
    }

    course_ids = list(enrollment_by_course.keys())

    records = (
        db.query(ClassSession, Course, Classroom)
        .join(Course, ClassSession.course_id == Course.course_id)
        .join(Classroom, ClassSession.classroom_id == Classroom.classroom_id)
        .filter(ClassSession.course_id.in_(course_ids))
        .all()
    )

    result = []
    now = now_syria()

    for session, course, classroom in records:
        enrollment = enrollment_by_course[course.course_id]
        session_type = session.session_type or "theory"

        # Theory: every enrolled student can see it.
        # Practical: only students assigned to this exact section can see it.
        if (
            session_type == "practical"
            and enrollment.section_id != session.section_id
        ):
            continue

        attendance_close_dt = datetime.combine(
            session.session_date,
            session.attendance_close_time
        )

        # Do not show expired attendance sessions.
        if attendance_close_dt <= now:
            continue

        existing_attendance = (
            db.query(Attendance)
            .filter(
                Attendance.student_id == current_student.student_id,
                Attendance.session_id == session.session_id
            )
            .first()
        )

        # A submitted session should disappear from the available sessions page.
        if existing_attendance:
            continue

        result.append({
            "session_id": session.session_id,
            "session_type": session_type,
            "session_date": str(session.session_date),
            "start_time": str(session.start_time),
            "end_time": str(session.end_time),
            "attendance_open_time": str(session.attendance_open_time),
            "attendance_close_time": str(session.attendance_close_time),
            "course": {
                "course_id": course.course_id,
                "course_name": course.course_name,
                "year_of_study": course.year_of_study,
            },
            "classroom": {
                "classroom_id": classroom.classroom_id,
                "name": classroom.name,
                "building": classroom.building,
                "room_number": classroom.room_number,
                "allowed_radius_meters": classroom.allowed_radius_meters,
            }
        })

    return result


@router.get("/student/course-attendance-summary")
def get_student_course_attendance_summary(
    current_student: Student = Depends(get_current_student),
    db: Session = Depends(get_db)
):
    enrollments = (
        db.query(StudentCourse, Course)
        .join(Course, StudentCourse.course_id == Course.course_id)
        .filter(StudentCourse.student_id == current_student.student_id)
        .all()
    )

    if not enrollments:
        return []

    now = now_syria()
    result = []

    for enrollment, course in enrollments:
        all_course_sessions = (
            db.query(ClassSession)
            .filter(ClassSession.course_id == course.course_id)
            .all()
        )

        counted_sessions = []

        for session in all_course_sessions:
            attendance = db.query(Attendance).filter(
                Attendance.session_id == session.session_id,
                Attendance.student_id == current_student.student_id
            ).first()

            attendance_close_dt = datetime.combine(
                session.session_date,
                session.attendance_close_time
            )

            # Count immediately if attended
            if attendance:
                counted_sessions.append(session)
            # Count as finalized absent only after window closes
            elif attendance_close_dt <= now:
                counted_sessions.append(session)

        total_sessions = len(counted_sessions)
        session_ids = [session.session_id for session in counted_sessions]

        attended_count = 0

        if session_ids:
            attended_count = (
                db.query(Attendance)
                .filter(
                    Attendance.student_id == current_student.student_id,
                    Attendance.session_id.in_(session_ids)
                )
                .count()
            )

        absent_count = total_sessions - attended_count if total_sessions > 0 else 0

        attendance_percentage = 0.0
        if total_sessions > 0:
            attendance_percentage = round((attended_count / total_sessions) * 100, 2)

        if total_sessions == 0:
            attendance_status = "No Sessions Yet"
        elif attendance_percentage >= 90:
            attendance_status = "Excellent"
        elif attendance_percentage >= 75:
            attendance_status = "Good"
        elif attendance_percentage >= 50:
            attendance_status = "Warning"
        else:
            attendance_status = "At Risk"

        result.append({
            "course_id": course.course_id,
            "course_name": course.course_name,
            "year_of_study": course.year_of_study,
            "attended_sessions": attended_count,
            "absent_sessions": absent_count,
            "total_sessions": total_sessions,
            "attendance_ratio": f"{attended_count}/{total_sessions}",
            "attendance_percentage": attendance_percentage,
            "attendance_status": attendance_status
        })

    result.sort(key=lambda x: x["course_name"].lower())

    return result

@router.get("/me")
def get_my_profile(current_student: Student = Depends(get_current_student)):
    return {
        "student_id": current_student.student_id,
        "full_name": current_student.full_name,
        "email": current_student.email,
        "university_number": current_student.university_number,
        "year_of_study": current_student.year_of_study,
        "email_verified": current_student.email_verified
    }


@router.post("/register")
def register_student(request: RegisterRequest, db: Session = Depends(get_db)):
    existing_student = db.query(Student).filter(Student.email == request.email).first()
    if existing_student:
        raise HTTPException(status_code=400, detail="Email already registered")

    existing_national = db.query(Student).filter(Student.national_number == request.national_number).first()
    if existing_national:
        raise HTTPException(status_code=400, detail="National number already registered")

    existing_university = db.query(Student).filter(Student.university_number == request.university_number).first()
    if existing_university:
        raise HTTPException(status_code=400, detail="University number already registered")

    verification_token = generate_verification_token()
    hashed_password = hash_password(request.password)

    new_student = Student(
        email=request.email,
        password_hash=hashed_password,
        email_verified=True,
        verification_token=verification_token,
        national_number=request.national_number,
        university_number=request.university_number,
        full_name=request.full_name,
        year_of_study=request.year_of_study,
        is_active=True
    )

    db.add(new_student)
    db.commit()
    db.refresh(new_student)

    return {
        "message": "Student registered successfully. Please verify your email.",
        "student_id": new_student.student_id,
        "email": new_student.email,
        "verification_token": verification_token
    }

@router.get("/verify-email")
def verify_email(token: str, db: Session = Depends(get_db)):
    student = db.query(Student).filter(Student.verification_token == token).first()

    if not student:
        raise HTTPException(status_code=400, detail="Invalid verification token")

    student.email_verified = True
    student.verification_token = None

    db.commit()

    return {
        "message": "Email verified successfully"
    }

@router.post("/login")
def login_student(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    student = db.query(Student).filter(Student.email == form_data.username).first()

    if not student:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not verify_password(form_data.password, student.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not student.email_verified:
        raise HTTPException(status_code=403, detail="Email is not verified")

    access_token = create_access_token(
        data={
            "sub": str(student.student_id),
            "email": student.email,
            "role": "student"
        }
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "student_id": student.student_id,
        "full_name": student.full_name,
        "email": student.email
    }

@router.post("/students/{student_id}/enroll-face")
def enroll_student_face(
    student_id: int,
    image: UploadFile = File(...),
    current_student: Student = Depends(get_current_student),
    db: Session = Depends(get_db)
):
    # 1) Make sure the logged-in student is enrolling only their own face
    if current_student.student_id != student_id:
        raise HTTPException(
            status_code=403,
            detail="You are not allowed to enroll a face for another student"
        )

    # 2) Check student exists
    student = db.query(Student).filter(Student.student_id == student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    # 3) Validate image type
    if not image.content_type or not image.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Uploaded file must be an image")

    # 4) Save uploaded image temporarily
    file_name = f"student_{student_id}_enrollment.jpg"
    file_path = os.path.join(ENROLLMENTS_DIR, file_name)

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(image.file, buffer)

    # 5) Generate embedding from uploaded image
    try:
        new_embedding = insightface_service.get_face_embedding(file_path)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # 6) Check current active embedding
    current_active_embedding = (
        db.query(StudentFaceEmbedding)
        .filter(
            StudentFaceEmbedding.student_id == student_id,
            StudentFaceEmbedding.is_active == True
        )
        .order_by(StudentFaceEmbedding.created_at.desc())
        .first()
    )

    # 7) If student already has an active embedding, verify the new one matches it
    if current_active_embedding:
        try:
            reenrollment_similarity = insightface_service.compare_embedding_with_stored_embedding(
                new_embedding,
                current_active_embedding.embedding
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        REENROLLMENT_MATCH_THRESHOLD = 0.65

        if reenrollment_similarity < REENROLLMENT_MATCH_THRESHOLD:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"New enrollment image does not match the previously enrolled face. "
                    f"Similarity: {reenrollment_similarity:.4f}"
                )
            )

    # 8) Convert embedding to bytes only after validation succeeds
    embedding_bytes = insightface_service.embedding_to_bytes(new_embedding)

    # 9) Deactivate old active embeddings
    old_embeddings = (
        db.query(StudentFaceEmbedding)
        .filter(
            StudentFaceEmbedding.student_id == student_id,
            StudentFaceEmbedding.is_active == True
        )
        .all()
    )

    for old_embedding in old_embeddings:
        old_embedding.is_active = False

    # 10) Save new embedding
    new_embedding_record = StudentFaceEmbedding(
        student_id=student_id,
        embedding=embedding_bytes,
        model_name="buffalo_l",
        is_active=True
    )

    db.add(new_embedding_record)
    db.commit()
    db.refresh(new_embedding_record)

    return {
        "message": "Face enrolled successfully",
        "student_id": student_id,
        "embedding_id": new_embedding_record.id,
        "model_name": new_embedding_record.model_name,
        "is_active": new_embedding_record.is_active
    }

@router.get("/student/attendance")
def get_student_attendance(
    current_student: Student = Depends(get_current_student),
    db: Session = Depends(get_db)
):
    enrollments = (
        db.query(StudentCourse)
        .filter(StudentCourse.student_id == current_student.student_id)
        .all()
    )

    if not enrollments:
        return []

    enrollment_by_course = {
        enrollment.course_id: enrollment
        for enrollment in enrollments
    }

    course_ids = list(enrollment_by_course.keys())

    sessions = (
        db.query(ClassSession)
        .filter(ClassSession.course_id.in_(course_ids))
        .all()
    )

    result = []
    now = now_syria()

    for session in sessions:
        enrollment = enrollment_by_course[session.course_id]
        session_type = session.session_type or "theory"

        # Theory belongs to every enrolled student.
        # Practical belongs only to the student's selected section.
        if (
            session_type == "practical"
            and enrollment.section_id != session.section_id
        ):
            continue

        attendance = (
            db.query(Attendance)
            .filter(
                Attendance.session_id == session.session_id,
                Attendance.student_id == current_student.student_id
            )
            .first()
        )

        attendance_close_dt = datetime.combine(
            session.session_date,
            session.attendance_close_time
        )

        if attendance:
            status = "Present"
        elif attendance_close_dt > now:
            continue
        else:
            status = "Absent"

        result.append({
            "session_id": session.session_id,
            "session_type": session_type,
            "course_name": session.course.course_name,
            "session_date": str(session.session_date),
            "start_time": str(session.start_time),
            "end_time": str(session.end_time),
            "status": status
        })

    result.sort(
        key=lambda x: (x["session_date"], x["start_time"]),
        reverse=True
    )

    return result


@router.get("/student/available-courses")
def get_available_courses_for_student(
    current_student: Student = Depends(get_current_student),
    db: Session = Depends(get_db)
):
    if not current_student.is_active:
        raise HTTPException(
            status_code=403,
            detail="Student account is inactive"
        )

    enrolled_course_ids = (
        db.query(StudentCourse.course_id)
        .filter(StudentCourse.student_id == current_student.student_id)
        .all()
    )

    enrolled_course_ids = [course_id for (course_id,) in enrolled_course_ids]

    query = (
        db.query(Course, Teacher)
        .join(Teacher, Course.teacher_id == Teacher.teacher_id)
        .filter(
            Course.is_active == True,
            Course.year_of_study == current_student.year_of_study
        )
    )

    if enrolled_course_ids:
        query = query.filter(Course.course_id.notin_(enrolled_course_ids))

    records = (
        query
        .order_by(Course.course_name.asc())
        .all()
    )

    return [
        {
            "course_id": course.course_id,
            "course_name": course.course_name,
            "year_of_study": course.year_of_study,
            "teacher": {
                "teacher_id": teacher.teacher_id,
                "full_name": teacher.full_name,
                "email": teacher.email
            }
        }
        for course, teacher in records
    ]


@router.post("/student/enroll-course")
def enroll_student_in_course(
    request: EnrollCourseRequest,
    current_student: Student = Depends(get_current_student),
    db: Session = Depends(get_db)
):
    if not current_student.is_active:
        raise HTTPException(
            status_code=403,
            detail="Student account is inactive"
        )

    course = (
        db.query(Course)
        .filter(Course.course_id == request.course_id)
        .first()
    )

    if not course:
        raise HTTPException(
            status_code=404,
            detail="Course not found"
        )

    if not course.is_active:
        raise HTTPException(
            status_code=400,
            detail="Course is not active"
        )

    if course.year_of_study != current_student.year_of_study:
        raise HTTPException(
            status_code=403,
            detail="You cannot enroll in a course from a different year"
        )

    existing_enrollment = (
        db.query(StudentCourse)
        .filter(
            StudentCourse.student_id == current_student.student_id,
            StudentCourse.course_id == course.course_id
        )
        .first()
    )

    if existing_enrollment:
        raise HTTPException(
            status_code=400,
            detail="You are already enrolled in this course"
        )

    new_enrollment = StudentCourse(
        student_id=current_student.student_id,
        course_id=course.course_id
    )

    db.add(new_enrollment)
    db.commit()
    db.refresh(new_enrollment)

    return {
        "message": "Enrolled in course successfully",
        "enrollment": {
            "id": new_enrollment.id,
            "student_id": current_student.student_id,
            "course_id": course.course_id,
            "course_name": course.course_name,
            "year_of_study": course.year_of_study,
            "enrolled_at": str(new_enrollment.enrolled_at)
        }
    }



@router.get("/student/my-courses")
def get_student_my_courses(
    current_student: Student = Depends(get_current_student),
    db: Session = Depends(get_db)
):
    if not current_student.is_active:
        raise HTTPException(
            status_code=403,
            detail="Student account is inactive"
        )

    enrollments = (
        db.query(StudentCourse, Course, Teacher)
        .join(Course, StudentCourse.course_id == Course.course_id)
        .join(Teacher, Course.teacher_id == Teacher.teacher_id)
        .filter(StudentCourse.student_id == current_student.student_id)
        .order_by(Course.course_name.asc())
        .all()
    )

    if not enrollments:
        return []

    now = now_syria()
    result = []

    for enrollment, course, teacher in enrollments:
        course_sessions = (
            db.query(ClassSession)
            .filter(ClassSession.course_id == course.course_id)
            .all()
        )
        active_practical_sections = (
            db.query(CourseSection)
            .filter(
                CourseSection.course_id == course.course_id,
                CourseSection.is_active == True
            )
            .count()
        )

        selected_section_name = None

        if enrollment.section_id is not None:
            selected_section = (
                db.query(CourseSection)
                .filter(
                    CourseSection.section_id == enrollment.section_id,
                    CourseSection.course_id == course.course_id
                )
                .first()
            )

            if selected_section:
                selected_section_name = selected_section.section_name

        attended_count = 0
        absent_count = 0
        total_sessions = 0

        for session in course_sessions:
            session_type = session.session_type or "theory"

            # Theory belongs to every enrolled student.
            # Practical belongs only to the student's selected section.
            if (
                session_type == "practical"
                and enrollment.section_id != session.section_id
            ):
                continue

            attendance = (
                db.query(Attendance)
                .filter(
                    Attendance.student_id == current_student.student_id,
                    Attendance.session_id == session.session_id
                )
                .first()
            )

            attendance_close_dt = datetime.combine(
                session.session_date,
                session.attendance_close_time
            )

            if attendance:
                attended_count += 1
                total_sessions += 1
            elif attendance_close_dt <= now:
                absent_count += 1
                total_sessions += 1

        attendance_percentage = 0.0

        if total_sessions > 0:
            attendance_percentage = round(
                (attended_count / total_sessions) * 100,
                2
            )

        if total_sessions == 0:
            attendance_status = "No Sessions Yet"
        elif attendance_percentage >= 90:
            attendance_status = "Excellent"
        elif attendance_percentage >= 75:
            attendance_status = "Good"
        elif attendance_percentage >= 50:
            attendance_status = "Warning"
        else:
            attendance_status = "At Risk"

        result.append({
            "course_id": course.course_id,
            "course_name": course.course_name,
            "year_of_study": course.year_of_study,
            "is_active": course.is_active,
            "selected_section_id": enrollment.section_id,
            "selected_section_name": selected_section_name,
            "has_practical_sections": active_practical_sections > 0,
            "teacher": {
                "teacher_id": teacher.teacher_id,
                "full_name": teacher.full_name,
                "email": teacher.email
            },
            "attendance": {
                "attended_sessions": attended_count,
                "absent_sessions": absent_count,
                "total_sessions": total_sessions,
                "attendance_ratio": f"{attended_count}/{total_sessions}",
                "attendance_percentage": attendance_percentage,
                "attendance_status": attendance_status
            },
            "enrolled_at": str(enrollment.enrolled_at)
        })

    return result


# This part is for section Registration


@router.get("/student/courses/{course_id}/practical-sections")
def get_student_practical_sections(
    course_id: int,
    current_student: Student = Depends(get_current_student),
    db: Session = Depends(get_db)
):
    enrollment = (
        db.query(StudentCourse)
        .filter(
            StudentCourse.student_id == current_student.student_id,
            StudentCourse.course_id == course_id
        )
        .first()
    )

    if not enrollment:
        raise HTTPException(
            status_code=403,
            detail="You are not enrolled in this course"
        )

    course = (
        db.query(Course)
        .filter(Course.course_id == course_id)
        .first()
    )

    if not course:
        raise HTTPException(
            status_code=404,
            detail="Course not found"
        )

    sections = (
        db.query(CourseSection)
        .filter(
            CourseSection.course_id == course_id,
            CourseSection.is_active == True
        )
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

        section_schedules = [
            {
                "weekday": schedule.weekday,
                "weekday_name": [
                    "Monday",
                    "Tuesday",
                    "Wednesday",
                    "Thursday",
                    "Friday",
                    "Saturday",
                    "Sunday",
                ][schedule.weekday],
                "start_time": str(schedule.start_time),
                "end_time": str(schedule.end_time),
                "repeat_interval_weeks": schedule.repeat_interval_weeks,
            }
            for schedule in section.schedules
            if schedule.is_active
        ]

        result.append(
            {
                "section_id": section.section_id,
                "section_name": section.section_name,
                "capacity": section.capacity,
                "classroom_id": section.classroom_id,
                "classroom_name": section.classroom.name,
                "building": section.classroom.building,
                "room_number": section.classroom.room_number,
                "enrolled_students_count": enrolled_students_count,
                "available_seats": max(
                    section.capacity - enrolled_students_count,
                    0
                ),
                "schedules": section_schedules,
                "is_selected_by_student": (
                    enrollment.section_id == section.section_id
                )
            }
        )

    return {
        "course": {
            "course_id": course.course_id,
            "course_name": course.course_name
        },
        "selected_section_id": enrollment.section_id,
        "sections": result
    }


@router.post("/student/courses/{course_id}/select-practical-section")
def select_student_practical_section(
    course_id: int,
    section_id: int = Body(..., embed=True),
    current_student: Student = Depends(get_current_student),
    db: Session = Depends(get_db)
):
    if not current_student.is_active:
        raise HTTPException(
            status_code=403,
            detail="Student account is inactive"
        )

    # Lock this student's enrollment row while selecting/switching.
    enrollment = (
        db.query(StudentCourse)
        .filter(
            StudentCourse.student_id == current_student.student_id,
            StudentCourse.course_id == course_id
        )
        .with_for_update()
        .first()
    )

    if not enrollment:
        raise HTTPException(
            status_code=403,
            detail="You are not enrolled in this course"
        )

    # A student cannot change section after practical attendance exists.
    practical_attendance_exists = (
        db.query(Attendance)
        .join(
            ClassSession,
            Attendance.session_id == ClassSession.session_id
        )
        .filter(
            Attendance.student_id == current_student.student_id,
            ClassSession.course_id == course_id,
            ClassSession.session_type == "practical"
        )
        .first()
    )

    if practical_attendance_exists:
        raise HTTPException(
            status_code=400,
            detail=(
                "You cannot change your practical section because "
                "you already have practical attendance records"
            )
        )

    # Lock the selected section too, so two students cannot take
    # the final available seat at the same time.
    section = (
        db.query(CourseSection)
        .filter(
            CourseSection.section_id == section_id,
            CourseSection.course_id == course_id,
            CourseSection.is_active == True
        )
        .with_for_update()
        .first()
    )

    if not section:
        raise HTTPException(
            status_code=404,
            detail="Active practical section not found in this course"
        )

    # If the student already chose this section, return normally.
    if enrollment.section_id == section.section_id:
        return {
            "message": "This practical section is already selected",
            "course_id": course_id,
            "section_id": section.section_id,
            "section_name": section.section_name
        }

    enrolled_students_count = (
        db.query(StudentCourse)
        .filter(StudentCourse.section_id == section.section_id)
        .count()
    )

    if enrolled_students_count >= section.capacity:
        raise HTTPException(
            status_code=400,
            detail="This practical section is full"
        )

    enrollment.section_id = section.section_id

    db.commit()
    db.refresh(enrollment)

    return {
        "message": "Practical section selected successfully",
        "course_id": course_id,
        "section": {
            "section_id": section.section_id,
            "section_name": section.section_name,
            "classroom_id": section.classroom_id,
            "classroom_name": section.classroom.name,
            "enrolled_students_count": enrolled_students_count + 1,
            "available_seats": max(
                section.capacity - (enrolled_students_count + 1),
                0
            )
        }
    }



# This is the end of the section Registration




def create_notification_if_not_exists(
    db: Session,
    student_id: int,
    title: str,
    message: str,
    notification_type: str,
    notification_key: str,
    send_push: bool = True
):
    existing_notification = (
        db.query(StudentNotification)
        .filter(StudentNotification.notification_key == notification_key)
        .first()
    )

    if existing_notification:
        return

    notification = StudentNotification(
        student_id=student_id,
        title=title,
        message=message,
        notification_type=notification_type,
        notification_key=notification_key,
        is_read=False
    )

    db.add(notification)

    if send_push:
        send_push_to_student(
            db=db,
            student_id=student_id,
            title=title,
            message=message,
            notification_type=notification_type
        )



def send_push_to_student(
    db: Session,
    student_id: int,
    title: str,
    message: str,
    notification_type: str
):
    active_tokens = (
        db.query(StudentDeviceToken)
        .filter(
            StudentDeviceToken.student_id == student_id,
            StudentDeviceToken.is_active == True
        )
        .all()
    )

    for token_record in active_tokens:
        try:
            send_push_notification_to_token(
                fcm_token=token_record.fcm_token,
                title=title,
                body=message,
                data={
                    "type": notification_type
                }
            )
        except Exception:
            # Do not break notification generation if one push fails.
            pass




@router.get("/student/notifications")
def get_student_notifications(
    current_student: Student = Depends(get_current_student),
    db: Session = Depends(get_db)
):
    if not current_student.is_active:
        raise HTTPException(
            status_code=403,
            detail="Student account is inactive"
        )

    now = now_syria()

    enrollments = (
        db.query(StudentCourse, Course, Teacher)
        .join(Course, StudentCourse.course_id == Course.course_id)
        .join(Teacher, Course.teacher_id == Teacher.teacher_id)
        .filter(StudentCourse.student_id == current_student.student_id)
        .all()
    )

    for enrollment, course, teacher in enrollments:
        all_course_sessions = (
            db.query(ClassSession)
            .filter(ClassSession.course_id == course.course_id)
            .all()
        )

        # Keep only sessions this student is actually allowed to attend.
        valid_sessions = []

        for session in all_course_sessions:
            session_type = session.session_type or "theory"

            # Theory belongs to every enrolled student.
            # Practical belongs only to the student's selected section.
            if (
                session_type == "practical"
                and enrollment.section_id != session.section_id
            ):
                continue

            valid_sessions.append(session)

        # ---------- Attendance warning calculation ----------
        attended_count = 0
        total_counted_sessions = 0

        for session in valid_sessions:
            attendance = (
                db.query(Attendance)
                .filter(
                    Attendance.student_id == current_student.student_id,
                    Attendance.session_id == session.session_id
                )
                .first()
            )

            attendance_close_dt = datetime.combine(
                session.session_date,
                session.attendance_close_time
            )

            if attendance:
                attended_count += 1
                total_counted_sessions += 1
            elif attendance_close_dt <= now:
                total_counted_sessions += 1

        if total_counted_sessions > 0:
            attendance_percentage = round(
                (attended_count / total_counted_sessions) * 100,
                2
            )

            if attendance_percentage < 70:
                create_notification_if_not_exists(
                    db=db,
                    student_id=current_student.student_id,
                    title="Attendance Warning",
                    message=(
                        f"Your attendance in {course.course_name} is below 70%. "
                        f"Current attendance: {attendance_percentage}%"
                    ),
                    notification_type="attendance_risk",
                    notification_key=(
                        f"attendance_risk:"
                        f"{current_student.student_id}:"
                        f"{course.course_id}:"
                        f"{attended_count}:"
                        f"{total_counted_sessions}"
                    )
                )

        # ---------- Session reminder notifications ----------
        for session in valid_sessions:
            existing_attendance = (
                db.query(Attendance)
                .filter(
                    Attendance.student_id == current_student.student_id,
                    Attendance.session_id == session.session_id
                )
                .first()
            )

            if existing_attendance:
                continue

            session_start_dt = datetime.combine(
                session.session_date,
                session.start_time
            )

            attendance_open_dt = datetime.combine(
                session.session_date,
                session.attendance_open_time
            )

            attendance_close_dt = datetime.combine(
                session.session_date,
                session.attendance_close_time
            )

            if (
                session_start_dt - timedelta(minutes=60)
                <= now
                < session_start_dt - timedelta(minutes=45)
            ):
                create_notification_if_not_exists(
                    db=db,
                    student_id=current_student.student_id,
                    title="Upcoming Session",
                    message=f"{course.course_name} starts in about 1 hour.",
                    notification_type="session_reminder",
                    notification_key=(
                        f"session_60:"
                        f"{current_student.student_id}:"
                        f"{session.session_id}"
                    )
                )

            if (
                session_start_dt - timedelta(minutes=15)
                <= now
                < session_start_dt
            ):
                create_notification_if_not_exists(
                    db=db,
                    student_id=current_student.student_id,
                    title="Session Starting Soon",
                    message=f"{course.course_name} starts in about 15 minutes.",
                    notification_type="session_reminder",
                    notification_key=(
                        f"session_15:"
                        f"{current_student.student_id}:"
                        f"{session.session_id}"
                    )
                )

            if (
                attendance_open_dt
                <= now
                < attendance_open_dt + timedelta(minutes=15)
            ):
                create_notification_if_not_exists(
                    db=db,
                    student_id=current_student.student_id,
                    title="Attendance Is Open",
                    message=f"Attendance is now open for {course.course_name}.",
                    notification_type="attendance_open",
                    notification_key=(
                        f"attendance_open:"
                        f"{current_student.student_id}:"
                        f"{session.session_id}"
                    )
                )

            if (
                attendance_close_dt - timedelta(minutes=15)
                <= now
                < attendance_close_dt
            ):
                create_notification_if_not_exists(
                    db=db,
                    student_id=current_student.student_id,
                    title="Attendance Closing Soon",
                    message=(
                        f"Attendance for {course.course_name} "
                        f"closes in about 15 minutes."
                    ),
                    notification_type="attendance_closing",
                    notification_key=(
                        f"attendance_close_15:"
                        f"{current_student.student_id}:"
                        f"{session.session_id}"
                    )
                )

    db.commit()

    notifications = (
        db.query(StudentNotification)
        .filter(StudentNotification.student_id == current_student.student_id)
        .order_by(StudentNotification.created_at.desc())
        .all()
    )

    unread_count = (
        db.query(StudentNotification)
        .filter(
            StudentNotification.student_id == current_student.student_id,
            StudentNotification.is_read == False
        )
        .count()
    )

    return {
        "unread_count": unread_count,
        "notifications": [
            {
                "notification_id": notification.notification_id,
                "title": notification.title,
                "message": notification.message,
                "notification_type": notification.notification_type,
                "is_read": notification.is_read,
                "created_at": str(notification.created_at)
            }
            for notification in notifications
        ]
    }



@router.put("/student/notifications/{notification_id}/read")
def mark_student_notification_as_read(
    notification_id: int,
    current_student: Student = Depends(get_current_student),
    db: Session = Depends(get_db)
):
    notification = (
        db.query(StudentNotification)
        .filter(
            StudentNotification.notification_id == notification_id,
            StudentNotification.student_id == current_student.student_id
        )
        .first()
    )

    if not notification:
        raise HTTPException(
            status_code=404,
            detail="Notification not found"
        )

    notification.is_read = True

    db.commit()
    db.refresh(notification)

    return {
        "message": "Notification marked as read",
        "notification_id": notification.notification_id
    }




@router.post("/auth/firebase-student-login")
def firebase_student_login(
    request: FirebaseLoginRequest,
    db: Session = Depends(get_db),
):
    try:
        firebase_user = verify_firebase_token(request.firebase_token)
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e))

    email = firebase_user["email"]

    student = db.query(Student).filter(Student.email == email).first()

    if not student:
        raise HTTPException(
            status_code=404,
            detail="No student account found in the backend for this verified email.",
        )

    if not student.is_active:
        raise HTTPException(
            status_code=403,
            detail="Student account is inactive",
        )

    # Since Firebase already verified the email, keep your backend record verified too
    if not student.email_verified:
        student.email_verified = True
        student.verification_token = None
        db.commit()
        db.refresh(student)

    access_token = create_access_token(
        data={
            "sub": str(student.student_id),
            "email": student.email,
            "role": "student",
        }
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "student_id": student.student_id,
        "full_name": student.full_name,
        "email": student.email,
        "university_number": student.university_number,
        "year_of_study": student.year_of_study,
    }



@router.post("/auth/firebase-student-register")
def firebase_student_register(
    request: FirebaseStudentRegisterRequest,
    db: Session = Depends(get_db),
):
    try:
        firebase_user = verify_firebase_token_for_registration(request.firebase_token)
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e))

    email = firebase_user["email"]

    existing_student = db.query(Student).filter(Student.email == email).first()
    if existing_student:
        raise HTTPException(status_code=400, detail="Email already registered")

    existing_national = (
        db.query(Student)
        .filter(Student.national_number == request.national_number)
        .first()
    )
    if existing_national:
        raise HTTPException(status_code=400, detail="National number already registered")

    existing_university = (
        db.query(Student)
        .filter(Student.university_number == request.university_number)
        .first()
    )
    if existing_university:
        raise HTTPException(status_code=400, detail="University number already registered")

    if request.year_of_study < 1 or request.year_of_study > 5:
        raise HTTPException(status_code=400, detail="Year of study must be between 1 and 5")

    new_student = Student(
        email=email,
        password_hash=hash_password("FIREBASE_AUTH_USER_NO_LOCAL_PASSWORD"),
        email_verified=firebase_user["email_verified"],
        verification_token=None,
        national_number=request.national_number,
        university_number=request.university_number,
        full_name=request.full_name,
        year_of_study=request.year_of_study,
        is_active=True,
    )

    db.add(new_student)
    db.commit()
    db.refresh(new_student)

    access_token = create_access_token(
        data={
            "sub": str(new_student.student_id),
            "email": new_student.email,
            "role": "student",
        }
    )

    return {
        "message": "Student registered successfully with verified Firebase email",
        "access_token": access_token,
        "token_type": "bearer",
        "student_id": new_student.student_id,
        "full_name": new_student.full_name,
        "email": new_student.email,
        "university_number": new_student.university_number,
        "year_of_study": new_student.year_of_study,
    }




@router.post("/student/fcm-token")
def save_student_fcm_token(
    request: SaveFcmTokenRequest,
    current_student: Student = Depends(get_current_student),
    db: Session = Depends(get_db)
):
    clean_token = request.fcm_token.strip()

    if not clean_token:
        raise HTTPException(
            status_code=400,
            detail="FCM token cannot be empty"
        )

    existing_token = (
        db.query(StudentDeviceToken)
        .filter(StudentDeviceToken.fcm_token == clean_token)
        .first()
    )

    if existing_token:
        existing_token.student_id = current_student.student_id
        existing_token.platform = request.platform
        existing_token.is_active = True
        existing_token.last_seen_at = datetime.now()

        db.commit()
        db.refresh(existing_token)

        return {
            "message": "FCM token updated successfully",
            "token_id": existing_token.id
        }

    new_token = StudentDeviceToken(
        student_id=current_student.student_id,
        fcm_token=clean_token,
        platform=request.platform,
        is_active=True,
        last_seen_at=datetime.now()
    )

    db.add(new_token)
    db.commit()
    db.refresh(new_token)

    return {
        "message": "FCM token saved successfully",
        "token_id": new_token.id
    }



@router.post("/student/test-push")
def send_student_test_push(
    current_student: Student = Depends(get_current_student),
    db: Session = Depends(get_db)
):
    active_tokens = (
        db.query(StudentDeviceToken)
        .filter(
            StudentDeviceToken.student_id == current_student.student_id,
            StudentDeviceToken.is_active == True
        )
        .all()
    )

    if not active_tokens:
        raise HTTPException(
            status_code=400,
            detail="No active FCM tokens found for this student"
        )

    sent_count = 0
    failed_tokens = []

    for token_record in active_tokens:
        try:
            send_push_notification_to_token(
                fcm_token=token_record.fcm_token,
                title="Attendance App Test",
                body="Push notifications are working successfully.",
                data={
                    "type": "test_push"
                }
            )
            sent_count += 1
        except Exception as e:
            failed_tokens.append({
                "token_id": token_record.id,
                "error": str(e)
            })

    return {
        "message": "Test push completed",
        "sent_count": sent_count,
        "failed_tokens": failed_tokens
    }















@router.post("/student/test-antispoofing")
def test_antispoofing_on_uploaded_image(
    image: UploadFile = File(...),
    current_student: Student = Depends(get_current_student),
):
    temp_path = f"temp_antispoofing_{current_student.student_id}_{image.filename}"

    with open(temp_path, "wb") as buffer:
        buffer.write(image.file.read())

    try:
        result = anti_spoofing_service.predict_image(temp_path)
        return result
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)









@router.get("/student/sessions/{session_id}/pdf-info")
def get_student_session_pdf_info(
    session_id: int,
    current_student: Student = Depends(get_current_student),
    db: Session = Depends(get_db)
):
    session = (
        db.query(ClassSession)
        .filter(ClassSession.session_id == session_id)
        .first()
    )

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    enrollment = (
        db.query(StudentCourse)
        .filter(
            StudentCourse.student_id == current_student.student_id,
            StudentCourse.course_id == session.course_id
        )
        .first()
    )

    if not enrollment:
        raise HTTPException(
            status_code=403,
            detail="You are not enrolled in this course"
        )

    session_type = session.session_type or "theory"

    if (
        session_type == "practical"
        and enrollment.section_id != session.section_id
    ):
        raise HTTPException(
            status_code=403,
            detail=(
                "You are not assigned to the practical section "
                "for this session"
            )
        )

    has_pdf = bool(session.pdf_file_path and os.path.exists(session.pdf_file_path))

    return {
        "session_id": session.session_id,
        "has_pdf": has_pdf,
        "pdf_original_name": session.pdf_original_name if has_pdf else None
    }






@router.get("/student/sessions/{session_id}/pdf")
def download_student_session_pdf(
    session_id: int,
    current_student: Student = Depends(get_current_student),
    db: Session = Depends(get_db)
):
    session = (
        db.query(ClassSession)
        .filter(ClassSession.session_id == session_id)
        .first()
    )

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    enrollment = (
        db.query(StudentCourse)
        .filter(
            StudentCourse.student_id == current_student.student_id,
            StudentCourse.course_id == session.course_id
        )
        .first()
    )

    if not enrollment:
        raise HTTPException(
            status_code=403,
            detail="You are not enrolled in this course"
        )
    session_type = session.session_type or "theory"

    if (
        session_type == "practical"
        and enrollment.section_id != session.section_id
    ):
        raise HTTPException(
            status_code=403,
            detail=(
                "You are not assigned to the practical section "
                "for this session"
            )
        )

    if not session.pdf_file_path or not os.path.exists(session.pdf_file_path):
        raise HTTPException(
            status_code=404,
            detail="No PDF uploaded for this session"
        )

    return FileResponse(
        path=session.pdf_file_path,
        media_type="application/pdf",
        filename=session.pdf_original_name or f"session_{session_id}.pdf"
    )





