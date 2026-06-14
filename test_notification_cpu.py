import time

from app.database import SessionLocal
from app.models import Student

# IMPORTANT:
# Import the function that generates/checks notifications.
# If your notification logic is still inside student_router.py,
# we will temporarily import the endpoint helper from there.
from app.routers.student_router import get_student_notifications


def measure_notification_check():
    db = SessionLocal()

    try:
        students = db.query(Student).filter(Student.is_active == True).all()

        print(f"Active students found: {len(students)}")

        start_cpu = time.process_time()
        start_real = time.time()

        for student in students:
            get_student_notifications(
                current_student=student,
                db=db
            )

        end_cpu = time.process_time()
        end_real = time.time()

        cpu_used = end_cpu - start_cpu
        real_used = end_real - start_real

        estimated_daily_cpu = cpu_used * 1440

        print("----- Notification CPU Test -----")
        print(f"CPU seconds used for one run: {cpu_used:.6f}")
        print(f"Real seconds used for one run: {real_used:.6f}")
        print(f"Estimated daily CPU if running every minute: {estimated_daily_cpu:.2f}")
        print("---------------------------------")

    finally:
        db.close()


if __name__ == "__main__":
    measure_notification_check()
