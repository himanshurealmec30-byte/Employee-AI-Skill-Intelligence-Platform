# Employee Upload and Project Matching Testing

## Sample Employee File

Use `docs/sample_candidate_dataset.csv`.

Supported upload columns:

- `Name`
- `Email`
- `Skills`
- `Experience`
- `Education`
- `Department`
- `Job Title`
- `Certifications`

Skills and certifications can be separated with semicolons, commas, or pipes.

## Test Steps

1. Start MySQL.
2. Initialize/seed the database if needed:

```powershell
cd "C:\Users\Himanshu\Desktop\CProjectsTalentBeacon"
python database/seed.py
```

3. Start the Flask app:

```powershell
python run_5001.py
```

4. Open `http://127.0.0.1:5001/login`.
5. Login as admin: `admin` / `admin123`.
6. Go to `Employee Files`.
7. Upload `docs/sample_candidate_dataset.csv`.
8. Confirm the upload progress bar appears while the file is processing.
9. Confirm the file appears in the uploaded files table.
10. Use `Activate` to make one upload the active dataset.
11. Open the dashboard and confirm charts/KPIs reflect the active dataset.
12. Go to `Projects`.
13. Create a project with required skills such as `Python; SQL; NLP`, minimum experience, and optional description.
14. Click `Match`.
15. Review ranked employees and test search, skill filter, minimum score, and sorting.
16. Return to `Employee Files`, delete a non-needed upload, and confirm the file disappears after the confirmation prompt.

## Project Match Scoring

The match score is weighted as:

- Skills: 45%
- Experience: 20%
- Education: 15%
- Keywords: 20%

## Validation

- Employee uploads accept only `.csv`, `.xlsx`, and `.xls`.
- Empty files are rejected with a visible error message.
- Delete removes the stored file, upload metadata, and employee rows created from that upload.
- Only one uploaded file is active at a time.
