"""
Seed script — populate the database with realistic demo data.

Usage:
    python -m scripts.seed            # seed (skip if data exists)
    python -m scripts.seed --reset    # drop all rows and re-seed
"""

from __future__ import annotations

import argparse
import random
import sys
from datetime import datetime, timedelta, timezone, date

from sqlalchemy.orm import Session

# Ensure the project root is on sys.path
sys.path.insert(0, ".")

from app.database import SessionLocal
from app.models import (
    Attendance,
    Base,
    Building,
    Classroom,
    ClassroomKind,
    Course,
    Department,
    Enrollment,
    EnergyRecord,
    Faculty,
    OccupancyRecord,
    Student,
    Timetable,
    University,
    User,
    UserRole,
    utcnow,
)
from app.security import hash_password
from app.services.campus_data import generate_energy_reading, generate_occupancy_reading

random.seed(42)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

UNIVERSITY = {"name": "UPES Dehradun", "code": "UPES", "address": "Bidholi, Dehradun, Uttarakhand"}

DEPARTMENTS = [
    {"name": "Computer Science", "code": "CS"},
    {"name": "Mechanical Engineering", "code": "ME"},
    {"name": "Electrical Engineering", "code": "EE"},
    {"name": "Applied Sciences", "code": "AS"},
]

BUILDINGS = [
    {"name": "Academic Block A", "code": "ACA", "building_type": "academic", "floors": 4},
    {"name": "Academic Block B", "code": "ACB", "building_type": "academic", "floors": 3},
    {"name": "Academic Block C", "code": "ACC", "building_type": "academic", "floors": 3},
    {"name": "Lab Complex", "code": "LAB", "building_type": "lab", "floors": 2},
    {"name": "Central Library", "code": "LIB", "building_type": "library", "floors": 3},
    {"name": "Hostel Block H1", "code": "H1", "building_type": "hostel", "floors": 5},
]

COURSES_PER_DEPT = [
    # (name_suffix, code_prefix, credits, semester)
    ("Data Structures", "DS", 4, 3),
    ("Algorithms", "ALGO", 4, 4),
    ("Database Systems", "DB", 3, 5),
    ("Machine Learning", "ML", 3, 6),
]

DESIGNATIONS = ["Professor", "Associate Professor", "Assistant Professor"]

DEFAULT_PASSWORD = "password123"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _batch_add(db: Session, objects: list, batch_size: int = 100) -> None:
    """Add objects in batches and flush."""
    for i in range(0, len(objects), batch_size):
        db.add_all(objects[i : i + batch_size])
        db.flush()


# ---------------------------------------------------------------------------
# Seeding
# ---------------------------------------------------------------------------

