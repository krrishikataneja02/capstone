# Digital Twin of a University — Backend

An intelligent platform for real-time monitoring, predictive analytics, simulation and optimization of campus operations.

**Team**: Full Stack AI specialization, School of Computer Science, UPES Dehradun.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Framework | FastAPI (Python 3.11+) |
| Database | MySQL 8.0 (InnoDB, utf8mb4) |
| ORM | SQLAlchemy 2.0 |
| Migrations | Alembic |
| Auth | JWT (PyJWT) + bcrypt |
| ML | scikit-learn (Random Forest, Isolation Forest) |
| Optimization | scipy (Hungarian algorithm) |
| Real-time | WebSocket |
| Cache | Redis |
| Validation | Pydantic v2 |

---

## Quick Start

### 1. Prerequisites

- Python 3.11+
- Docker & Docker Compose (for MySQL and Redis)

### 2. Configure Environment

```bash
cp .env.example .env
```

The example values are local-development credentials only. Set `DATABASE_URL` to match the Compose MySQL credentials before running the backend.

### 3. Start Infrastructure

```bash
docker compose up -d
```

This starts MySQL 8.0 on port 3306 and Redis on port 6379.

### 4. Install Dependencies

```bash
pip install -r requirements.txt
```

### 5. Run Database Migrations

```bash
alembic upgrade head
```

### 6. Seed the Database

```bash
python -m scripts.seed
```

To reset and re-seed:

```bash
python -m scripts.seed --reset
```

This creates:
- 1 university (UPES Dehradun)
- 4 departments
- 6 buildings (~25 spaces)
- 12 faculty, 200 students
- 16 courses with enrollments
- Conflict-free timetable
- 4 days of hourly energy & occupancy data
- 30 days of attendance records
- Admin: `admin@upes.ac.in` / `password123`
- Facility Manager: `facilities@upes.ac.in` / `password123`

### 7. Run the Server

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

API docs: http://localhost:8000/docs

### 8. Run Tests

```bash
pytest tests/ -v
```

Tests use SQLite in-memory — no MySQL needed.

---

## Project Structure

```
backend/
├── app/
│   ├── main.py          # FastAPI app, CORS, lifespan, WS, health
│   ├── config.py        # Pydantic Settings (env vars)
│   ├── database.py      # SQLAlchemy engine + session
│   ├── models.py        # ORM models (17 entities)
│   ├── schemas.py       # Pydantic v2 request/response schemas
│   ├── security.py      # JWT + bcrypt
│   ├── deps.py          # Dependency injection (DB, auth, RBAC)
│   ├── ws.py            # WebSocket connection manager
│   ├── routers/
│   │   ├── auth.py      # Login, /auth/me, user management
│   │   ├── crud.py      # Departments, buildings, classrooms, courses, timetable, /me/*
│   │   ├── twin.py      # GET /twin/state
│   │   ├── ingestion.py # CSV import, telemetry tick, energy/occupancy history
│   │   └── analytics.py # Predictions, anomalies, simulations, optimization
│   └── services/
│       ├── anomaly.py       # Isolation Forest + z-score (pure function)
│       ├── forecast.py      # Random Forest regression (pure function)
│       ├── simulation.py    # What-if: enrollment growth, close building (pure)
│       ├── optimization.py  # Hungarian algorithm classroom allocation (pure)
│       ├── campus_data.py   # Simulated sensor data generators
│       └── twin.py          # Twin state aggregation
├── alembic/             # Alembic migrations
├── db/
│   ├── schema.sql       # Plain MySQL DDL
│   └── queries.sql      # Example analytical queries
├── scripts/
│   └── seed.py          # Database seeding
├── tests/
│   ├── conftest.py      # Test fixtures (SQLite in-memory)
│   ├── test_services.py # Unit tests for pure service functions
│   └── test_api.py      # API integration tests
├── requirements.txt
├── docker-compose.yml
├── alembic.ini
├── .env.example
└── README.md
```

---

