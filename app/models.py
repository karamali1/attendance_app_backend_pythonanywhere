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
    manual_attendances = relationship(
        "Attendance",
        foreign_keys="Attendance.marked_by_teacher_id"
    )


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
    practical_sections = relationship("CourseSection", back_populates="classroom")





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
    sections = relationship("CourseSection", back_populates="course", cascade="all, delete-orphan")



class CourseSection(Base):
    __tablename__ = "course_sections"
    __table_args__ = (
        UniqueConstraint(
            "course_id",
            "section_name",
            name="uq_course_section_name"
        ),
    )

    section_id = Column(Integer, primary_key=True, index=True)

    course_id = Column(
        Integer,
        ForeignKey("courses.course_id", ondelete="CASCADE"),
        nullable=False
    )

    section_name = Column(String(100), nullable=False)

    capacity = Column(Integer, nullable=False)

    classroom_id = Column(
        Integer,
        ForeignKey("classrooms.classroom_id", ondelete="RESTRICT"),
        nullable=False
    )

    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())

    course = relationship("Course", back_populates="sections")
    classroom = relationship("Classroom", back_populates="practical_sections")

    enrollments = relationship(
        "StudentCourse",
        back_populates="section"
    )

    sessions = relationship(
        "ClassSession",
        back_populates="section"
    )
    schedules = relationship(
        "SectionSchedule",
        back_populates="section",
        cascade="all, delete-orphan"
    )


class SectionSchedule(Base):
    __tablename__ = "section_schedules"
    __table_args__ = (
        UniqueConstraint(
            "section_id",
            "weekday",
            "start_time",
            "start_date",
            name="uq_section_schedule_start"
        ),
    )

    schedule_id = Column(Integer, primary_key=True, index=True)

    section_id = Column(
        Integer,
        ForeignKey("course_sections.section_id", ondelete="CASCADE"),
        nullable=False
    )

    # Monday = 0, Tuesday = 1, ..., Sunday = 6
    weekday = Column(SmallInteger, nullable=False)

    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)

    # 1 = every week, 2 = every two weeks
    repeat_interval_weeks = Column(
        SmallInteger,
        nullable=False,
        default=1
    )

    start_date = Column(Date, nullable=False)

    # Teacher chooses one of these later:
    end_date = Column(Date, nullable=True)
    repeat_for_weeks = Column(Integer, nullable=True)

    # These values will be copied into every generated practical session.
    attendance_open_time = Column(Time, nullable=False)
    attendance_close_time = Column(Time, nullable=False)

    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())

    section = relationship("CourseSection", back_populates="schedules")

    sessions = relationship(
        "ClassSession",
        back_populates="schedule"
    )


class ClassSession(Base):
    __tablename__ = "class_sessions"

    session_id = Column(Integer, primary_key=True, index=True)
    course_id = Column(Integer, ForeignKey("courses.course_id"), nullable=False)
    classroom_id = Column(Integer, ForeignKey("classrooms.classroom_id"), nullable=False)
    session_type = Column(
        String(20),
        nullable=False,
        default="theory"
    )

    section_id = Column(
        Integer,
        ForeignKey("course_sections.section_id", ondelete="RESTRICT"),
        nullable=True
    )

    schedule_id = Column(
        Integer,
        ForeignKey("section_schedules.schedule_id", ondelete="SET NULL"),
        nullable=True
    )

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
    section = relationship("CourseSection", back_populates="sessions")
    schedule = relationship("SectionSchedule", back_populates="sessions")


class StudentCourse(Base):
    __tablename__ = "student_courses"
    __table_args__ = (
        UniqueConstraint("student_id", "course_id", name="uq_student_course"),
    )

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("students.student_id"), nullable=False)
    course_id = Column(Integer, ForeignKey("courses.course_id"), nullable=False)
    section_id = Column(
        Integer,
        ForeignKey("course_sections.section_id", ondelete="SET NULL"),
        nullable=True
    )

    enrolled_at = Column(DateTime, server_default=func.now())

    student = relationship("Student", back_populates="enrollments")
    course = relationship("Course", back_populates="students")
    section = relationship("CourseSection", back_populates="enrollments")


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
    attendance_method = Column(
        String(20),
        nullable=False,
        default="face"
    )

    marked_by_teacher_id = Column(
        Integer,
        ForeignKey("teachers.teacher_id"),
        nullable=True
    )

    manual_note = Column(String(500), nullable=True)

    manually_marked_at = Column(DateTime, nullable=True)

    student = relationship("Student", back_populates="attendances")
    session = relationship("ClassSession", back_populates="attendances")
    marked_by_teacher = relationship(
        "Teacher",
        foreign_keys=[marked_by_teacher_id]
    )


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