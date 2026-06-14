import os
import shutil
from fastapi import UploadFile, File
from fastapi.responses import FileResponse
from app.core.config import SESSION_PDFS_DIR

from datetime import datetime
from app.core.time_utils import now_syria

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from typing import Optional

from app.database import get_db
from app.dependencies.auth_dependencies import get_current_student
from app.dependencies.auth_dependencies import get_current_teacher
from app.models import (
    Teacher,
    Course,
    Classroom,
    ClassSession,
    StudentCourse,
    Student,
    Attendance,
)
from app.schemas.session_schema import CreateSessionRequest, UpdateSessionRequest


router = APIRouter(prefix="/teacher", tags=["Teacher Sessions"])

@router.post("/courses/{course_id}/sessions")
def create_course_session(
    course_id: int,
    request: CreateSessionRequest,
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

    # 2) Check classroom exists
    classroom = (
        db.query(Classroom)
        .filter(Classroom.classroom_id == request.classroom_id)
        .first()
    )

    if not classroom:
        raise HTTPException(status_code=404, detail="Classroom not found")

    # 3) Parse date and time strings
    try:
        parsed_session_date = datetime.strptime(request.session_date, "%Y-%m-%d").date()
        parsed_start_time = datetime.strptime(request.start_time, "%H:%M:%S").time()
        parsed_end_time = datetime.strptime(request.end_time, "%H:%M:%S").time()
        parsed_attendance_open_time = datetime.strptime(request.attendance_open_time, "%H:%M:%S").time()
        parsed_attendance_close_time = datetime.strptime(request.attendance_close_time, "%H:%M:%S").time()
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid date/time format. Use YYYY-MM-DD for date and HH:MM:SS for time"
        )

    # 4) Validate time order
    if parsed_start_time >= parsed_end_time:
        raise HTTPException(
            status_code=400,
            detail="Session start_time must be earlier than end_time"
        )

    if parsed_attendance_open_time > parsed_attendance_close_time:
        raise HTTPException(
            status_code=400,
            detail="Attendance open time must be earlier than or equal to attendance close time"
        )

    if parsed_attendance_open_time < parsed_start_time:
        raise HTTPException(
            status_code=400,
            detail="Attendance open time cannot be earlier than session start time"
        )

    if parsed_attendance_close_time > parsed_end_time:
        raise HTTPException(
            status_code=400,
            detail="Attendance close time cannot be later than session end time"
        )

    # 5) Create the session
    new_session = ClassSession(
        course_id=course.course_id,
        classroom_id=request.classroom_id,
        session_date=parsed_session_date,
        start_time=parsed_start_time,
        end_time=parsed_end_time,
        attendance_open_time=parsed_attendance_open_time,
        attendance_close_time=parsed_attendance_close_time
    )

    db.add(new_session)
    db.commit()
    db.refresh(new_session)

    return {
        "message": "Session created successfully",
        "session_id": new_session.session_id,
        "course": {
            "course_id": course.course_id,
            "course_name": course.course_name
        },
        "classroom": {
            "classroom_id": classroom.classroom_id,
            "name": classroom.name,
            "building": classroom.building,
            "room_number": classroom.room_number
        },
        "session_date": str(new_session.session_date),
        "start_time": str(new_session.start_time),
        "end_time": str(new_session.end_time),
        "attendance_open_time": str(new_session.attendance_open_time),
        "attendance_close_time": str(new_session.attendance_close_time)
    }


