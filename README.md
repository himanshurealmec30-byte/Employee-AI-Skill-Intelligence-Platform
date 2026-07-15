# TalentBeacon

AI-powered employee recommendation and skill intelligence platform for employee file upload, project matching, talent search, career path recommendations, analytics, and secure role-based authentication.

## Tech Stack

- Frontend: HTML, CSS, JavaScript, Bootstrap
- Backend: Flask
- Database: MySQL
- ML/NLP: Scikit-learn, XGBoost, Pandas
- Deployment: Railway

## Features

- Admin/HR employee CSV/Excel upload
- Active dataset selection
- Employee account generation
- Secure login with OTP and password setup
- Role-based access: Admin, HR, Manager, Employee
- Talent search
- Project skill matching
- Career path recommendation
- Analytics dashboard
- PDF/Excel reports
- Audit logs

## Local Setup

```powershell
cd "C:\Users\Himanshu\Desktop\CProjectsTalentBeacon"

$env:MYSQL_HOST="your-mysql-host"
$env:MYSQL_PORT="3306"
$env:MYSQL_USER="root"
$env:MYSQL_PASSWORD="your-password"
$env:MYSQL_DATABASE="talentbeacon"
$env:APP_ENV="development"

python run_5001.py
```

Open:

```text
http://127.0.0.1:5001/login
```

## Testing

```powershell
python -m unittest tests.test_auth_privacy tests.test_skill_normalization
python -m py_compile run.py config.py src\db\repository.py
```

## Deployment

The project is deployed on Railway with Railway MySQL as the cloud database. All users connect to the same hosted database, so data stays consistent across devices.

## Future Scope

- Real email OTP using SMTP/SendGrid/AWS SES
- Advanced ML model training pipeline
- Resume parser
- Mobile app
- Power BI integration