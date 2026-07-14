# TalentBeacon Production Deployment

TalentBeacon must be deployed as one public web application with one shared database. Do not run separate `127.0.0.1` copies on different laptops if users need the same accounts, projects, matches, and career results.

## Required Production Architecture

```text
Users on laptop / Android / tablet
        |
        v
Public HTTPS URL
        |
        v
One TalentBeacon Flask server
        |
        v
One shared MySQL database
        |
        v
Shared upload storage / persistent disk
```

## Environment Variables

Set these on the hosting platform:

```text
APP_ENV=production
SECRET_KEY=<strong-random-secret>
MYSQL_HOST=<public-or-private-db-host>
MYSQL_PORT=3306
MYSQL_USER=<db-user>
MYSQL_PASSWORD=<db-password>
MYSQL_DATABASE=talentbeacon
MYSQL_READS_ENABLED=1
UPLOADS_DIR=/persistent/uploads
MAX_UPLOAD_MB=50
```

`SECRET_KEY` must be different from the development default. The app will refuse to boot in production if it is not set.

## Startup Command

Production hosts should use:

```text
gunicorn wsgi:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120
```

The included `Procfile` already contains this command.

## Before First Production Run

1. Create the MySQL database.
2. Run database setup:

```powershell
python database/init_db.py
python database/seed.py
```

3. Start the deployed app.
4. Log in with Admin.
5. Upload and activate employee data once.
6. Generate/show employee accounts from the Users page.

## Important Behavior

- Same public URL + same MySQL database = same results on every device.
- Separate localhost copies = different results.
- Android mobile works through the public HTTPS URL in Chrome.
- Uploaded files need persistent storage. If the hosting platform deletes local files on restart, configure `UPLOADS_DIR` to a persistent disk or cloud storage mount.

## Deployment Platforms

Good options:

- Render + managed MySQL
- Railway + MySQL
- AWS Elastic Beanstalk/EC2 + RDS MySQL
- Azure App Service + Azure Database for MySQL
- VPS + MySQL