@router.put("/sessions/{session_id}")
def update_teacher_session(
    session_id: int,
    request: UpdateSessionRequest,
    current_teacher: Teacher = Depends(get_current_teacher),
    db: Session = Depends(get_db)
):
    # 1) Load the session and verify ownership through the course
    session_record = (
        db.query(ClassSession, Course)
        .join(Course, ClassSession.course_id == Course.course_id)
        .filter(
            ClassSession.session_id == session_id,
            Course.teacher_id == current_teacher.teacher_id
        )
        .first()
    )

    if not session_record:
        raise HTTPException(
            status_code=404,
            detail="Session not found or does not belong to this teacher"
        )

    session, course = session_record

    # 2) Check classroom exists
    classroom = (
        db.query(Classroom)
        .filter(Classroom.classroom_id == request.classroom_id)
        .first()
    )

    if not classroom:
        raise HTTPException(status_code=404, detail="Classroom not found")

    # 3) Parse date and time strings
    try:
        parsed_session_date = datetime.strptime(request.session_date, "%Y-%m-%d").date()
        parsed_start_time = datetime.strptime(request.start_time, "%H:%M:%S").time()
        parsed_end_time = datetime.strptime(request.end_time, "%H:%M:%S").time()
        parsed_attendance_open_time = datetime.strptime(request.attendance_open_time, "%H:%M:%S").time()
        parsed_attendance_close_time = datetime.strptime(request.attendance_close_time, "%H:%M:%S").time()
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid date/time format. Use YYYY-MM-DD for date and HH:MM:SS for time"
        )

    # 4) Validate time logic
    if parsed_start_time >= parsed_end_time:
        raise HTTPException(
            status_code=400,
            detail="Session start_time must be earlier than end_time"
        )

    if parsed_attendance_open_time > parsed_attendance_close_time:
        raise HTTPException(
            status_code=400,
            detail="Attendance open time must be earlier than or equal to attendance close time"
        )

    if parsed_attendance_open_time < parsed_start_time:
        raise HTTPException(
            status_code=400,
            detail="Attendance open time cannot be earlier than session start time"
        )

    if parsed_attendance_close_time > parsed_end_time:
        raise HTTPException(
            status_code=400,
            detail="Attendance close time cannot be later than session end time"
        )

    # 5) Update session fields
    session.classroom_id = request.classroom_id
    session.session_date = parsed_session_date
    session.start_time = parsed_start_time
    session.end_time = parsed_end_time
    session.attendance_open_time = parsed_attendance_open_time
    session.attendance_close_time = parsed_attendance_close_time

    db.commit()
    db.refresh(session)

    return {
        "message": "Session updated successfully",
        "session_id": session.session_id,
        "course": {
            "course_id": course.course_id,
            "course_name": course.course_name
        },
        "classroom": {
            "classroom_id": classroom.classroom_id,
            "name": classroom.name,
            "building": classroom.building,
            "room_number": classroom.room_number
        },
        "session_date": str(session.session_date),
        "start_time": str(session.start_time),
        "end_time": str(session.end_time),
        "attendance_open_time": str(session.attendance_open_time),
        "attendance_close_time": str(session.attendance_close_time)
    }

@router.delete("/sessions/{session_id}")
def delete_teacher_session(
    session_id: int,
    current_teacher: Teacher = Depends(get_current_teacher),
    db: Session = Depends(get_db)
):
    # 1) Load the session and verify ownership through the course
    session_record = (
        db.query(ClassSession, Course)
        .join(Course, ClassSession.course_id == Course.course_id)
        .filter(
            ClassSession.session_id == session_id,
            Course.teacher_id == current_teacher.teacher_id
        )
        .first()
    )

    if not session_record:
        raise HTTPException(
            status_code=404,
            detail="Session not found or does not belong to this teacher"
        )

    session, course = session_record

    attendance_exists = (
        db.query(Attendance)
        .filter(Attendance.session_id == session_id)
        .first()
        )

    if attendance_exists:
        raise HTTPException(
            status_code=400,
            detail="Cannot delete a session that already has attendance records"
        )

    db.delete(session)
    db.commit()

    return {
            "message": "Session deleted successfully",
            "session_id": session_id,
            "course_id": course.course_id
        }



