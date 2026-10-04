-- ==========================================================================
-- Digital Twin of a University — Full MySQL 8.0 DDL
-- Engine: InnoDB | Charset: utf8mb4 | Collation: utf8mb4_unicode_ci
-- ==========================================================================

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- ------------------------------------------------------------------
-- Universities
-- ------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `universities` (
  `id`         INT           NOT NULL AUTO_INCREMENT,
  `name`       VARCHAR(255)  NOT NULL,
  `code`       VARCHAR(50)   NOT NULL,
  `address`    VARCHAR(500)  DEFAULT NULL,
  `created_at` DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_university_code` (`code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------------
-- Users
-- ------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `users` (
  `id`              INT          NOT NULL AUTO_INCREMENT,
  `email`           VARCHAR(255) NOT NULL,
  `name`            VARCHAR(255) NOT NULL,
  `hashed_password` VARCHAR(255) NOT NULL,
  `role`            ENUM('admin','faculty','student','facility_manager') NOT NULL,
  `is_active`       BOOLEAN      NOT NULL DEFAULT TRUE,
  `created_at`      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at`      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_user_email` (`email`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------------
-- Departments
-- ------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `departments` (
  `id`            INT          NOT NULL AUTO_INCREMENT,
  `name`          VARCHAR(255) NOT NULL,
  `code`          VARCHAR(50)  NOT NULL,
  `university_id` INT          NOT NULL,
  `created_at`    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_department_code` (`code`),
  CONSTRAINT `fk_dept_university` FOREIGN KEY (`university_id`)
    REFERENCES `universities` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------------
-- Buildings
-- ------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `buildings` (
  `id`            INT          NOT NULL AUTO_INCREMENT,
  `name`          VARCHAR(255) NOT NULL,
  `code`          VARCHAR(50)  NOT NULL,
  `university_id` INT          NOT NULL,
  `building_type` VARCHAR(50)  NOT NULL,
  `floors`        INT          NOT NULL DEFAULT 1,
  `created_at`    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_building_code` (`code`),
  CONSTRAINT `fk_building_university` FOREIGN KEY (`university_id`)
    REFERENCES `universities` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------------
-- Classrooms (classroom | lab | library | hostel)
-- ------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `classrooms` (
  `id`          INT          NOT NULL AUTO_INCREMENT,
  `name`        VARCHAR(255) NOT NULL,
  `code`        VARCHAR(50)  NOT NULL,
  `building_id` INT          NOT NULL,
  `kind`        ENUM('classroom','lab','library','hostel') NOT NULL DEFAULT 'classroom',
  `capacity`    INT          NOT NULL,
  `floor`       INT          NOT NULL DEFAULT 0,
  `created_at`  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_classroom_code` (`code`),
  CONSTRAINT `ck_classroom_capacity` CHECK (`capacity` > 0),
  CONSTRAINT `fk_classroom_building` FOREIGN KEY (`building_id`)
    REFERENCES `buildings` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------------
-- Faculty
-- ------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `faculty` (
  `id`            INT          NOT NULL AUTO_INCREMENT,
  `user_id`       INT          NOT NULL,
  `department_id` INT          NOT NULL,
  `employee_id`   VARCHAR(50)  NOT NULL,
  `designation`   VARCHAR(100) NOT NULL,
  `created_at`    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_faculty_employee_id` (`employee_id`),
  UNIQUE KEY `uq_faculty_user_id` (`user_id`),
  CONSTRAINT `fk_faculty_user` FOREIGN KEY (`user_id`)
    REFERENCES `users` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_faculty_dept` FOREIGN KEY (`department_id`)
    REFERENCES `departments` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------------
-- Students
-- ------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `students` (
  `id`            INT          NOT NULL AUTO_INCREMENT,
  `user_id`       INT          NOT NULL,
  `department_id` INT          NOT NULL,
  `roll_number`   VARCHAR(50)  NOT NULL,
  `semester`      INT          NOT NULL,
  `created_at`    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_student_roll_number` (`roll_number`),
  UNIQUE KEY `uq_student_user_id` (`user_id`),
  CONSTRAINT `fk_student_user` FOREIGN KEY (`user_id`)
    REFERENCES `users` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_student_dept` FOREIGN KEY (`department_id`)
    REFERENCES `departments` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------------
-- Courses
-- ------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `courses` (
  `id`            INT          NOT NULL AUTO_INCREMENT,
  `name`          VARCHAR(255) NOT NULL,
  `code`          VARCHAR(50)  NOT NULL,
  `department_id` INT          NOT NULL,
  `credits`       INT          NOT NULL DEFAULT 3,
  `semester`      INT          NOT NULL,
  `created_at`    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_course_code` (`code`),
  CONSTRAINT `fk_course_dept` FOREIGN KEY (`department_id`)
    REFERENCES `departments` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------------
-- Enrollments (student ↔ course M:N)
-- ------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `enrollments` (
  `id`          INT      NOT NULL AUTO_INCREMENT,
  `student_id`  INT      NOT NULL,
  `course_id`   INT      NOT NULL,
  `enrolled_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_enrollment_student_course` (`student_id`, `course_id`),
  CONSTRAINT `fk_enrollment_student` FOREIGN KEY (`student_id`)
    REFERENCES `students` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_enrollment_course` FOREIGN KEY (`course_id`)
    REFERENCES `courses` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------------
-- Timetables
-- ------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `timetables` (
  `id`           INT      NOT NULL AUTO_INCREMENT,
  `course_id`    INT      NOT NULL,
  `classroom_id` INT      NOT NULL,
  `faculty_id`   INT      NOT NULL,
  `day_of_week`  INT      NOT NULL,
  `start_hour`   INT      NOT NULL,
  `end_hour`     INT      NOT NULL,
  `created_at`   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  CONSTRAINT `ck_timetable_day`   CHECK (`day_of_week` >= 0 AND `day_of_week` <= 6),
  CONSTRAINT `ck_timetable_hours` CHECK (`end_hour` > `start_hour`),
  CONSTRAINT `fk_timetable_course`    FOREIGN KEY (`course_id`)    REFERENCES `courses` (`id`)    ON DELETE CASCADE,
  CONSTRAINT `fk_timetable_classroom` FOREIGN KEY (`classroom_id`) REFERENCES `classrooms` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_timetable_faculty`   FOREIGN KEY (`faculty_id`)   REFERENCES `faculty` (`id`)    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------------
-- Attendances
-- ------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `attendances` (
  `id`         INT     NOT NULL AUTO_INCREMENT,
  `student_id` INT     NOT NULL,
  `course_id`  INT     NOT NULL,
  `date`       DATE    NOT NULL,
  `present`    BOOLEAN NOT NULL,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_attendance_student_course_date` (`student_id`, `course_id`, `date`),
  CONSTRAINT `fk_attendance_student` FOREIGN KEY (`student_id`) REFERENCES `students` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_attendance_course`  FOREIGN KEY (`course_id`)  REFERENCES `courses` (`id`)  ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------------
-- Energy records (time-series per building)
-- ------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `energy_records` (
  `id`          INT      NOT NULL AUTO_INCREMENT,
  `building_id` INT      NOT NULL,
  `ts`          DATETIME NOT NULL,
  `kwh`         FLOAT    NOT NULL,
  `created_at`  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  INDEX `ix_energy_building_ts` (`building_id`, `ts`),
  CONSTRAINT `fk_energy_building` FOREIGN KEY (`building_id`)
    REFERENCES `buildings` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------------
-- Occupancy records (time-series per classroom)
-- ------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `occupancy_records` (
  `id`           INT      NOT NULL AUTO_INCREMENT,
  `classroom_id` INT      NOT NULL,
  `ts`           DATETIME NOT NULL,
  `count`        INT      NOT NULL,
  `created_at`   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  INDEX `ix_occupancy_classroom_ts` (`classroom_id`, `ts`),
  CONSTRAINT `fk_occupancy_classroom` FOREIGN KEY (`classroom_id`)
    REFERENCES `classrooms` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------------
-- Predictions
-- ------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `predictions` (
  `id`          INT          NOT NULL AUTO_INCREMENT,
  `entity_type` VARCHAR(50)  NOT NULL,
  `entity_id`   INT          NOT NULL,
  `metric`      VARCHAR(50)  NOT NULL,
  `target_ts`   DATETIME     NOT NULL,
  `value`       FLOAT        NOT NULL,
  `model_name`  VARCHAR(100) NOT NULL,
  `mae`         FLOAT        DEFAULT NULL,
  `created_at`  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------------
-- Anomalies
-- ------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `anomalies` (
  `id`              INT         NOT NULL AUTO_INCREMENT,
  `entity_type`     VARCHAR(50) NOT NULL,
  `entity_id`       INT         NOT NULL,
  `metric`          VARCHAR(50) NOT NULL,
  `observed_value`  FLOAT       NOT NULL,
  `expected_value`  FLOAT       NOT NULL,
  `score`           FLOAT       NOT NULL,
  `status`          ENUM('detected','acknowledged','resolved','dismissed') NOT NULL DEFAULT 'detected',
  `note`            TEXT        DEFAULT NULL,
  `detected_at`     DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `acknowledged_at` DATETIME    DEFAULT NULL,
  `resolved_at`     DATETIME    DEFAULT NULL,
  `created_at`      DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------------
-- Simulation scenarios
-- ------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `simulation_scenarios` (
  `id`              INT          NOT NULL AUTO_INCREMENT,
  `name`            VARCHAR(255) NOT NULL,
  `simulation_type` VARCHAR(50)  NOT NULL,
  `parameters`      JSON         NOT NULL,
  `created_by`      INT          DEFAULT NULL,
  `created_at`      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  CONSTRAINT `fk_scenario_user` FOREIGN KEY (`created_by`)
    REFERENCES `users` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------------
-- Simulation results
-- ------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `simulation_results` (
  `id`               INT      NOT NULL AUTO_INCREMENT,
  `scenario_id`      INT      NOT NULL,
  `baseline_metrics` JSON     NOT NULL,
  `scenario_metrics` JSON     NOT NULL,
  `deltas`           JSON     NOT NULL,
  `warnings`         JSON     DEFAULT NULL,
  `feasible`         BOOLEAN  NOT NULL,
  `created_at`       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  CONSTRAINT `fk_result_scenario` FOREIGN KEY (`scenario_id`)
    REFERENCES `simulation_scenarios` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

SET FOREIGN_KEY_CHECKS = 1;