def seed(db: Session) -> None:
    existing_university = db.query(University).filter(University.code == UNIVERSITY["code"]).first()
    if existing_university is not None:
        print(f"UPES sample data already exists (university id={existing_university.id}); skipping.")
        return

    now = utcnow()
    hashed = hash_password(DEFAULT_PASSWORD)

    # ---- University ----
    uni = University(**UNIVERSITY)
    db.add(uni)
    db.flush()
    print(f"  University: {uni.name} (id={uni.id})")

    # ---- Admin user ----
    admin_user = User(
        email="admin@upes.ac.in",
        name="Campus Admin",
        hashed_password=hashed,
        role=UserRole.admin,
        is_active=True,
    )
    db.add(admin_user)
    db.flush()

    # ---- Facility Manager ----
    fm_user = User(
        email="facilities@upes.ac.in",
        name="Facility Manager",
        hashed_password=hashed,
        role=UserRole.facility_manager,
        is_active=True,
    )
    db.add(fm_user)
    db.flush()
    print(f"  Admin: {admin_user.email}, Facility Manager: {fm_user.email}")

    # ---- Departments ----
    dept_objs: list[Department] = []
    for d in DEPARTMENTS:
        dept = Department(name=d["name"], code=d["code"], university_id=uni.id)
        db.add(dept)
        db.flush()
        dept_objs.append(dept)
    print(f"  Departments: {len(dept_objs)}")

    # ---- Buildings ----
    bldg_objs: list[Building] = []
    for b in BUILDINGS:
        bldg = Building(
            name=b["name"],
            code=b["code"],
            university_id=uni.id,
            building_type=b["building_type"],
            floors=b["floors"],
        )
        db.add(bldg)
        db.flush()
        bldg_objs.append(bldg)
    print(f"  Buildings: {len(bldg_objs)}")

    # ---- Classrooms ----
    classroom_objs: list[Classroom] = []
    room_counter = 1
    for bldg in bldg_objs:
        if bldg.building_type == "academic":
            for floor in range(1, bldg.floors + 1):
                for i in range(1, 3):  # 2 classrooms per floor
                    c = Classroom(
                        name=f"{bldg.code}-{floor}0{i}",
                        code=f"R{room_counter:03d}",
                        building_id=bldg.id,
                        kind=ClassroomKind.classroom,
                        capacity=random.choice([40, 60, 80, 100]),
                        floor=floor,
                    )
                    db.add(c)
                    classroom_objs.append(c)
                    room_counter += 1
        elif bldg.building_type == "lab":
            for floor in range(1, bldg.floors + 1):
                for i in range(1, 3):
                    c = Classroom(
                        name=f"{bldg.code}-Lab-{floor}0{i}",
                        code=f"R{room_counter:03d}",
                        building_id=bldg.id,
                        kind=ClassroomKind.lab,
                        capacity=random.choice([30, 40]),
                        floor=floor,
                    )
                    db.add(c)
                    classroom_objs.append(c)
                    room_counter += 1
        elif bldg.building_type == "library":
            c = Classroom(
                name="Main Reading Hall",
                code=f"R{room_counter:03d}",
                building_id=bldg.id,
                kind=ClassroomKind.library,
                capacity=200,
                floor=1,
            )
            db.add(c)
            classroom_objs.append(c)
            room_counter += 1
        elif bldg.building_type == "hostel":
            c = Classroom(
                name="Hostel H1 Common Area",
                code=f"R{room_counter:03d}",
                building_id=bldg.id,
                kind=ClassroomKind.hostel,
                capacity=300,
                floor=0,
            )
            db.add(c)
            classroom_objs.append(c)
            room_counter += 1

    db.flush()
    print(f"  Classrooms/Spaces: {len(classroom_objs)}")

    # ---- Faculty ----
    faculty_objs: list[Faculty] = []
    faculty_names = [
        "Dr. Arun Kumar", "Dr. Priya Sharma", "Dr. Rajesh Verma",
        "Dr. Neha Gupta", "Dr. Vikram Singh", "Dr. Anita Patel",
        "Dr. Sanjay Mehta", "Dr. Kavita Joshi", "Dr. Ramesh Yadav",
        "Dr. Sunita Mishra", "Dr. Deepak Tiwari", "Dr. Pooja Rawat",
    ]
    for idx, name in enumerate(faculty_names):
        dept = dept_objs[idx % len(dept_objs)]
        user = User(
            email=f"faculty{idx + 1}@upes.ac.in",
            name=name,
            hashed_password=hashed,
            role=UserRole.faculty,
            is_active=True,
        )
        db.add(user)
        db.flush()
        fac = Faculty(
            user_id=user.id,
            department_id=dept.id,
            employee_id=f"EMP{idx + 1:03d}",
            designation=DESIGNATIONS[idx % len(DESIGNATIONS)],
        )
        db.add(fac)
        db.flush()
        faculty_objs.append(fac)
    print(f"  Faculty: {len(faculty_objs)}")

    # ---- Courses ----
    course_objs: list[Course] = []
    for dept in dept_objs:
        for name_suffix, code_prefix, credits, semester in COURSES_PER_DEPT:
            c = Course(
                name=f"{name_suffix} ({dept.code})",
                code=f"{dept.code}-{code_prefix}",
                department_id=dept.id,
                credits=credits,
                semester=semester,
            )
            db.add(c)
            course_objs.append(c)
    db.flush()
    print(f"  Courses: {len(course_objs)}")

    # ---- Students ----
    student_objs: list[Student] = []
    for i in range(200):
        dept = dept_objs[i % len(dept_objs)]
        user = User(
            email=f"student{i + 1}@upes.ac.in",
            name=f"Student {i + 1}",
            hashed_password=hashed,
            role=UserRole.student,
            is_active=True,
        )
        db.add(user)
        db.flush()
        stu = Student(
            user_id=user.id,
            department_id=dept.id,
            roll_number=f"R{i + 1:04d}",
            semester=random.choice([3, 4, 5, 6]),
        )
        db.add(stu)
        student_objs.append(stu)
    db.flush()
    print(f"  Students: {len(student_objs)}")

    # ---- Enrollments ----
    enrollment_objs: list[Enrollment] = []
    for stu in student_objs:
        dept_courses = [c for c in course_objs if c.department_id == stu.department_id]
        eligible = [c for c in dept_courses if c.semester <= stu.semester]
        if not eligible:
            eligible = dept_courses[:2]
        for course in eligible:
            e = Enrollment(student_id=stu.id, course_id=course.id)
            enrollment_objs.append(e)
    _batch_add(db, enrollment_objs)
    db.flush()
    print(f"  Enrollments: {len(enrollment_objs)}")

    # ---- Timetable (conflict-free) ----
    academic_rooms = [c for c in classroom_objs if c.kind in (ClassroomKind.classroom, ClassroomKind.lab)]
    room_occupied: dict[tuple[int, int, int], bool] = {}  # (room_id, day, hour) -> True
    faculty_busy: dict[tuple[int, int, int], bool] = {}  # (fac_id, day, hour) -> True

    timetable_objs: list[Timetable] = []
    for course in course_objs:
        dept_faculty = [f for f in faculty_objs if f.department_id == course.department_id]
        if not dept_faculty:
            continue
        fac = random.choice(dept_faculty)

        slots_created = 0
        for day in range(5):  # Mon–Fri
            if slots_created >= 2:
                break
            for start_h in range(8, 17):
                if slots_created >= 2:
                    break
                end_h = start_h + 1
                # Check faculty availability
                if (fac.id, day, start_h) in faculty_busy:
                    continue
                # Find available room
                found_room = None
                random.shuffle(academic_rooms)
                for room in academic_rooms:
                    if (room.id, day, start_h) not in room_occupied:
                        found_room = room
                        break
                if found_room is None:
                    continue

                t = Timetable(
                    course_id=course.id,
                    classroom_id=found_room.id,
                    faculty_id=fac.id,
                    day_of_week=day,
                    start_hour=start_h,
                    end_hour=end_h,
                )
                timetable_objs.append(t)
                room_occupied[(found_room.id, day, start_h)] = True
                faculty_busy[(fac.id, day, start_h)] = True
                slots_created += 1

    _batch_add(db, timetable_objs)
    db.flush()
    print(f"  Timetable slots: {len(timetable_objs)}")

    # ---- Energy records (4 days of hourly data) ----
    energy_objs: list[EnergyRecord] = []
    base_ts = now - timedelta(days=4)
    for bldg in bldg_objs:
        for hour_offset in range(96):  # 4 days × 24 hours
            ts = base_ts + timedelta(hours=hour_offset)
            kwh = generate_energy_reading(bldg.building_type, ts)
            energy_objs.append(EnergyRecord(building_id=bldg.id, ts=ts, kwh=kwh))
    _batch_add(db, energy_objs)
    db.flush()
    print(f"  Energy records: {len(energy_objs)}")

    # ---- Occupancy records (4 days of hourly data) ----
    # Build timetable lookup for occupancy simulation
    slot_lookup: dict[tuple[int, int, int], Timetable] = {}
    course_enrollment_count: dict[int, int] = {}
    for t in timetable_objs:
        slot_lookup[(t.classroom_id, t.day_of_week, t.start_hour)] = t
    for e in enrollment_objs:
        course_enrollment_count[e.course_id] = course_enrollment_count.get(e.course_id, 0) + 1

    occ_objs: list[OccupancyRecord] = []
    for room in classroom_objs:
        kind_val = room.kind.value if hasattr(room.kind, "value") else room.kind
        for hour_offset in range(96):
            ts = base_ts + timedelta(hours=hour_offset)
            day = ts.weekday()
            hour = ts.hour
            slot = slot_lookup.get((room.id, day, hour))
            has_class = slot is not None
            enrollment = course_enrollment_count.get(slot.course_id, 0) if slot else 0
            count = generate_occupancy_reading(
                room.capacity, kind_val, ts,
                has_class=has_class, enrollment=enrollment,
            )
            occ_objs.append(OccupancyRecord(classroom_id=room.id, ts=ts, count=count))
    _batch_add(db, occ_objs)
    db.flush()
    print(f"  Occupancy records: {len(occ_objs)}")

    # ---- Attendance (last 30 days, weekdays only) ----
    attendance_objs: list[Attendance] = []
    today = date.today()
    for stu in student_objs:
        enrolled_courses = [e.course_id for e in enrollment_objs if e.student_id == stu.id]
        for course_id in enrolled_courses:
            for d in range(30):
                att_date = today - timedelta(days=d)
                if att_date.weekday() >= 5:
                    continue
                present = random.random() < 0.80  # 80% attendance rate
                attendance_objs.append(Attendance(
                    student_id=stu.id,
                    course_id=course_id,
                    date=att_date,
                    present=present,
                ))
    _batch_add(db, attendance_objs, batch_size=500)
    db.flush()
    print(f"  Attendance records: {len(attendance_objs)}")

    db.commit()
    print("\n[OK] Seed complete!")


def reset_db(db: Session) -> None:
    """Delete all data from all tables (reverse FK order)."""
    from app.models import SimulationResult, SimulationScenario, Anomaly, Prediction
    tables = [
        SimulationResult, SimulationScenario, Anomaly, Prediction,
        OccupancyRecord, EnergyRecord, Attendance, Timetable,
        Enrollment, Course, Student, Faculty,
        Classroom, Building, Department, User, University,
    ]
    for model in tables:
        db.query(model).delete()
    db.commit()
    print("[OK] All data deleted.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the Digital Twin database")
    parser.add_argument("--reset", action="store_true", help="Delete all data first")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        if args.reset:
            reset_db(db)
        existing = db.query(University).filter(University.code == UNIVERSITY["code"]).count()
        if existing > 0:
            print("Data already exists. Use --reset to re-seed.")
            return
        print("Seeding database...")
        seed(db)
    finally:
        db.close()


if __name__ == "__main__":
    main()