@router.get("/sessions/{session_id}/attendance-report")
def get_session_attendance_report(
    session_id: int,
    current_teacher: Teacher = Depends(get_current_teacher),
    db: Session = Depends(get_db)
):
    session_record = (
        db.query(ClassSession, Course, Classroom)
        .join(Course, ClassSession.course_id == Course.course_id)
        .join(Classroom, ClassSession.classroom_id == Classroom.classroom_id)
        .filter(
            ClassSession.session_id == session_id,
            Course.teacher_id == current_teacher.teacher_id
        )
        .first()
    )

    if not session_record:
        raise HTTPException(
            status_code=404,
            detail="Session not found or does not belong to this teacher"
        )

    session, course, classroom = session_record

    enrolled_records = (
        db.query(StudentCourse, Student)
        .join(Student, StudentCourse.student_id == Student.student_id)
        .filter(StudentCourse.course_id == course.course_id)
        .all()
    )

    attendance_records = (
        db.query(Attendance, Student)
        .join(Student, Attendance.student_id == Student.student_id)
        .filter(Attendance.session_id == session_id)
        .all()
    )

    attended_student_ids = {
        attendance.student_id
        for attendance, student in attendance_records
    }

    present_students = [
        {
            "student_id": student.student_id,
            "full_name": student.full_name,
            "email": student.email,
            "university_number": student.university_number,
            "status": attendance.status,
            "confidence_score": attendance.confidence_score,
            "distance_from_class_meters": attendance.distance_from_class_meters,
            "captured_at": str(attendance.captured_at),
            "image_path": attendance.image_path
        }
        for attendance, student in attendance_records
    ]

    now = now_syria()
    attendance_close_dt = datetime.combine(
        session.session_date,
        session.attendance_close_time
    )
    attendance_finalized = attendance_close_dt <= now

    absent_students = [
        {
            "student_id": student.student_id,
            "full_name": student.full_name,
            "email": student.email,
            "university_number": student.university_number,
            "year_of_study": student.year_of_study,
            "attendance_status": "Absent"
        }
        for student_course, student in enrolled_records
        if student.student_id not in attended_student_ids and attendance_finalized
    ]

    return {
        "teacher": {
            "teacher_id": current_teacher.teacher_id,
            "full_name": current_teacher.full_name
        },
        "course": {
            "course_id": course.course_id,
            "course_name": course.course_name,
            "year_of_study": course.year_of_study
        },
        "session": {
            "session_id": session.session_id,
            "session_date": str(session.session_date),
            "start_time": str(session.start_time),
            "end_time": str(session.end_time),
            "attendance_open_time": str(session.attendance_open_time),
            "attendance_close_time": str(session.attendance_close_time)
        },
        "classroom": {
            "classroom_id": classroom.classroom_id,
            "name": classroom.name,
            "building": classroom.building,
            "room_number": classroom.room_number
        },
        "summary": {
            "attendance_finalized": attendance_finalized,
            "total_enrolled": len(enrolled_records),
            "total_present": len(present_students),
            "total_absent": len(absent_students) if attendance_finalized else 0
        },
        "present_students": present_students,
        "absent_students": absent_students
    }


