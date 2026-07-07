# TalentBeacon MySQL Step By Step

## 1. Start MySQL

Make sure MySQL is running locally.

Current app settings are in `config.py`:

```text
Host: localhost
Port: 3306
User: root
Password: 9552087105
Database: talentbeacon
```

## 2. Create and sync the database

From PowerShell:

```powershell
cd "C:\Users\Himanshu\Desktop\CProjectsTalentBeacon"
python production_db_sync.py
```

This creates the `talentbeacon` database if needed, creates upload/matching tables, and syncs the active uploaded employee file into MySQL.

## 3. Run the website

```powershell
cd "C:\Users\Himanshu\Desktop\CProjectsTalentBeacon"
python run_5001.py
```

Open:

```text
http://127.0.0.1:5001/login
```

## 4. Upload employee files normally

Use the website:

```text
Employee Files -> Upload CSV/Excel -> Activate file
```

New uploads now sync to MySQL automatically. The app reads the logged-in user's active employee file from MySQL first. If MySQL is unavailable, it safely falls back to the existing uploaded file.

## 5. Verify MySQL employee reads

```powershell
cd "C:\Users\Himanshu\Desktop\CProjectsTalentBeacon"
python -c "from src.services.workspace_service import load_active_employee_df; df=load_active_employee_df(user_id=1); print(len(df)); print(df.iloc[0].get('Source') if len(df) else 'empty')"
```

Expected output after sync:

```text
4998
mysql
```

## 6. Turn MySQL reads off temporarily

Only if needed for debugging:

```powershell
$env:MYSQL_READS_ENABLED="0"
python run_5001.py
```

Default is enabled.
