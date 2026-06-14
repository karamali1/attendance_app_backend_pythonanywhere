from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    Date,
    Time,
    ForeignKey,
    SmallInteger,
    Float,
    DateTime,
    LargeBinary,
    UniqueConstraint
)
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class Student(Base):
    __tablename__ = "students"

    student_id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)

    email_verified = Column(Boolean, default=False)
    verification_token = Column(String(255), nullable=True)

    national_number = Column(String(20), unique=True, nullable=False)
    university_number = Column(String(20), unique=True, nullable=False)
    full_name = Column(String(150), nullable=False)
    year_of_study = Column(SmallInteger, nullable=False)

    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())

    enrollments = relationship("StudentCourse", back_populates="student", cascade="all, delete-orphan")
    attendances = relationship("Attendance", back_populates="student", cascade="all, delete-orphan")
    embeddings = relationship("StudentFaceEmbedding", back_populates="student", cascade="all, delete-orphan")
    notifications = relationship("StudentNotification", back_populates="student", cascade="all, delete-orphan")
    device_tokens = relationship("StudentDeviceToken", back_populates="student", cascade="all, delete-orphan")


class Teacher(Base):
    __tablename__ = "teachers"

    teacher_id = Column(Integer, primary_key=True, index=True)
    national_number = Column(String(20), unique=True, nullable=False)
    full_name = Column(String(150), nullable=False)
    email = Column(String(255), unique=True, nullable=True)
    password_hash = Column(String(255), nullable=False)

    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())

    courses = relationship("Course", back_populates="teacher", cascade="all, delete-orphan")


class Classroom(Base):
    __tablename__ = "classrooms"

    classroom_id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, unique=True)
    building = Column(String(100), nullable=True)
    room_number = Column(String(50), nullable=True)

    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    allowed_radius_meters = Column(Float, nullable=False, default=30.0)

    created_at = Column(DateTime, server_default=func.now())

    sessions = relationship("ClassSession", back_populates="classroom", cascade="all, delete-orphan")


class Course(Base):
    __tablename__ = "courses"

    course_id = Column(Integer, primary_key=True, index=True)
    course_name = Column(String(150), nullable=False)
    year_of_study = Column(SmallInteger, nullable=False)

    teacher_id = Column(Integer, ForeignKey("teachers.teacher_id"), nullable=False)

    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())

    teacher = relationship("Teacher", back_populates="courses")
    students = relationship("StudentCourse", back_populates="course", cascade="all, delete-orphan")
    sessions = relationship("ClassSession", back_populates="course", cascade="all, delete-orphan")


class ClassSession(Base):
    __tablename__ = "class_sessions"

    session_id = Column(Integer, primary_key=True, index=True)
    course_id = Column(Integer, ForeignKey("courses.course_id"), nullable=False)
    classroom_id = Column(Integer, ForeignKey("classrooms.classroom_id"), nullable=False)

    session_date = Column(Date, nullable=False)
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)

    attendance_open_time = Column(Time, nullable=False)
    attendance_close_time = Column(Time, nullable=False)

    created_at = Column(DateTime, server_default=func.now())

    pdf_file_path = Column(String(255), nullable=True)
    pdf_original_name = Column(String(255), nullable=True)

    course = relationship("Course", back_populates="sessions")
    classroom = relationship("Classroom", back_populates="sessions")
    attendances = relationship("Attendance", back_populates="session", cascade="all, delete-orphan")


class StudentCourse(Base):
    __tablename__ = "student_courses"
    __table_args__ = (
        UniqueConstraint("student_id", "course_id", name="uq_student_course"),
    )

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("students.student_id"), nullable=False)
    course_id = Column(Integer, ForeignKey("courses.course_id"), nullable=False)

    enrolled_at = Column(DateTime, server_default=func.now())

    student = relationship("Student", back_populates="enrollments")
    course = relationship("Course", back_populates="students")


class Attendance(Base):
    __tablename__ = "attendance"
    __table_args__ = (
        UniqueConstraint("student_id", "session_id", name="uq_student_session_attendance"),
    )

    attendance_id = Column(Integer, primary_key=True, index=True)

    student_id = Column(Integer, ForeignKey("students.student_id"), nullable=False)
    session_id = Column(Integer, ForeignKey("class_sessions.session_id"), nullable=False)

    status = Column(String(20), nullable=False)  # present / absent / rejected
    confidence_score = Column(Float, nullable=True)

    student_latitude = Column(Float, nullable=True)
    student_longitude = Column(Float, nullable=True)
    distance_from_class_meters = Column(Float, nullable=True)
    image_path = Column(String(255), nullable=True)

    captured_at = Column(DateTime, server_default=func.now())

    student = relationship("Student", back_populates="attendances")
    session = relationship("ClassSession", back_populates="attendances")


class StudentFaceEmbedding(Base):
    __tablename__ = "student_face_embeddings"

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("students.student_id"), nullable=False)

    embedding = Column(LargeBinary, nullable=False)
    model_name = Column(String(100), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())

    student = relationship("Student", back_populates="embeddings")



class StudentNotification(Base):
    __tablename__ = "student_notifications"

    notification_id = Column(Integer, primary_key=True, index=True)

    student_id = Column(Integer, ForeignKey("students.student_id"), nullable=False)

    title = Column(String(150), nullable=False)
    message = Column(String(500), nullable=False)

    notification_type = Column(String(50), nullable=False)
    notification_key = Column(String(255), unique=True, nullable=False)

    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime, server_default=func.now())

    student = relationship("Student", back_populates="notifications")





class StudentDeviceToken(Base):
    __tablename__ = "student_device_tokens"

    id = Column(Integer, primary_key=True, index=True)

    student_id = Column(Integer, ForeignKey("students.student_id"), nullable=False)
    fcm_token = Column(String(500), unique=True, nullable=False)
    platform = Column(String(50), nullable=True)

    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())
    last_seen_at = Column(DateTime, server_default=func.now())

    student = relationship("Student", back_populates="device_tokens")