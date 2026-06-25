import os
import shutil
from datetime import datetime
from app.core.time_utils import now_syria

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session

from app.services.antispoofing_instance import anti_spoofing_service

from app.core.config import UPLOAD_DIR
from app.database import get_db
from app.dependencies.auth_dependencies import get_current_student
from app.models import (
    Student,
    Classroom,
    ClassSession,
    StudentCourse,
    Attendance,
    Course,
    StudentFaceEmbedding,
)
from app.services.face_service_instance import insightface_service
from app.utils.geo_utils import calculate_distance_meters


router = APIRouter(tags=["Attendance"])

@router.get("/attendance")
def get_attendance(db: Session = Depends(get_db)):
    records = (
        db.query(Attendance, Student, ClassSession, Course, Classroom)
        .join(Student, Attendance.student_id == Student.student_id)
        .join(ClassSession, Attendance.session_id == ClassSession.session_id)
        .join(Course, ClassSession.course_id == Course.course_id)
        .join(Classroom, ClassSession.classroom_id == Classroom.classroom_id)
        .all()
    )

    result = []

    for attendance, student, session, course, classroom in records:
        result.append({
            "attendance_id": attendance.attendance_id,

            "student": {
                "student_id": student.student_id,
                "full_name": student.full_name,
                "email": student.email,
                "university_number": student.university_number
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
                "end_time": str(session.end_time)
            },

            "classroom": {
                "classroom_id": classroom.classroom_id,
                "name": classroom.name,
                "building": classroom.building,
                "room_number": classroom.room_number
            },

            "attendance_details": {
                "status": attendance.status,
                "confidence_score": attendance.confidence_score,
                "distance_from_class_meters": attendance.distance_from_class_meters,
                "captured_at": str(attendance.captured_at),
                "image_path": attendance.image_path
            }
        })

    return result


@router.post("/attendance/submit")
def submit_attendance(
    session_id: int = Form(...),
    latitude: float = Form(...),
    longitude: float = Form(...),
    image: UploadFile = File(...),
    current_student: Student = Depends(get_current_student),
    db: Session = Depends(get_db)
):
    student_id = current_student.student_id

    # 1) Check session exists
    session = db.query(ClassSession).filter(ClassSession.session_id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # 2) Check student is enrolled in the course
    enrollment = (
        db.query(StudentCourse)
        .filter(
            StudentCourse.student_id == student_id,
            StudentCourse.course_id == session.course_id
        )
        .first()
    )
    if not enrollment:
        raise HTTPException(
            status_code=403,
            detail="Student is not enrolled in this course"
        )

    # 3) Check practical-section authorization
    session_type = session.session_type or "theory"

    if session_type == "practical":
        if enrollment.section_id is None:
            raise HTTPException(
                status_code=403,
                detail=(
                    "You must select a practical section before submitting "
                    "attendance for a practical session"
                )
            )

    if enrollment.section_id != session.section_id:
        raise HTTPException(
            status_code=403,
            detail=(
                "You are not assigned to the practical section "
                "for this session"
            )
        )

    # 4) Check duplicate attendance

    existing_attendance = (
        db.query(Attendance)
        .filter(
            Attendance.student_id == student_id,
            Attendance.session_id == session_id
        )
        .first()
    )
    if existing_attendance:
        raise HTTPException(status_code=400, detail="Attendance already submitted for this session")

    # 4) Check time window
    now = now_syria()
    current_date = now.date()
    current_time = now.time()

    if current_date != session.session_date:
        raise HTTPException(status_code=400, detail="Attendance is not allowed on this date")

    if not (session.attendance_open_time <= current_time <= session.attendance_close_time):
        raise HTTPException(status_code=400, detail="Attendance window is closed")

    # 5) Check classroom and distance
    classroom = db.query(Classroom).filter(Classroom.classroom_id == session.classroom_id).first()
    if not classroom:
        raise HTTPException(status_code=404, detail="Classroom not found")

    distance = calculate_distance_meters(
        latitude,
        longitude,
        classroom.latitude,
        classroom.longitude
    )

    if distance > classroom.allowed_radius_meters:
        raise HTTPException(
            status_code=400,
            detail=f"Student is outside classroom radius. Distance: {distance:.2f} meters"
        )

    # 6) Check image type
    if not image.content_type or not image.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Uploaded file must be an image")

    # 7) Get active enrolled embedding
    enrolled_face = (
        db.query(StudentFaceEmbedding)
        .filter(
            StudentFaceEmbedding.student_id == student_id,
            StudentFaceEmbedding.is_active == True
        )
        .order_by(StudentFaceEmbedding.created_at.desc())
        .first()
    )

    if not enrolled_face:
        raise HTTPException(status_code=400, detail="No enrolled face found for this student")

    # 8) Save uploaded attendance selfie
    safe_filename = f"student_{student_id}_session_{session_id}_{int(datetime.now().timestamp())}.jpg"
    file_path = os.path.join(UPLOAD_DIR, safe_filename)

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(image.file, buffer)


    # 10) antispoofing starts here
    anti_spoofing_result = anti_spoofing_service.predict_image(file_path)

    if not anti_spoofing_result["success"]:
        raise HTTPException(
            status_code=400,
            detail=anti_spoofing_result["message"]
        )

    if not anti_spoofing_result["is_real"]:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Fake face detected. Attendance rejected.",
                "anti_spoofing_label": anti_spoofing_result["label"],
                "anti_spoofing_score": anti_spoofing_result["score"]
            }
     )

    # 11) antispoofing ends here

    # 9) Compare face with stored embedding
    try:
        similarity = insightface_service.compare_image_with_stored_embedding(
            file_path,
            enrolled_face.embedding
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    FACE_MATCH_THRESHOLD = 0.50

    if similarity < FACE_MATCH_THRESHOLD:
        raise HTTPException(
            status_code=400,
            detail=f"Face does not match the enrolled student. Similarity: {similarity:.4f}"
        )

    # 10) Save attendance
    attendance = Attendance(
        student_id=student_id,
        session_id=session_id,
        status="present",
        confidence_score=similarity,
        student_latitude=latitude,
        student_longitude=longitude,
        distance_from_class_meters=distance,
        image_path=file_path
    )

    db.add(attendance)
    db.commit()
    db.refresh(attendance)

    return {
        "message": "Attendance submitted successfully",
        "attendance_id": attendance.attendance_id,
        "student_id": attendance.student_id,
        "student_name": current_student.full_name,
        "session_id": attendance.session_id,
        "distance_from_class_meters": round(distance, 2),
        "similarity_score": round(similarity, 4),
        "image_path": attendance.image_path,
        "status": attendance.status,
        "anti_spoofing": {
            "label": anti_spoofing_result["label"],
            "score": anti_spoofing_result["score"],
            "is_real": anti_spoofing_result["is_real"]
        }
    }