@router.get("/courses/{course_id}/sessions")
def get_course_sessions(
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

    # 2) Get all sessions for this course
    records = (
        db.query(ClassSession, Classroom)
        .join(Classroom, ClassSession.classroom_id == Classroom.classroom_id)
        .filter(ClassSession.course_id == course_id)
        .order_by(ClassSession.session_date.asc(), ClassSession.start_time.asc())
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
        "sessions": [
            {
                "session_id": session.session_id,
                "session_date": str(session.session_date),
                "start_time": str(session.start_time),
                "end_time": str(session.end_time),
                "attendance_open_time": str(session.attendance_open_time),
                "attendance_close_time": str(session.attendance_close_time),
                "classroom": {
                    "classroom_id": classroom.classroom_id,
                    "name": classroom.name,
                    "building": classroom.building,
                    "room_number": classroom.room_number
                }
            }
            for session, classroom in records
        ],
        "total_sessions": len(records)
    }

@router.get("/courses/{course_id}/attendance-summary")
def get_course_attendance_summary(
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

    now = now_syria()

    course_sessions = (
        db.query(ClassSession)
        .filter(ClassSession.course_id == course_id)
        .order_by(ClassSession.session_date.asc(), ClassSession.start_time.asc())
        .all()
    )

    enrolled_records = (
        db.query(StudentCourse, Student)
        .join(Student, StudentCourse.student_id == Student.student_id)
        .filter(StudentCourse.course_id == course_id)
        .all()
    )

    session_ids = [session.session_id for session in course_sessions]

    attendance_records = []
    if session_ids:
        attendance_records = (
            db.query(Attendance)
            .filter(Attendance.session_id.in_(session_ids))
            .all()
        )

    attendance_lookup = {
        (attendance.session_id, attendance.student_id)
        for attendance in attendance_records
    }

    student_summaries = []

    for student_course, student in enrolled_records:
        attended_count = 0
        absent_count = 0
        total_sessions = 0

        for session in course_sessions:
            attendance_close_dt = datetime.combine(
                session.session_date,
                session.attendance_close_time
            )

            has_attended = (session.session_id, student.student_id) in attendance_lookup

            # Count immediately if this student attended
            if has_attended:
                attended_count += 1
                total_sessions += 1
            # Count as absent only after this session's window closes
            elif attendance_close_dt <= now:
                absent_count += 1
                total_sessions += 1
            # Otherwise do not count yet
            else:
                pass

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

        student_summaries.append({
            "student_id": student.student_id,
            "full_name": student.full_name,
            "email": student.email,
            "university_number": student.university_number,
            "year_of_study": student.year_of_study,
            "attended_sessions": attended_count,
            "absent_sessions": absent_count,
            "total_sessions": total_sessions,
            "attendance_ratio": f"{attended_count}/{total_sessions}",
            "attendance_percentage": attendance_percentage,
            "attendance_status": attendance_status
        })

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
        "summary": {
            "total_course_sessions": len(course_sessions),
            "total_enrolled_students": len(enrolled_records),
            "counting_rule": "Attended sessions are counted immediately for each student; absences are counted only after that student's attendance window closes"
        },
        "students": student_summaries
    }


@router.get("/classrooms/{classroom_id}/sessions-history")
def get_classroom_sessions_history(
    classroom_id: int,
    start_date: Optional[str] = Query(default=None),
    end_date: Optional[str] = Query(default=None),
    course_id: Optional[int] = Query(default=None),
    current_teacher: Teacher = Depends(get_current_teacher),
    db: Session = Depends(get_db)
):
    # 1) Check classroom exists
    classroom = (
        db.query(Classroom)
        .filter(Classroom.classroom_id == classroom_id)
        .first()
    )

    if not classroom:
        raise HTTPException(status_code=404, detail="Classroom not found")

    # 2) Validate optional course filter
    selected_course = None

    if course_id is not None:
        selected_course = (
            db.query(Course)
            .filter(
                Course.course_id == course_id,
                Course.teacher_id == current_teacher.teacher_id
            )
            .first()
        )

        if not selected_course:
            raise HTTPException(
                status_code=404,
                detail="Course not found or does not belong to this teacher"
            )

    # 3) Validate optional date filter
    parsed_start_date = None
    parsed_end_date = None

    if (start_date and not end_date) or (end_date and not start_date):
        raise HTTPException(
            status_code=400,
            detail="Please provide both start_date and end_date, or leave both empty"
        )

    if start_date and end_date:
        try:
            parsed_start_date = datetime.strptime(start_date, "%Y-%m-%d").date()
            parsed_end_date = datetime.strptime(end_date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="Invalid date format. Use YYYY-MM-DD"
            )

        if parsed_start_date > parsed_end_date:
            raise HTTPException(
                status_code=400,
                detail="start_date cannot be after end_date"
            )

    # 4) Base query: classroom sessions owned by this teacher
    query = (
        db.query(ClassSession, Course)
        .join(Course, ClassSession.course_id == Course.course_id)
        .filter(
            ClassSession.classroom_id == classroom_id,
            Course.teacher_id == current_teacher.teacher_id
        )
    )

    # 5) Optional course filter
    if course_id is not None:
        query = query.filter(ClassSession.course_id == course_id)

    # 6) Optional date range filter
    if parsed_start_date and parsed_end_date:
        query = query.filter(
            ClassSession.session_date >= parsed_start_date,
            ClassSession.session_date <= parsed_end_date
        )

    records = (
        query
        .order_by(ClassSession.session_date.desc(), ClassSession.start_time.desc())
        .all()
    )

    session_ids = [session.session_id for session, course in records]
    course_ids = list({course.course_id for session, course in records})

    # 7) Build enrolled-count lookup per course
    enrolled_count_lookup = {}

    if course_ids:
        enrolled_records = (
            db.query(StudentCourse.course_id, StudentCourse.student_id)
            .filter(StudentCourse.course_id.in_(course_ids))
            .all()
        )

        for course_id_value, student_id_value in enrolled_records:
            enrolled_count_lookup[course_id_value] = (
                enrolled_count_lookup.get(course_id_value, 0) + 1
            )

    # 8) Build present-count lookup per session
    present_count_lookup = {}

    if session_ids:
        attendance_records = (
            db.query(Attendance.session_id, Attendance.student_id)
            .filter(
                Attendance.session_id.in_(session_ids),
                Attendance.status == "present"
            )
            .all()
        )

        for session_id_value, student_id_value in attendance_records:
            present_count_lookup[session_id_value] = (
                present_count_lookup.get(session_id_value, 0) + 1
            )

    # 9) Format response
    now = now_syria()
    sessions_result = []

    for session, course in records:
        attendance_close_dt = datetime.combine(
            session.session_date,
            session.attendance_close_time
        )

        attendance_finalized = attendance_close_dt <= now

        total_enrolled = enrolled_count_lookup.get(course.course_id, 0)
        total_present = present_count_lookup.get(session.session_id, 0)

        total_absent = 0
        if attendance_finalized:
            total_absent = total_enrolled - total_present

        attendance_percentage = 0.0
        if total_enrolled > 0:
            attendance_percentage = round((total_present / total_enrolled) * 100, 2)

        sessions_result.append({
            "session_id": session.session_id,
            "course_id": course.course_id,
            "course_name": course.course_name,
            "year_of_study": course.year_of_study,
            "session_date": str(session.session_date),
            "start_time": str(session.start_time),
            "end_time": str(session.end_time),
            "attendance_open_time": str(session.attendance_open_time),
            "attendance_close_time": str(session.attendance_close_time),
            "attendance_finalized": attendance_finalized,
            "total_enrolled": total_enrolled,
            "total_present": total_present,
            "total_absent": total_absent,
            "attendance_percentage": attendance_percentage
        })

    return {
        "teacher": {
            "teacher_id": current_teacher.teacher_id,
            "full_name": current_teacher.full_name
        },
        "classroom": {
            "classroom_id": classroom.classroom_id,
            "name": classroom.name,
            "building": classroom.building,
            "room_number": classroom.room_number
        },
        "filters": {
            "start_date": start_date,
            "end_date": end_date,
            "course_id": course_id,
            "course_name": selected_course.course_name if selected_course else None,
            "date_filter_applied": bool(start_date and end_date),
            "course_filter_applied": course_id is not None
        },
        "summary": {
            "total_sessions": len(sessions_result)
        },
        "sessions": sessions_result
    }


@router.post("/sessions/{session_id}/pdf")
def upload_session_pdf(
    session_id: int,
    pdf_file: UploadFile = File(...),
    current_teacher: Teacher = Depends(get_current_teacher),
    db: Session = Depends(get_db)
):
    session = (
        db.query(ClassSession)
        .join(Course, ClassSession.course_id == Course.course_id)
        .filter(
            ClassSession.session_id == session_id,
            Course.teacher_id == current_teacher.teacher_id
        )
        .first()
    )

    if not session:
        raise HTTPException(
            status_code=404,
            detail="Session not found or does not belong to this teacher"
        )

    if not pdf_file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=400,
            detail="Only PDF files are allowed"
        )

    os.makedirs(SESSION_PDFS_DIR, exist_ok=True)

    safe_filename = f"session_{session_id}.pdf"
    file_path = os.path.join(SESSION_PDFS_DIR, safe_filename)

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(pdf_file.file, buffer)

    session.pdf_file_path = file_path
    session.pdf_original_name = pdf_file.filename

    db.commit()
    db.refresh(session)

    return {
        "message": "PDF uploaded successfully",
        "session_id": session.session_id,
        "pdf_original_name": session.pdf_original_name
    }



