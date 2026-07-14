# TalentBeacon Professional Development Workflow

This document explains the complete planning and development checklist for TalentBeacon. It is written as a project guide for SRS, presentation, GitHub, and future production work.

## 1. Problem Statement

TalentBeacon is an AI-powered employee recommendation and skill intelligence platform. It helps Admin, HR, and Managers upload employee data, analyze skills, match employees to projects, identify skill gaps, and recommend learning paths.

## 2. Requirement Analysis

### Functional Requirements

The system should support:

- Secure login and logout
- Admin/HR employee file upload
- Employee account generation from uploaded files
- Role-based access for Admin, HR, Manager, and Employee
- Project requirement upload using CSV, Excel, PDF, DOC, DOCX, and text inputs where supported
- NLP-based project skill extraction
- AI/ML employee recommendation
- Skill gap analysis
- Career path recommendation
- Dashboard and analytics
- Reports and exports
- Audit logs for important user/admin actions
- Password reset and first-login password setup
- Duplicate file/project detection

### Non-Functional Requirements

The system should be:

- Secure: hashed passwords, protected routes, role-based access
- Fast: optimized upload checks, pagination-ready tables, efficient matching logic
- Responsive: works on desktop and mobile screens
- Scalable: supports production database configuration and uploaded datasets
- Reliable: handles missing files, invalid files, empty files, and database issues
- Easy to use: simple navigation and clear success/error messages
- Maintainable: modular Flask routes, services, ML, NLP, and database layers

## 3. Technology Stack

Current TalentBeacon stack:

| Layer | Technology |
| --- | --- |
| Frontend | HTML, CSS, Bootstrap, JavaScript, Chart.js |
| Backend | Python Flask |
| Database | MySQL |
| Machine Learning | Scikit-learn, XGBoost, Pandas, NumPy |
| NLP | TF-IDF, cosine similarity, skill aliases, regex extraction |
| Visualization | Chart.js, Plotly/Pandas reports |
| Deployment | WSGI, Gunicorn, Procfile, environment variables |

Possible future alternatives:

- Frontend: React
- Backend: FastAPI, Django, Node.js
- Database: PostgreSQL
- Visualization: external BI tools, if required

## 4. Database Design

Core database/storage concepts:

- Users
- Employees
- Uploaded employee files
- Projects
- Project documents
- Skills
- Employee skills
- Recommendations
- Training courses
- Certificates
- Performance data
- Audit logs
- OTP/reset tokens

Database design goals:

- Keep uploaded employee data connected to the correct user/admin.
- Keep active dataset selection isolated per account/organization.
- Do not mix data between different uploaded files.
- Store account status permanently so logout does not reset active accounts to pending.

## 5. System Architecture

```text
Frontend UI
    ↓
Flask Routes / REST APIs
    ↓
Authentication + RBAC
    ↓
Business Logic Services
    ↓
NLP + ML Recommendation Engine
    ↓
MySQL Database + Upload Storage
```

## 6. UI/UX Design

Main pages:

- Login
- First-login password setup
- Forgot password
- Dashboard
- Employee Files
- User Management
- Project Matching
- Talent Search
- Analytics
- Career/Profile
- ML Metrics
- Unauthorized access page

UI principles:

- Keep navigation role-based.
- Show clear loading states.
- Show large visible errors for empty or duplicate files.
- Keep employee detail views close to the selected employee.
- Use responsive layouts for mobile and desktop.

## 7. Authentication & Authorization

Implemented/planned security flow:

- Public self-registration removed
- Admin/HR creates or generates users
- Role comes from backend/database only
- Passwords stored using hashing
- Temporary password used for first login
- OTP supported in demo mode
- First login forces password change
- Dashboard blocked until first-login setup is completed
- Account lock after repeated failed login attempts
- Role-based page/API access

Role access:

| Role | Access |
| --- | --- |
| Admin | Full access |
| HR | Employee upload, user management, analytics, reports |
| Manager | Projects, matching, recommendations |
| Employee | Own profile only |

## 8. Data Validation

Validation rules:

- Required fields are checked before saving
- Email format validation
- Employee ID uniqueness handling
- Empty file detection
- Allowed file types only
- File size limits
- Duplicate upload detection
- Project document duplicate detection
- Safe skill normalization for case, spacing, and spelling variations

## 9. File Upload Strategy

Allowed employee files:

- CSV
- XLS
- XLSX

Allowed project requirement files:

- PDF
- DOC
- DOCX
- TXT

Upload rules:

- Validate file type
- Validate file size
- Reject empty files
- Reject duplicate files with a clear message
- Store upload metadata
- Allow activation of one employee dataset
- Delete should remove metadata and stored file where applicable

