-- ==========================================================================
-- Digital Twin of a University — Example analytical queries (MySQL 8.0)
-- ==========================================================================

-- 1. Average energy (kWh) by hour of day per building
SELECT
    b.name                             AS building_name,
    HOUR(er.ts)                        AS hour_of_day,
    ROUND(AVG(er.kwh), 2)             AS avg_kwh,
    COUNT(*)                           AS reading_count
FROM energy_records er
JOIN buildings b ON b.id = er.building_id
GROUP BY b.id, b.name, HOUR(er.ts)
ORDER BY b.name, hour_of_day;


-- 2. Room utilisation per day (percentage of available hours that are scheduled)
--    Assumes the academic day runs from 8:00 to 18:00 (10 hours).
SELECT
    c.name                                                          AS room_name,
    c.kind                                                          AS room_kind,
    t.day_of_week,
    SUM(t.end_hour - t.start_hour)                                 AS scheduled_hours,
    ROUND(SUM(t.end_hour - t.start_hour) / 10 * 100, 1)           AS utilisation_pct
FROM timetables t
JOIN classrooms c ON c.id = t.classroom_id
GROUP BY c.id, c.name, c.kind, t.day_of_week
ORDER BY c.name, t.day_of_week;


-- 3. Attendance percentage per student per course
SELECT
    u.name                                              AS student_name,
    s.roll_number,
    co.code                                             AS course_code,
    co.name                                             AS course_name,
    COUNT(a.id)                                         AS total_classes,
    SUM(CASE WHEN a.present = 1 THEN 1 ELSE 0 END)    AS present_count,
    ROUND(
        SUM(CASE WHEN a.present = 1 THEN 1 ELSE 0 END) / COUNT(a.id) * 100, 2
    )                                                   AS attendance_pct
FROM attendances a
JOIN students s   ON s.id  = a.student_id
JOIN users    u   ON u.id  = s.user_id
JOIN courses  co  ON co.id = a.course_id
GROUP BY s.id, u.name, s.roll_number, co.id, co.code, co.name
ORDER BY attendance_pct ASC;


-- 4. Top 5 most over-capacity timetable slots
--    (enrollment > room capacity)
SELECT
    t.id                                                AS timetable_id,
    co.code                                             AS course_code,
    c.name                                              AS room_name,
    c.capacity                                          AS room_capacity,
    enr.enrollment_count,
    (enr.enrollment_count - c.capacity)                AS overflow
FROM timetables t
JOIN classrooms c   ON c.id  = t.classroom_id
JOIN courses    co  ON co.id = t.course_id
JOIN (
    SELECT course_id, COUNT(*) AS enrollment_count
    FROM enrollments
    GROUP BY course_id
) enr ON enr.course_id = t.course_id
WHERE enr.enrollment_count > c.capacity
ORDER BY overflow DESC
LIMIT 5;