@router.get("/sessions/{session_id}/pdf-info")
def get_teacher_session_pdf_info(
    session_id: int,
    current_teacher: Teacher = Depends(get_current_teacher),
    db: Session = Depends(get_db)
):
    session = (
        db.query(ClassSession)
        .join(Course, ClassSession.course_id == Course.course_id)
        .filter(
            ClassSession.session_id == session_id,
            Course.teacher_id == current_teacher.teacher_id
        )
        .first()
    )

    if not session:
        raise HTTPException(
            status_code=404,
            detail="Session not found or does not belong to this teacher"
        )

    has_pdf = bool(session.pdf_file_path and os.path.exists(session.pdf_file_path))

    return {
        "session_id": session.session_id,
        "has_pdf": has_pdf,
        "pdf_original_name": session.pdf_original_name if has_pdf else None
    }





@router.get("/sessions/{session_id}/pdf")
def download_teacher_session_pdf(
    session_id: int,
    current_teacher: Teacher = Depends(get_current_teacher),
    db: Session = Depends(get_db)
):
    session = (
        db.query(ClassSession)
        .join(Course, ClassSession.course_id == Course.course_id)
        .filter(
            ClassSession.session_id == session_id,
            Course.teacher_id == current_teacher.teacher_id
        )
        .first()
    )

    if not session:
        raise HTTPException(
            status_code=404,
            detail="Session not found or does not belong to this teacher"
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