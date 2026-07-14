-- TalentBeacon™ Database Schema v1.0
CREATE DATABASE IF NOT EXISTS talentbeacon CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE talentbeacon;

-- Users & Authentication
CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(100) NOT NULL UNIQUE,
    email VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(30) NOT NULL DEFAULT 'employee',
    employee_id INT NULL,
    company_email VARCHAR(255) NULL,
    employee_login_id VARCHAR(50) NULL,
    first_login BOOLEAN DEFAULT FALSE,
    temp_password_used BOOLEAN DEFAULT FALSE,
    temp_password_expires_at VARCHAR(40) NULL,
    failed_attempts INT DEFAULT 0,
    locked_until VARCHAR(40) NULL,
    otp_hash VARCHAR(255) NULL,
    otp_expires_at VARCHAR(40) NULL,
    otp_used BOOLEAN DEFAULT FALSE,
    otp_purpose VARCHAR(40) NULL,
    source_dataset_id VARCHAR(100) NULL,
    source_employee_code VARCHAR(255) NULL,
    source_employee_key VARCHAR(255) NULL,
    source_file_hash VARCHAR(255) NULL,
    source_email VARCHAR(255) NULL,
    created_by INT NULL,
    created_from_upload BOOLEAN DEFAULT FALSE,
    created_from_demo BOOLEAN DEFAULT FALSE,
    name_from_file BOOLEAN DEFAULT FALSE,
    account_created BOOLEAN DEFAULT FALSE,
    account_status VARCHAR(40) NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    action VARCHAR(120) NOT NULL,
    actor_id INT NULL,
    target_id INT NULL,
    status VARCHAR(40) DEFAULT 'ok',
    details_json JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Employees