Future production recommendation:

- Add antivirus scanning before accepting uploads
- Store files in cloud storage such as S3
- Run heavy parsing in background jobs

## 10. AI/ML Planning

```text
Input data
    ↓
Preprocessing
    ↓
Skill normalization
    ↓
Feature engineering
    ↓
Model training
    ↓
Model saving/versioning
    ↓
Prediction
    ↓
Explainable recommendation report
```

Current ML/NLP features:

- TF-IDF skill embedding
- Cosine similarity
- Skill extraction from project text
- Hybrid match score
- XGBoost readiness model
- Random Forest and Logistic Regression baselines
- Model metrics page
- Explainable score breakdown for skills, experience, performance, and certifications

## 11. Error Handling

Handled cases include:

- Invalid login
- Account locked
- Unauthorized access
- Missing uploaded file
- Empty file
- Duplicate file
- Invalid CSV/Excel/PDF/DOC input
- Empty project description
- No active employee dataset
- No matching employees
- Database fallback or unavailable state

## 12. Logging

Important logs:

- Account created
- Login success
- Login failed
- Password changed
- Role changed
- Account locked
- File uploaded
- File deleted
- Dataset activated
- Project created
- Recommendation generated
- Errors and exceptions

## 13. Security

Security requirements:

- Password hashing
- SQL injection protection through parameterized queries
- XSS protection through template escaping and input sanitization
- CSRF protection recommended for production forms
- HTTPS in deployment
- Secure cookies in production
- Environment variables for secrets
- Secrets outside GitHub
- Rate limiting for login and OTP endpoints
- Role checks on frontend routes and backend APIs

## 14. Performance

Performance checklist:

- Database indexes for users, employees, uploads, and projects
- Pagination for large employee/user tables
- Lazy loading for heavy pages
- API caching where safe
- Background processing for large uploads and model training
- Duplicate detection before expensive processing
- Compression in production web server

## 15. Testing

Testing types:

- Unit testing
- Integration testing
- API testing
- UI testing
- Security testing
- Upload validation testing
- Role-based access testing
- Load testing
- User acceptance testing

Existing tests include:

- Authentication privacy tests
- Skill normalization tests

## 16. Documentation

Project documentation should include:

- README
- Installation guide
- MySQL setup guide
- Production deployment guide
- API documentation
- User manual
- Admin manual
- SRS
- Architecture diagram
- Testing instructions
- Model training guide

Existing files:

- `README.md`
- `MYSQL_STEP_BY_STEP.md`
- `PRODUCTION_DEPLOYMENT.md`
- `SHARED_SERVER_SETUP.md`
- `docs/technical_documentation.md`
- `docs/upload_matching_testing.md`
- `docs/development_workflow.md`

## 17. Deployment

Deployment planning:

- Use production MySQL database
- Configure environment variables
- Set strong `SECRET_KEY`
- Use HTTPS and domain name
- Use WSGI/Gunicorn server
- Configure file upload storage
- Add backup strategy
- Add monitoring and error reporting
- Do not commit secrets or real employee data to GitHub

## 18. Maintenance

Maintenance tasks:

- Bug fixes
- Security updates
- Dependency updates
- Database migrations
- Model retraining
- Skill vocabulary updates
- New feature requests
- Backup verification
- Log review

## 19. Future Scope

Possible future features:

- AI chatbot
- Resume parser
- Attendance integration
- Skill prediction
- Promotion prediction
- Internal job portal
- Advanced course recommendations
- Mobile app
- Email/SMS notifications
- Cloud file storage
- Organization multi-tenancy

## 20. Professional Development Workflow

```text
Problem Statement
    ↓
Requirement Analysis
    ↓
SRS Documentation
    ↓
Wireframes & UI Design
    ↓
Database Design
    ↓
System Architecture
    ↓
Frontend Development
    ↓
Backend Development
    ↓
Authentication & Security
    ↓
Machine Learning Integration
    ↓
Testing
    ↓
Optimization
    ↓
Deployment
    ↓
Monitoring
    ↓
Maintenance
```

## Current Project Status

TalentBeacon already covers most core workflow areas: authentication, employee upload, project upload, NLP extraction, ML matching, skill gap analysis, dashboard, analytics, reports, MySQL configuration, tests, and deployment structure.

Main production improvements still recommended:

- Add proper CSRF middleware for all forms
- Add real email provider for OTP/reset emails
- Add cloud storage for uploaded files
- Add migrations using Alembic or Flask-Migrate
- Add CI/CD testing before deployment
- Add centralized logging and monitoring
- Add load testing for large employee files
