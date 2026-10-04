from __future__ import annotations

from datetime import timedelta

import pytest
from starlette.websockets import WebSocketDisconnect

from app.models import (
    Anomaly,
    AnomalyStatus,
    Attendance,
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
from app.security import create_access_token, hash_password


def campus_fixture_data(db_session):
    university = University(name="Test Campus", code="TUNI")
    db_session.add(university)
    db_session.flush()
    department = Department(name="Computing", code="COMP", university_id=university.id)
    db_session.add(department)
    db_session.flush()
    building = Building(
        name="Academic A", code="ACA1", university_id=university.id,
        building_type="academic", floors=3,
    )
    db_session.add(building)
    db_session.flush()
    room = Classroom(
        name="Room 101", code="R101", building_id=building.id,
        kind=ClassroomKind.classroom, capacity=50,
    )
    library = Classroom(
        name="Library", code="LIB1", building_id=building.id,
        kind=ClassroomKind.library, capacity=100,
    )
    db_session.add_all([room, library])
    faculty_user = User(
        email="faculty@example.test", name="Faculty", hashed_password=hash_password("faculty-password"),
        role=UserRole.faculty, is_active=True,
    )
    student_user = User(
        email="student@example.test", name="Student", hashed_password=hash_password("student-password"),
        role=UserRole.student, is_active=True,
    )
    db_session.add_all([faculty_user, student_user])
    db_session.flush()
    faculty = Faculty(
        user_id=faculty_user.id, department_id=department.id,
        employee_id="FAC-1", designation="Professor",
    )
    student = Student(
        user_id=student_user.id, department_id=department.id,
        roll_number="STU-1", semester=3,
    )
    db_session.add_all([faculty, student])
    db_session.flush()
    course = Course(
        name="Foundations", code="COMP101", department_id=department.id,
        credits=3, semester=3,
    )
    db_session.add(course)
    db_session.flush()
    db_session.add_all([
        Enrollment(student_id=student.id, course_id=course.id),
        Timetable(
            course_id=course.id, classroom_id=room.id, faculty_id=faculty.id,
            day_of_week=0, start_hour=9, end_hour=10,
        ),
        Attendance(student_id=student.id, course_id=course.id, date=utcnow().date(), present=True),
    ])
    now = utcnow()
    for hour in range(12):
        ts = now - timedelta(hours=12 - hour)
        db_session.add(EnergyRecord(building_id=building.id, ts=ts, kwh=30.0 + hour))
        db_session.add(OccupancyRecord(classroom_id=room.id, ts=ts, count=15 + hour))
    db_session.commit()
    return {
        "university": university,
        "department": department,
        "building": building,
        "room": room,
        "library": library,
        "faculty": faculty,
        "faculty_user": faculty_user,
        "student": student,
        "student_user": student_user,
        "course": course,
    }


def bearer(user: User) -> dict[str, str]:
    token = create_access_token({"sub": str(user.id)})
    return {"Authorization": f"Bearer {token}"}


def test_extended_crud_and_personal_routes(client, db_session, admin_headers):
    data = campus_fixture_data(db_session)
    assert client.get("/courses", headers=admin_headers).json()["total"] == 1
    assert client.get("/timetable", headers=admin_headers).json()["total"] == 1
    assert client.get("/faculty", headers=admin_headers).json()["total"] == 1
    assert client.get("/students", headers=admin_headers).json()["total"] == 1

    response = client.get("/me/timetable", headers=bearer(data["student_user"]))
    assert response.status_code == 200 and len(response.json()) == 1
    response = client.get("/me/attendance", headers=bearer(data["student_user"]))
    assert response.status_code == 200
    assert response.json()[0]["percentage"] == 100.0

    created_course = client.post(
        "/courses",
        json={"name": "New Course", "code": "COMP202", "department_id": data["department"].id,
              "credits": 4, "semester": 4},
        headers=admin_headers,
    )
    assert created_course.status_code == 201
    created_slot = client.post(
        "/timetable",
        json={"course_id": created_course.json()["id"], "classroom_id": data["room"].id,
              "faculty_id": data["faculty"].id, "day_of_week": 1,
              "start_hour": 10, "end_hour": 11},
        headers=admin_headers,
    )
    assert created_slot.status_code == 201


def test_twin_telemetry_and_history(client, db_session, admin_headers):
    data = campus_fixture_data(db_session)

    state = client.get("/twin/state", headers=admin_headers)
    assert state.status_code == 200
    assert state.json()["buildings"][0]["latest_energy_kwh"] is not None

    tick = client.post("/telemetry/tick", headers=admin_headers)
    assert tick.status_code == 200
    assert tick.json()["energy_readings"] == 1
    assert tick.json()["occupancy_readings"] == 2
    assert client.get(f"/telemetry/energy?building_id={data['building'].id}", headers=admin_headers).json()["total"] == 13
    assert client.get(f"/telemetry/occupancy?classroom_id={data['room'].id}", headers=admin_headers).json()["total"] == 13


def test_csv_upload_valid_invalid_and_role_restrictions(client, db_session, admin_headers):
    data = campus_fixture_data(db_session)
    valid_csv = "building_code,timestamp,kwh\nACA1,2026-01-01T00:00:00,42.5\n"
    response = client.post(
        "/ingestion/csv?entity_type=energy",
        files={"file": ("energy.csv", valid_csv, "text/csv")},
        headers=admin_headers,
    )
    assert response.status_code == 200
    assert response.json()["imported"] == 1

    malformed = client.post(
        "/ingestion/csv?entity_type=energy",
        files={"file": ("bad.csv", "wrong,columns\n1,2\n", "text/csv")},
        headers=admin_headers,
    )
    assert malformed.status_code == 400

    denied = client.post(
        "/ingestion/csv?entity_type=energy",
        files={"file": ("energy.csv", valid_csv, "text/csv")},
        headers=bearer(data["student_user"]),
    )
    assert denied.status_code == 403


def test_predictions_anomaly_list_simulation_detail_and_optimization(client, db_session, admin_headers):
    data = campus_fixture_data(db_session)
    energy_prediction = client.post(f"/predictions/energy/{data['building'].id}?n_future=2", headers=admin_headers)
    assert energy_prediction.status_code == 200 and len(energy_prediction.json()) == 2
    occupancy_prediction = client.post(f"/predictions/occupancy/{data['room'].id}?n_future=2", headers=admin_headers)
    assert occupancy_prediction.status_code == 200 and len(occupancy_prediction.json()) == 2
    assert client.get("/predictions", headers=admin_headers).json()["total"] == 4

    anomaly = Anomaly(
        entity_type="building", entity_id=data["building"].id, metric="energy",
        observed_value=100.0, expected_value=30.0, score=-0.5,
        status=AnomalyStatus.detected, detected_at=utcnow(),
    )
    db_session.add(anomaly)
    db_session.commit()
    assert client.get("/anomalies", headers=admin_headers).json()["total"] == 1

    simulation = client.post(
        "/simulations",
        json={"name": "Campus growth", "simulation_type": "enrollment_growth", "parameters": {"percent": 10}},
        headers=admin_headers,
    )
    assert simulation.status_code == 201
    scenario_id = simulation.json()["scenario"]["id"]
    assert client.get(f"/simulations/{scenario_id}", headers=admin_headers).status_code == 200
    assert client.post("/optimization/classrooms", headers=admin_headers).status_code == 200


def test_websocket_requires_jwt_and_receives_live_tick(client, db_session, admin_user, admin_headers):
    campus_fixture_data(db_session)
    with client.websocket_connect(f"/ws/live?token={create_access_token({'sub': str(admin_user.id)})}") as socket:
        response = client.post("/telemetry/tick", headers=admin_headers)
        assert response.status_code == 200
        message = socket.receive_json()
        assert message["type"] == "tick"

    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/live?token=invalid"):
            pass


def test_user_role_is_loaded_from_database_not_jwt_claim(client, db_session):
    data = campus_fixture_data(db_session)
    forged_admin_token = create_access_token({"sub": str(data["student_user"].id), "role": "admin"})

    response = client.get(
        "/auth/users", headers={"Authorization": f"Bearer {forged_admin_token}"}
    )

    assert response.status_code == 403


def test_login_rate_limit(client):
    for _ in range(10):
        response = client.post(
            "/auth/login", data={"username": "unknown@example.test", "password": "wrong-password"}
        )
        assert response.status_code == 401

    limited = client.post(
        "/auth/login", data={"username": "unknown@example.test", "password": "wrong-password"}
    )
    assert limited.status_code == 429


def test_twin_aggregation_empty_and_multiple_buildings(db_session):
    from app.services.twin import get_twin_state

    assert get_twin_state(db_session)["buildings"] == []

    university = University(name="Twin Campus", code="TWIN")
    db_session.add(university)
    db_session.flush()
    building_a = Building(name="A", code="TWA", university_id=university.id, building_type="academic")
    building_b = Building(name="B", code="TWB", university_id=university.id, building_type="library")
    db_session.add_all([building_a, building_b])
    db_session.flush()
    room = Classroom(name="Room", code="TWR", building_id=building_a.id,
                     kind=ClassroomKind.classroom, capacity=40)
    db_session.add(room)
    db_session.flush()
    ts = utcnow()
    db_session.add_all([
        EnergyRecord(building_id=building_a.id, ts=ts - timedelta(minutes=1), kwh=25.0),
        EnergyRecord(building_id=building_a.id, ts=ts, kwh=30.0),
        OccupancyRecord(classroom_id=room.id, ts=ts, count=10),
        Anomaly(entity_type="building", entity_id=building_a.id, metric="energy",
                observed_value=90.0, expected_value=30.0, score=-0.5,
                status=AnomalyStatus.detected, detected_at=ts),
    ])
    db_session.commit()

    state = get_twin_state(db_session)
    assert len(state["buildings"]) == 2
    assert state["buildings"][0]["latest_energy_kwh"] == 30.0
    assert state["buildings"][0]["open_anomaly_count"] == 1
    assert state["buildings"][0]["spaces"][0]["utilization"] == 25.0
    assert state["buildings"][1]["latest_energy_kwh"] is None
