import os
import shutil
from datetime import datetime
from typing import Optional
from app.core.time_utils import now_syria

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from sqlalchemy.orm import Session

from app.core.config import CLASSROOM_TEST_DIR, CLASSROOM_SESSION_DIR
from app.database import get_db
from app.dependencies.auth_dependencies import get_current_teacher
from app.models import (
    Teacher,
    Classroom,
    Course,
    ClassSession,
    StudentCourse,
    Attendance,
)
from app.schemas.classroom_schema import CreateClassroomRequest
from app.services.face_service_instance import insightface_service


router = APIRouter(prefix="/teacher", tags=["Teacher Classrooms"])




@router.get("/classrooms/available")
def get_available_classrooms(
    session_date: str,
    start_time: str,
    end_time: str,
    current_teacher: Teacher = Depends(get_current_teacher),
    db: Session = Depends(get_db)
):
    # 1) Parse date and time
    try:
        parsed_session_date = datetime.strptime(session_date, "%Y-%m-%d").date()
        parsed_start_time = datetime.strptime(start_time, "%H:%M:%S").time()
        parsed_end_time = datetime.strptime(end_time, "%H:%M:%S").time()
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid date/time format. Use YYYY-MM-DD and HH:MM:SS"
        )

    # 2) Validate time order
    if parsed_start_time >= parsed_end_time:
        raise HTTPException(
            status_code=400,
            detail="Start time must be earlier than end time"
        )

    # 3) Find classrooms that already have a conflicting session
    busy_classroom_ids = (
        db.query(ClassSession.classroom_id)
        .filter(
            ClassSession.session_date == parsed_session_date,
            ClassSession.start_time < parsed_end_time,
            ClassSession.end_time > parsed_start_time
        )
        .distinct()
        .all()
    )

    busy_classroom_ids = [
        classroom_id for (classroom_id,) in busy_classroom_ids
    ]

    # 4) Return classrooms that are not busy
    query = db.query(Classroom)

    if busy_classroom_ids:
        query = query.filter(Classroom.classroom_id.notin_(busy_classroom_ids))

    available_classrooms = (
        query
        .order_by(Classroom.name.asc(), Classroom.building.asc(), Classroom.room_number.asc())
        .all()
    )

    return {
        "filters": {
            "session_date": session_date,
            "start_time": start_time,
            "end_time": end_time
        },
        "available_classrooms": [
            {
                "classroom_id": classroom.classroom_id,
                "name": classroom.name,
                "building": classroom.building,
                "room_number": classroom.room_number,
                "latitude": classroom.latitude,
                "longitude": classroom.longitude,
                "allowed_radius_meters": classroom.allowed_radius_meters
            }
            for classroom in available_classrooms
        ],
        "total_available": len(available_classrooms)
    }




@router.get("/classrooms")
def get_teacher_classrooms(
    current_teacher: Teacher = Depends(get_current_teacher),
    db: Session = Depends(get_db)
):
    classrooms = (
        db.query(Classroom)
        .order_by(Classroom.name.asc(), Classroom.building.asc(), Classroom.room_number.asc())
        .all()
    )

    return [
        {
            "classroom_id": classroom.classroom_id,
            "name": classroom.name,
            "building": classroom.building,
            "room_number": classroom.room_number,
            "latitude": classroom.latitude,
            "longitude": classroom.longitude,
            "allowed_radius_meters": classroom.allowed_radius_meters
        }
        for classroom in classrooms
    ]


@router.post("/classrooms")
def create_teacher_classroom(
    request: CreateClassroomRequest,
    current_teacher: Teacher = Depends(get_current_teacher),
    db: Session = Depends(get_db)
):
    existing_classroom = (
        db.query(Classroom)
        .filter(Classroom.name == request.name)
        .first()
    )

    if existing_classroom:
        raise HTTPException(
            status_code=400,
            detail="Classroom name already exists"
        )

    new_classroom = Classroom(
        name=request.name,
        building=request.building,
        room_number=request.room_number,
        latitude=request.latitude,
        longitude=request.longitude,
        allowed_radius_meters=request.allowed_radius_meters
    )

    db.add(new_classroom)
    db.commit()
    db.refresh(new_classroom)

    return {
        "message": "Classroom created successfully",
        "classroom": {
            "classroom_id": new_classroom.classroom_id,
            "name": new_classroom.name,
            "building": new_classroom.building,
            "room_number": new_classroom.room_number,
            "latitude": new_classroom.latitude,
            "longitude": new_classroom.longitude,
            "allowed_radius_meters": new_classroom.allowed_radius_meters
        }
    }


@router.post("/count-classroom-faces")
def count_classroom_faces(

    image: UploadFile = File(...),
    current_teacher: Teacher = Depends(get_current_teacher),
    db: Session = Depends(get_db)
):
    # 1) Validate image type
    if not image.content_type or not image.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Uploaded file must be an image")

    # 2) Save uploaded classroom image
    safe_filename = f"teacher_{current_teacher.teacher_id}_classroom_{int(datetime.now().timestamp())}.jpg"
    file_path = os.path.join(CLASSROOM_TEST_DIR, safe_filename)

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(image.file, buffer)

    # 3) Count faces
    try:
        face_count = insightface_service.count_faces_in_image(file_path)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # 4) Return only the count
    return {
        "message": "Face count completed successfully",
        "teacher_id": current_teacher.teacher_id,
        "face_count": face_count,
        "image_path": file_path
    }

@router.post("/sessions/{session_id}/compare-classroom-count")
def compare_classroom_face_count_with_attendance(
    session_id: int,
    image: UploadFile = File(...),
    current_teacher: Teacher = Depends(get_current_teacher),
    db: Session = Depends(get_db)
):
    # 1) Validate image type
    if not image.content_type or not image.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Uploaded file must be an image")

    # 2) Load the session and verify it belongs to the logged-in teacher
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

    # 3) Save uploaded classroom image
    safe_filename = f"session_{session_id}_teacher_{current_teacher.teacher_id}_{int(datetime.now().timestamp())}.jpg"
    file_path = os.path.join(CLASSROOM_SESSION_DIR, safe_filename)

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(image.file, buffer)

    # 4) Count detected faces in the uploaded classroom image
    try:
        detected_face_count = insightface_service.count_faces_in_image(file_path)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # 5) Count present attendance rows for this session
    present_count = (
        db.query(Attendance)
        .filter(
            Attendance.session_id == session_id,
            Attendance.status == "present"
        )
        .count()
    )

    # 6) Check whether attendance is finalized
    now = now_syria()
    attendance_close_dt = datetime.combine(
        session.session_date,
        session.attendance_close_time
    )
    attendance_finalized = attendance_close_dt <= now

    # 7) Calculate comparison difference
    difference = detected_face_count - present_count

    return {
        "message": "Classroom face count comparison completed successfully",
        "session": {
            "session_id": session.session_id,
            "session_date": str(session.session_date),
            "start_time": str(session.start_time),
            "end_time": str(session.end_time),
            "attendance_open_time": str(session.attendance_open_time),
            "attendance_close_time": str(session.attendance_close_time)
        },
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
        "attendance_finalized": attendance_finalized,
        "detected_face_count": detected_face_count,
        "present_count": present_count,
        "difference": difference,
        "image_path": file_path
    }

