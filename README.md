# TalentBeacon™ – Employee Recommendation & Skill Intelligence Platform

AI-powered workforce analytics platform per SRS v1.0. Identifies best-fit employees, analyzes skill gaps, recommends learning paths, and predicts role readiness using **trained ML and NLP models**.

## Tech Stack

| Layer | Technology |
|-------|------------|
| Frontend | HTML, CSS, Bootstrap 5, JavaScript, Chart.js |
| Backend | Python Flask |
| Database | MySQL (root / configured in `config.py`) |
| NLP | TF-IDF, Cosine Similarity, Regex skill extraction |
| ML | XGBoost, Random Forest, Logistic Regression |
| Analytics | Pandas, NumPy, Scikit-Learn, Plotly |
| Alt UI | Streamlit (`app.py`) |

---

## Quick Start

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure MySQL
Edit `config.py` if needed (default: `root` / `9552087105`, database: `talentbeacon`).

### 3. Initialize database & seed 4,998 employees
```bash
python database/seed.py
```

### 4. Train ML & NLP models
```bash
python train_models.py
```

### 5. Run Flask web app (SRS primary UI)
```bash
python run.py
```
Open **http://localhost:5000**

### 6. (Optional) Run Streamlit dashboard
```bash
streamlit run app.py
```

---

## Admin Employee Upload & Project Matching

### Admin: upload employees
1. Login as `admin` / `admin123`
2. Open **Employee Files**
3. Upload a `.csv`, `.xlsx`, or `.xls` file

Sample format: `docs/sample_candidate_dataset.csv`

Recommended columns:
- `Name`
- `Email`
- `Skills`
- `Experience`
- `Education`
- `Department`
- `Job Title`
- `Certifications`

Uploaded rows are inserted into MySQL automatically and linked to an employee file upload record.
Admins can activate one uploaded file at a time. Dashboard charts, employee matching, skill gap analysis, and recommendations use the active upload. Admins can also delete uploaded files, which removes the stored file and its upload metadata.

### Manager/Admin: create projects and match employees
1. Login as `manager` / `manager123` or `admin` / `admin123`
2. Open **Projects**
3. Create a project with required skills, minimum experience, and optional description
4. Click **Match**
5. Review uploaded employees sorted by match score

Match score weights:
- Skills: 45%
- Experience: 20%
- Education: 15%
- Keywords: 20%

Detailed testing steps are in `docs/upload_matching_testing.md`.

---

## Login Credentials

| Role | Username | Password |
|------|----------|----------|
| Admin | admin | admin123 |
| Manager | manager | manager123 |
| Employee | employee | employee123 |

---

## SRS Modules Implemented

| Module | Description |
|--------|-------------|
| Authentication & RBAC | Login, logout, Admin/Manager/Employee roles |
| Employee Skill Profile | MySQL storage with skills, certs, performance |
| Skills Repository | Master skill catalog (91+ skills from dataset) |
| Role Intelligence | 6 target roles with required/desired skills |
| Employee Matching Engine | TF-IDF cosine + weighted hybrid scoring |
| Skill Gap Analysis | Missing skills, severity score, course recommendations |
| Learning Recommendations | Linked to skill gaps via LMS resources |
| Career Path Recommendation | Content-based filtering with roadmaps |
| Workforce Readiness Score | XGBoost regressor (R² ≈ 0.999) |
| Project Recommendation | NLP text → skills → ranked employees |
| Talent Discovery | Search by skill, department, performance |
| Workforce Analytics | Charts for skills, departments, KPIs |
| ML Training Dashboard | View model metrics (Admin only) |
| NLP Project Analysis | Extract skills/experience/certs from text |

---

## ML & NLP Training (Focus Area)

### Train all models
```bash
python train_models.py
```

### Models saved to `models/`
- `skill_tfidf.pkl` — NLP TF-IDF skill vectorizer (91 features)
- `skill_vocab.json` — Trained skill vocabulary
- `readiness_xgb.pkl` — XGBoost regressor + classifiers bundle
- `readiness_rf.pkl` — Random Forest classifier
- `readiness_lr.pkl` — Logistic Regression baseline
- `training_metrics.json` — Last run metrics

### Last training results
| Model | Metric | Value |
|-------|--------|-------|
| XGBoost Regressor | R² | 0.999 |
| XGBoost Classifier | Accuracy | 99.6% |
| XGBoost Classifier | F1 | 0.854 |
| Random Forest | Accuracy | 98.8% |
| Logistic Regression | F1 | 0.790 |

### Algorithms (per SRS Section 5)
- **NLP:** TF-IDF vectorization, cosine similarity, regex skill extraction
- **Recommendation:** Content-based filtering, hybrid weighted scoring
- **Readiness:** XGBoost, Random Forest, Logistic Regression

---

## Project Structure

```
TalentBeacon/
├── config.py                 # MySQL & model paths
├── run.py                    # Flask app entry point
├── train_models.py           # ML/NLP training pipeline
├── app.py                    # Streamlit dashboard (optional)
├── database/
│   ├── init_db.py            # Schema creation
│   ├── seed.py               # CSV → MySQL seeding
│   └── schema.sql            # SQL reference
├── models/                   # Trained model artifacts
├── src/
│   ├── db/                   # MySQL connection & repository
│   ├── ml/                   # Readiness trainer, skill gap, career path
│   ├── nlp/                  # TF-IDF embedder, similarity, extractor
│   ├── recommendation/       # Hybrid recommendation engine
│   ├── services/             # Unified talent service
│   └── dashboard/            # Streamlit pages
├── templates/                # Bootstrap HTML pages
├── static/                   # CSS & JS
└── employee management system cleaned data output2.csv
```

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/match/role/<role>` | Top 10 employees for role |
| POST | `/api/match/project` | Match by skill list |
| POST | `/api/nlp/parse` | NLP requirement extraction |
| GET | `/api/skill-gap/<emp_id>/<role>` | Skill gap report |
| GET | `/api/readiness/<emp_id>/<role>` | ML readiness score |
| GET | `/api/career/<emp_id>` | Career path recommendations |
| GET | `/api/search` | Talent discovery search |
| GET | `/api/analytics` | Organization analytics |

---

## Team Notes

- Re-run `python train_models.py` after uploading new employee data
- Re-run `python database/seed.py` to reset MySQL (drops & recreates DB)
- ML training logs are stored in `ml_training_logs` table when DB is available
