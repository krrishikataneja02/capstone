"""
CRUD router — departments, buildings, classrooms, courses, timetable,
faculty, students, personal views (/me/timetable, /me/attendance).

All signed-in users can read; admin writes. Student list: admin and faculty only.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.deps import get_current_user, get_db, require_role
from app.models import (
    Attendance,
    Building,
    Classroom,
    Course,
    Department,
    Enrollment,
    Faculty,
    Student,
    Timetable,
    User,
    UserRole,
)
from app.redis_client import invalidate_twin_state
from app.schemas import (
    AttendanceSummary,
    BuildingCreate,
    BuildingRead,
    ClassroomCreate,
    ClassroomRead,
    CourseCreate,
    CourseRead,
    DepartmentCreate,
    DepartmentRead,
    FacultyRead,
    PaginatedResponse,
    StudentRead,
    TimetableCreate,
    TimetableRead,
)

router = APIRouter(tags=["crud"])


# ===================================================================
# Helpers
# ===================================================================

def _paginate(query, page: int, page_size: int, schema):
    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()
    return PaginatedResponse(
        items=[schema.model_validate(i) for i in items],
        total=total,
        page=page,
        page_size=page_size,
    )


# ===================================================================
# Departments
# ===================================================================

@router.get("/departments", response_model=PaginatedResponse)
def list_departments(
    page: int = 1,
    page_size: int = 20,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return _paginate(db.query(Department).order_by(Department.id), page, page_size, DepartmentRead)


@router.get("/departments/{dept_id}", response_model=DepartmentRead)
def get_department(
    dept_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    dept = db.get(Department, dept_id)
    if not dept:
        raise HTTPException(status_code=404, detail="Department not found")
    return dept


@router.post("/departments", response_model=DepartmentRead, status_code=201)
def create_department(
    body: DepartmentCreate,
    user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    dept = Department(name=body.name, code=body.code, university_id=body.university_id)
    db.add(dept)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Constraint violated (duplicate code or invalid FK)")
    db.refresh(dept)
    return dept


# ===================================================================
# Buildings
# ===================================================================

@router.get("/buildings", response_model=PaginatedResponse)
def list_buildings(
    page: int = 1,
    page_size: int = 20,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return _paginate(db.query(Building).order_by(Building.id), page, page_size, BuildingRead)


@router.get("/buildings/{building_id}", response_model=BuildingRead)
def get_building(
    building_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    b = db.get(Building, building_id)
    if not b:
        raise HTTPException(status_code=404, detail="Building not found")
    return b


@router.post("/buildings", response_model=BuildingRead, status_code=201)
def create_building(
    body: BuildingCreate,
    user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    b = Building(
        name=body.name,
        code=body.code,
        university_id=body.university_id,
        building_type=body.building_type,
        floors=body.floors,
    )
    db.add(b)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Constraint violated (duplicate code or invalid FK)")
    db.refresh(b)
    invalidate_twin_state()
    return b


# ===================================================================
# Classrooms
# ===================================================================

@router.get("/classrooms", response_model=PaginatedResponse)
def list_classrooms(
    building_id: int | None = None,
    kind: str | None = None,
    page: int = 1,
    page_size: int = 20,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(Classroom)
    if building_id is not None:
        q = q.filter(Classroom.building_id == building_id)
    if kind is not None:
        q = q.filter(Classroom.kind == kind)
    return _paginate(q.order_by(Classroom.id), page, page_size, ClassroomRead)


@router.get("/classrooms/{classroom_id}", response_model=ClassroomRead)
def get_classroom(
    classroom_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    c = db.get(Classroom, classroom_id)
    if not c:
        raise HTTPException(status_code=404, detail="Classroom not found")
    return c


@router.post("/classrooms", response_model=ClassroomRead, status_code=201)
def create_classroom(
    body: ClassroomCreate,
    user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    c = Classroom(
        name=body.name,
        code=body.code,
        building_id=body.building_id,
        kind=body.kind,
        capacity=body.capacity,
        floor=body.floor,
    )
    db.add(c)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Constraint violated (duplicate code or invalid FK)")
    db.refresh(c)
    invalidate_twin_state()
    return c


# ===================================================================
# Courses
# ===================================================================

@router.get("/courses", response_model=PaginatedResponse)
def list_courses(
    department_id: int | None = None,
    page: int = 1,
    page_size: int = 20,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(Course)
    if department_id is not None:
        q = q.filter(Course.department_id == department_id)
    return _paginate(q.order_by(Course.id), page, page_size, CourseRead)


@router.get("/courses/{course_id}", response_model=CourseRead)
def get_course(
    course_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    c = db.get(Course, course_id)
    if not c:
        raise HTTPException(status_code=404, detail="Course not found")
    return c


@router.post("/courses", response_model=CourseRead, status_code=201)
def create_course(
    body: CourseCreate,
    user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    c = Course(
        name=body.name,
        code=body.code,
        department_id=body.department_id,
        credits=body.credits,
        semester=body.semester,
    )
    db.add(c)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Constraint violated (duplicate code or invalid FK)")
    db.refresh(c)
    return c


# ===================================================================
# Timetable
# ===================================================================

@router.get("/timetable", response_model=PaginatedResponse)
def list_timetable(
    classroom_id: int | None = None,
    course_id: int | None = None,
    day_of_week: int | None = None,
    page: int = 1,
    page_size: int = 50,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(Timetable)
    if classroom_id is not None:
        q = q.filter(Timetable.classroom_id == classroom_id)
    if course_id is not None:
        q = q.filter(Timetable.course_id == course_id)
    if day_of_week is not None:
        q = q.filter(Timetable.day_of_week == day_of_week)
    return _paginate(q.order_by(Timetable.id), page, page_size, TimetableRead)


@router.post("/timetable", response_model=TimetableRead, status_code=201)
def create_timetable(
    body: TimetableCreate,
    user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    if body.end_hour <= body.start_hour:
        raise HTTPException(status_code=422, detail="end_hour must be > start_hour")
    t = Timetable(
        course_id=body.course_id,
        classroom_id=body.classroom_id,
        faculty_id=body.faculty_id,
        day_of_week=body.day_of_week,
        start_hour=body.start_hour,
        end_hour=body.end_hour,
    )
    db.add(t)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Constraint violated")
    db.refresh(t)
    return t


# ===================================================================
# Faculty
# ===================================================================

@router.get("/faculty", response_model=PaginatedResponse)
def list_faculty(
    department_id: int | None = None,
    page: int = 1,
    page_size: int = 20,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(Faculty)
    if department_id is not None:
        q = q.filter(Faculty.department_id == department_id)
    return _paginate(q.order_by(Faculty.id), page, page_size, FacultyRead)


# ===================================================================
# Students (admin & faculty only)
# ===================================================================

@router.get("/students", response_model=PaginatedResponse)
def list_students(
    department_id: int | None = None,
    page: int = 1,
    page_size: int = 20,
    user: User = Depends(require_role("admin", "faculty")),
    db: Session = Depends(get_db),
):
    q = db.query(Student)
    if department_id is not None:
        q = q.filter(Student.department_id == department_id)
    return _paginate(q.order_by(Student.id), page, page_size, StudentRead)


# ===================================================================
# Personal views
# ===================================================================

@router.get("/me/timetable", response_model=list[TimetableRead])
def my_timetable(
    user: User = Depends(require_role("faculty", "student")),
    db: Session = Depends(get_db),
):
    """Return the timetable for the current faculty or student."""
    role_value = user.role.value if hasattr(user.role, "value") else user.role
    if role_value == "faculty":
        fac = db.query(Faculty).filter(Faculty.user_id == user.id).first()
        if not fac:
            raise HTTPException(status_code=404, detail="Faculty profile not found")
        slots = db.query(Timetable).filter(Timetable.faculty_id == fac.id).all()
    else:
        stu = db.query(Student).filter(Student.user_id == user.id).first()
        if not stu:
            raise HTTPException(status_code=404, detail="Student profile not found")
        enrolled_course_ids = [
            e.course_id for e in db.query(Enrollment).filter(Enrollment.student_id == stu.id).all()
        ]
        slots = db.query(Timetable).filter(Timetable.course_id.in_(enrolled_course_ids)).all() if enrolled_course_ids else []
    return slots


@router.get("/me/attendance", response_model=list[AttendanceSummary])
def my_attendance(
    user: User = Depends(require_role("student")),
    db: Session = Depends(get_db),
):
    """Return attendance percentage per course for the current student."""
    stu = db.query(Student).filter(Student.user_id == user.id).first()
    if not stu:
        raise HTTPException(status_code=404, detail="Student profile not found")

    # Get enrolled courses
    enrollments = db.query(Enrollment).filter(Enrollment.student_id == stu.id).all()
    results: list[AttendanceSummary] = []
    for enr in enrollments:
        course = db.get(Course, enr.course_id)
        if not course:
            continue
        total = db.query(Attendance).filter(
            Attendance.student_id == stu.id,
            Attendance.course_id == course.id,
        ).count()
        present = db.query(Attendance).filter(
            Attendance.student_id == stu.id,
            Attendance.course_id == course.id,
            Attendance.present.is_(True),
        ).count()
        pct = round(present / total * 100, 2) if total > 0 else 0.0
        results.append(AttendanceSummary(
            course_id=course.id,
            course_name=course.name,
            course_code=course.code,
            total_classes=total,
            present_count=present,
            percentage=pct,
        ))
    return results