## API Endpoints

### Auth
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/auth/login` | — | OAuth2 password login (rate-limited) |
| GET | `/auth/me` | Any | Current user profile |
| GET | `/auth/users` | Admin | List all users |
| POST | `/auth/users` | Admin | Create a user |

### CRUD
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET/POST | `/departments` | Read: any, Write: admin | Departments |
| GET | `/departments/{id}` | Any | Single department |
| GET/POST | `/buildings` | Read: any, Write: admin | Buildings |
| GET/POST | `/classrooms` | Read: any, Write: admin | Classrooms |
| GET/POST | `/courses` | Read: any, Write: admin | Courses |
| GET/POST | `/timetable` | Read: any, Write: admin | Timetable |
| GET | `/faculty` | Any | Faculty list |
| GET | `/students` | Admin, Faculty | Student list |

### Personal
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/me/timetable` | Faculty, Student | My timetable |
| GET | `/me/attendance` | Student | My attendance % |

### Twin State
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/twin/state` | Any | Per-building live snapshot |

### Telemetry
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/telemetry/tick` | Any | Simulate one sensor round |
| GET | `/telemetry/energy?building_id=` | Any | Energy history |
| GET | `/telemetry/occupancy?classroom_id=` | Any (students: lib/hostel only) | Occupancy history |

### Ingestion
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/ingestion/csv?entity_type=` | Admin | Import CSV (students/courses/energy) |

### Analytics
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/predictions/energy/{building_id}` | Any | Energy forecast |
| POST | `/predictions/occupancy/{classroom_id}` | Any (students: lib/hostel) | Occupancy forecast |
| GET | `/predictions` | Any | List predictions |
| GET | `/anomalies` | Admin, FM | List anomalies |
| PATCH | `/anomalies/{id}` | Admin, FM | Update anomaly status |
| POST | `/simulations` | Admin | Run what-if simulation |
| GET | `/simulations` | Admin | List simulations |
| GET | `/simulations/{id}` | Admin | Simulation details |
| POST | `/optimization/classrooms` | Admin, FM | Classroom optimization |

### Other
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/health` | — | Health check |
| WS | `/ws/live?token=` | JWT | Real-time broadcasts |

---

## Roles (RBAC)

| Role | Capabilities |
|------|-------------|
| **admin** | Full access: manage users, configure twin entities, run simulations, view everything |
| **faculty** | View classrooms, timetable, courses, attendance analytics |
| **student** | View own timetable/attendance, library/hostel occupancy predictions |
| **facility_manager** | Monitor energy, manage anomalies, view optimization output |

---

## Anomaly Lifecycle

```
DETECTED → ACKNOWLEDGED → RESOLVED
DETECTED → DISMISSED
ACKNOWLEDGED → DISMISSED
```

Invalid transitions return HTTP 409.

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | credential-free local MySQL URL | MySQL connection |
| `ENV` | `dev` | Runtime mode (`dev` or `prod`); production requires a unique 32+ character key and explicit CORS origins |
| `SECRET_KEY` | development-only fallback | JWT signing key; set a unique random value in production |
| `JWT_ALGORITHM` | `HS256` | JWT algorithm |
| `JWT_EXPIRATION_MINUTES` | `60` | Token TTL |
| `REDIS_URL` | unset (Redis optional) | Redis connection; set to `redis://localhost:6379/0` for local Compose |
| `CORS_ORIGINS` | `http://localhost:3000` | Allowed CORS origins |
| `SIMULATOR_ENABLED` | `false` | Auto-tick background loop |
| `SIMULATOR_INTERVAL_SECONDS` | `10` | Tick interval |
| `CAMPUS_TIMEZONE` | `Asia/Kolkata` | Campus-local timezone |
| `MYSQL_ROOT_PASSWORD` | local-only example | Docker Compose MySQL root password |
| `MYSQL_USER` | `twin` | Docker Compose application user |
| `MYSQL_PASSWORD` | local-only example | Docker Compose application password |