CREATE TABLE IF NOT EXISTS employees (
    id INT AUTO_INCREMENT PRIMARY KEY,
    employee_code VARCHAR(50) NOT NULL UNIQUE,
    name VARCHAR(200) DEFAULT NULL,
    email VARCHAR(255) DEFAULT NULL,
    department VARCHAR(100) NOT NULL,
    designation VARCHAR(100) NOT NULL,
    years_of_experience INT DEFAULT 0,
    education_level VARCHAR(100),
    performance_score INT DEFAULT 3,
    projects_handled INT DEFAULT 0,
    satisfaction_score DECIMAL(4,2) DEFAULT 3.0,
    hire_date DATE,
    dataset_upload_id INT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Uploaded candidate datasets
CREATE TABLE IF NOT EXISTS dataset_uploads (
    id INT AUTO_INCREMENT PRIMARY KEY,
    filename VARCHAR(255) NOT NULL,
    stored_filename VARCHAR(255) NULL,
    file_path VARCHAR(500) NULL,
    file_type ENUM('csv', 'excel') NOT NULL,
    row_count INT DEFAULT 0,
    is_active BOOLEAN DEFAULT FALSE,
    uploaded_by INT NULL,
    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Uploaded job descriptions
CREATE TABLE IF NOT EXISTS jd_uploads (
    id INT AUTO_INCREMENT PRIMARY KEY,
    filename VARCHAR(255) NOT NULL,
    extracted_text MEDIUMTEXT,
    requirements_json JSON,
    uploaded_by INT NULL,
    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Candidate match results for each JD
CREATE TABLE IF NOT EXISTS jd_candidate_matches (
    id INT AUTO_INCREMENT PRIMARY KEY,
    jd_upload_id INT NOT NULL,
    employee_id INT NOT NULL,
    match_score DECIMAL(5,2) NOT NULL,
    score_breakdown JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (jd_upload_id) REFERENCES jd_uploads(id) ON DELETE CASCADE,
    FOREIGN KEY (employee_id) REFERENCES employees(id) ON DELETE CASCADE,
    UNIQUE KEY uq_jd_employee_match (jd_upload_id, employee_id)
);

-- Skills Master Catalog
CREATE TABLE IF NOT EXISTS skills (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    category ENUM('technical', 'analytics', 'soft', 'other') DEFAULT 'technical',
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Employee Skills with proficiency
CREATE TABLE IF NOT EXISTS employee_skills (
    id INT AUTO_INCREMENT PRIMARY KEY,
    employee_id INT NOT NULL,
    skill_id INT NOT NULL,
    proficiency_level ENUM('beginner', 'intermediate', 'advanced', 'expert') DEFAULT 'intermediate',
    FOREIGN KEY (employee_id) REFERENCES employees(id) ON DELETE CASCADE,
    FOREIGN KEY (skill_id) REFERENCES skills(id) ON DELETE CASCADE,
    UNIQUE KEY uq_emp_skill (employee_id, skill_id)
);

-- Certifications
CREATE TABLE IF NOT EXISTS certifications (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(255) NOT NULL UNIQUE,
    provider VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS employee_certifications (
    id INT AUTO_INCREMENT PRIMARY KEY,
    employee_id INT NOT NULL,
    certification_id INT NOT NULL,
    obtained_date DATE,
    FOREIGN KEY (employee_id) REFERENCES employees(id) ON DELETE CASCADE,
    FOREIGN KEY (certification_id) REFERENCES certifications(id) ON DELETE CASCADE,
    UNIQUE KEY uq_emp_cert (employee_id, certification_id)
);

-- Job Roles
CREATE TABLE IF NOT EXISTS roles (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(150) NOT NULL UNIQUE,
    description TEXT,
    department VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS role_skills (
    id INT AUTO_INCREMENT PRIMARY KEY,
    role_id INT NOT NULL,
    skill_id INT NOT NULL,
    is_required BOOLEAN DEFAULT TRUE,
    min_level ENUM('beginner', 'intermediate', 'advanced', 'expert') DEFAULT 'intermediate',
    FOREIGN KEY (role_id) REFERENCES roles(id) ON DELETE CASCADE,
    FOREIGN KEY (skill_id) REFERENCES skills(id) ON DELETE CASCADE,
    UNIQUE KEY uq_role_skill (role_id, skill_id)
);

-- Learning Resources
CREATE TABLE IF NOT EXISTS learning_resources (
    id INT AUTO_INCREMENT PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    skill_id INT,
    source ENUM('internal_lms', 'youtube', 'company', 'external_cert') DEFAULT 'internal_lms',
    url VARCHAR(500),
    duration_hours DECIMAL(5,1),
    difficulty ENUM('beginner', 'intermediate', 'advanced') DEFAULT 'beginner',
    FOREIGN KEY (skill_id) REFERENCES skills(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS employee_learning (
    id INT AUTO_INCREMENT PRIMARY KEY,
    employee_id INT NOT NULL,
    resource_id INT NOT NULL,
    status ENUM('not_started', 'in_progress', 'completed') DEFAULT 'not_started',
    completion_date DATE,
    score DECIMAL(5,2),
    FOREIGN KEY (employee_id) REFERENCES employees(id) ON DELETE CASCADE,
    FOREIGN KEY (resource_id) REFERENCES learning_resources(id) ON DELETE CASCADE
);

-- Assessments
CREATE TABLE IF NOT EXISTS assessments (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    skill_id INT,
    max_score INT DEFAULT 100,
    FOREIGN KEY (skill_id) REFERENCES skills(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS employee_assessments (
    id INT AUTO_INCREMENT PRIMARY KEY,
    employee_id INT NOT NULL,
    assessment_id INT NOT NULL,
    score DECIMAL(5,2),
    taken_date DATE,
    FOREIGN KEY (employee_id) REFERENCES employees(id) ON DELETE CASCADE,
    FOREIGN KEY (assessment_id) REFERENCES assessments(id) ON DELETE CASCADE
);

-- Projects
CREATE TABLE IF NOT EXISTS projects (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    description TEXT,
    required_skills TEXT,
    min_experience INT DEFAULT 0,
    status ENUM('open', 'in_progress', 'completed') DEFAULT 'open',
    created_by INT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Project candidate matches from uploaded employee datasets
CREATE TABLE IF NOT EXISTS project_candidate_matches (
    id INT AUTO_INCREMENT PRIMARY KEY,
    project_id INT NOT NULL,
    employee_id INT NOT NULL,
    match_score DECIMAL(5,2) NOT NULL,
    score_breakdown JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    FOREIGN KEY (employee_id) REFERENCES employees(id) ON DELETE CASCADE,
    UNIQUE KEY uq_project_employee_match (project_id, employee_id)
);

-- Career paths
CREATE TABLE IF NOT EXISTS career_paths (
    id INT AUTO_INCREMENT PRIMARY KEY,
    from_role_id INT NOT NULL,
    to_role_id INT NOT NULL,
    transition_score DECIMAL(5,2) DEFAULT 0.5,
    FOREIGN KEY (from_role_id) REFERENCES roles(id) ON DELETE CASCADE,
    FOREIGN KEY (to_role_id) REFERENCES roles(id) ON DELETE CASCADE
);

-- ML model training logs
CREATE TABLE IF NOT EXISTS ml_training_logs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    model_name VARCHAR(100) NOT NULL,
    algorithm VARCHAR(50),
    accuracy DECIMAL(6,4),
    f1_score DECIMAL(6,4),
    rmse DECIMAL(8,4),
    metrics_json JSON,
    trained_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for performance
CREATE INDEX idx_emp_dept ON employees(department);
CREATE INDEX idx_emp_designation ON employees(designation);
CREATE INDEX idx_emp_email ON employees(email);
CREATE INDEX idx_emp_dataset_upload ON employees(dataset_upload_id);
CREATE INDEX idx_users_company_email ON users(company_email);
CREATE INDEX idx_users_source_dataset ON users(source_dataset_id);
CREATE INDEX idx_users_created_by ON users(created_by);
CREATE INDEX idx_users_employee_login_id ON users(employee_login_id);
CREATE INDEX idx_users_source_employee_key ON users(source_employee_key);
CREATE INDEX idx_audit_action ON audit_logs(action);
CREATE INDEX idx_audit_actor ON audit_logs(actor_id);
CREATE INDEX idx_audit_target ON audit_logs(target_id);
CREATE INDEX idx_skill_category ON skills(category);
CREATE INDEX idx_role_name ON roles(name);
CREATE INDEX idx_jd_match_score ON jd_candidate_matches(jd_upload_id, match_score);
CREATE INDEX idx_project_match_score ON project_candidate_matches(project_id, match_score);
