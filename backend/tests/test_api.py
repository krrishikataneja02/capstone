"""
API integration tests — test endpoints via FastAPI TestClient + SQLite.
"""

from __future__ import annotations

import pytest

from app.models import (
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
    Anomaly,
    AnomalyStatus,
    utcnow,
)
from app.security import hash_password
from datetime import datetime, timedelta


# ===================================================================
# Health
# ===================================================================


class TestHealth:
    def test_health(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
        assert resp.json()["application"] == "ok"
        assert resp.json()["database"] == "ok"


# ===================================================================
# Auth
# ===================================================================


class TestAuth:
    def test_login_success(self, client, admin_user):
        resp = client.post(
            "/auth/login",
            data={"username": "admin@test.com", "password": "admin123"},
        )
        assert resp.status_code == 200
        assert "access_token" in resp.json()

    def test_login_wrong_password(self, client, admin_user):
        resp = client.post(
            "/auth/login",
            data={"username": "admin@test.com", "password": "wrong"},
        )
        assert resp.status_code == 401

    def test_me(self, client, admin_headers):
        resp = client.get("/auth/me", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["email"] == "admin@test.com"

    def test_me_no_auth(self, client):
        resp = client.get("/auth/me")
        assert resp.status_code == 401

    def test_create_user_as_admin(self, client, admin_headers):
        resp = client.post(
            "/auth/users",
            json={"email": "new@test.com", "name": "New User", "password": "newpass123", "role": "student"},
            headers=admin_headers,
        )
        assert resp.status_code == 201
        assert resp.json()["email"] == "new@test.com"
        assert "hashed_password" not in resp.json()

    def test_create_user_duplicate_email(self, client, admin_headers, admin_user):
        resp = client.post(
            "/auth/users",
            json={"email": "admin@test.com", "name": "Dup", "password": "pass123456", "role": "student"},
            headers=admin_headers,
        )
        assert resp.status_code == 409

    def test_list_users_non_admin_forbidden(self, client, db_session):
        # Create a student user and generate token directly
        from app.security import create_access_token
        user = User(
            email="student@test.com", name="Student", hashed_password=hash_password("pass123"),
            role=UserRole.student, is_active=True,
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)
        token = create_access_token({"sub": str(user.id), "role": "student"})
        resp = client.get("/auth/users", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 403


# ===================================================================
# CRUD
# ===================================================================


class TestCrud:
    @pytest.fixture(autouse=True)
    def setup(self, db_session):
        """Create university for FK references."""
        self.uni = University(name="Test Uni", code="TU", address="Test")
        db_session.add(self.uni)
        db_session.commit()
        db_session.refresh(self.uni)

    def test_create_and_list_departments(self, client, admin_headers, db_session):
        resp = client.post(
            "/departments",
            json={"name": "CS", "code": "CS", "university_id": self.uni.id},
            headers=admin_headers,
        )
        assert resp.status_code == 201
        dept_id = resp.json()["id"]

        resp = client.get("/departments", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1

        resp = client.get(f"/departments/{dept_id}", headers=admin_headers)
        assert resp.status_code == 200

    def test_department_not_found(self, client, admin_headers):
        resp = client.get("/departments/9999", headers=admin_headers)
        assert resp.status_code == 404

    def test_create_and_list_buildings(self, client, admin_headers, db_session):
        resp = client.post(
            "/buildings",
            json={"name": "Block A", "code": "BLA", "university_id": self.uni.id, "building_type": "academic"},
            headers=admin_headers,
        )
        assert resp.status_code == 201

    def test_create_classroom(self, client, admin_headers, db_session):
        bldg = Building(name="B1", code="B1X", university_id=self.uni.id, building_type="academic", floors=2)
        db_session.add(bldg)
        db_session.commit()
        db_session.refresh(bldg)

        resp = client.post(
            "/classrooms",
            json={"name": "R101", "code": "R101", "building_id": bldg.id, "kind": "classroom", "capacity": 50, "floor": 1},
            headers=admin_headers,
        )
        assert resp.status_code == 201

    def test_duplicate_code_returns_409(self, client, admin_headers, db_session):
        client.post(
            "/departments",
            json={"name": "CS", "code": "DUP", "university_id": self.uni.id},
            headers=admin_headers,
        )
        resp = client.post(
            "/departments",
            json={"name": "CS2", "code": "DUP", "university_id": self.uni.id},
            headers=admin_headers,
        )
        assert resp.status_code == 409


# ===================================================================
# Anomaly lifecycle
# ===================================================================


class TestAnomalyLifecycle:
    def test_detect_acknowledge_resolve(self, client, admin_headers, db_session):
        # Manually create an anomaly
        anom = Anomaly(
            entity_type="building", entity_id=1, metric="energy",
            observed_value=500.0, expected_value=50.0, score=-0.5,
            status=AnomalyStatus.detected, detected_at=utcnow(),
        )
        db_session.add(anom)
        db_session.commit()
        db_session.refresh(anom)

        # Acknowledge
        resp = client.patch(
            f"/anomalies/{anom.id}",
            json={"status": "acknowledged", "note": "Looking into it"},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "acknowledged"

        # Resolve
        resp = client.patch(
            f"/anomalies/{anom.id}",
            json={"status": "resolved"},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "resolved"

    def test_invalid_transition_returns_409(self, client, admin_headers, db_session):
        anom = Anomaly(
            entity_type="building", entity_id=1, metric="energy",
            observed_value=500.0, expected_value=50.0, score=-0.5,
            status=AnomalyStatus.resolved, detected_at=utcnow(),
        )
        db_session.add(anom)
        db_session.commit()
        db_session.refresh(anom)

        # Can't go from resolved to acknowledged
        resp = client.patch(
            f"/anomalies/{anom.id}",
            json={"status": "acknowledged"},
            headers=admin_headers,
        )
        assert resp.status_code == 409

    def test_dismiss_from_detected(self, client, admin_headers, db_session):
        anom = Anomaly(
            entity_type="building", entity_id=1, metric="energy",
            observed_value=500.0, expected_value=50.0, score=-0.5,
            status=AnomalyStatus.detected, detected_at=utcnow(),
        )
        db_session.add(anom)
        db_session.commit()
        db_session.refresh(anom)

        resp = client.patch(
            f"/anomalies/{anom.id}",
            json={"status": "dismissed"},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "dismissed"


# ===================================================================
# Simulation
# ===================================================================


class TestSimulation:
    @pytest.fixture(autouse=True)
    def setup_data(self, db_session):
        """Create minimal data for simulation tests."""
        uni = University(name="Uni", code="U1")
        db_session.add(uni)
        db_session.flush()

        dept = Department(name="CS", code="CS", university_id=uni.id)
        db_session.add(dept)
        db_session.flush()

        bldg = Building(name="B1", code="B1", university_id=uni.id, building_type="academic", floors=2)
        db_session.add(bldg)
        db_session.flush()

        room = Classroom(name="R1", code="R1", building_id=bldg.id, kind=ClassroomKind.classroom, capacity=60)
        db_session.add(room)
        db_session.flush()

        course = Course(name="CS101", code="CS101", department_id=dept.id, credits=3, semester=3)
        db_session.add(course)
        db_session.flush()

        # Create a faculty user + faculty record
        fac_user = User(
            email="fac@test.com", name="Faculty", hashed_password=hash_password("pass"),
            role=UserRole.faculty, is_active=True,
        )
        db_session.add(fac_user)
        db_session.flush()
        fac = Faculty(user_id=fac_user.id, department_id=dept.id, employee_id="E001", designation="Professor")
        db_session.add(fac)
        db_session.flush()

        tt = Timetable(course_id=course.id, classroom_id=room.id, faculty_id=fac.id, day_of_week=0, start_hour=9, end_hour=10)
        db_session.add(tt)
        db_session.flush()

        # Enroll some students
        for i in range(20):
            su = User(
                email=f"stu{i}@test.com", name=f"S{i}", hashed_password=hash_password("pass"),
                role=UserRole.student, is_active=True,
            )
            db_session.add(su)
            db_session.flush()
            s = Student(user_id=su.id, department_id=dept.id, roll_number=f"R{i:04d}", semester=3)
            db_session.add(s)
            db_session.flush()
            e = Enrollment(student_id=s.id, course_id=course.id)
            db_session.add(e)

        db_session.commit()
        self.building_id = bldg.id

    def test_enrollment_growth_simulation(self, client, admin_headers):
        resp = client.post(
            "/simulations",
            json={"name": "Growth Test", "simulation_type": "enrollment_growth", "parameters": {"percent": 10}},
            headers=admin_headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert "scenario" in data
        assert "results" in data
        assert len(data["results"]) == 1

    def test_close_building_simulation(self, client, admin_headers):
        resp = client.post(
            "/simulations",
            json={"name": "Close Test", "simulation_type": "close_building", "parameters": {"building_id": self.building_id}},
            headers=admin_headers,
        )
        assert resp.status_code == 201

    def test_invalid_simulation_type(self, client, admin_headers):
        resp = client.post(
            "/simulations",
            json={"name": "Bad", "simulation_type": "invalid_type", "parameters": {}},
            headers=admin_headers,
        )
        assert resp.status_code == 422

    def test_list_simulations(self, client, admin_headers):
        resp = client.get("/simulations", headers=admin_headers)
        assert resp.status_code == 200
