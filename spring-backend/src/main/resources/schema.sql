CREATE TABLE IF NOT EXISTS `application` (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    applicant_name VARCHAR(100) NOT NULL,
    id_number VARCHAR(32) NOT NULL,
    applicant_user_id BIGINT,
    project_name VARCHAR(200),
    water_location VARCHAR(300),
    water_use VARCHAR(100),
    industry_category VARCHAR(100),
    contact_phone VARCHAR(32),
    status VARCHAR(20) NOT NULL,
    submission_time DATETIME NOT NULL,
    file_path TEXT,
    review_result LONGTEXT,
    review_time DATETIME
);

CREATE TABLE IF NOT EXISTS user_info (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    username VARCHAR(100) NOT NULL UNIQUE,
    password VARCHAR(100) NOT NULL DEFAULT '123456',
    role VARCHAR(50) NOT NULL,
    display_name VARCHAR(100) NOT NULL,
    identity_no VARCHAR(64) NOT NULL,
    user_type VARCHAR(30) NOT NULL DEFAULT 'PERSONAL',
    credit_code VARCHAR(64),
    phone VARCHAR(32) NOT NULL,
    email VARCHAR(120) NOT NULL,
    account_status VARCHAR(30) NOT NULL DEFAULT 'PENDING_ACTIVATION',
    failed_login_count INT NOT NULL DEFAULT 0,
    locked_until DATETIME,
    two_factor_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    created_at DATETIME NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_log (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    user_id BIGINT,
    action VARCHAR(100) NOT NULL,
    target_id BIGINT,
    message VARCHAR(500),
    created_at DATETIME NOT NULL
);
