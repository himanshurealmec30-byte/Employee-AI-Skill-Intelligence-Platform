import unittest
from unittest.mock import patch
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd
from werkzeug.datastructures import FileStorage

import config
from run import _skill_filter_match
from src.ml.skill_gap import analyze_gap_from_skill_lists
from src.nlp.similarity import SkillSimilarityModel
from src.recommendation.engine import RecommendationEngine
from src.services.workspace_service import _parse_document_requirements
from src.services import workspace_service
from src.services.workspace_service import process_dataset_upload
from src.services.workspace_service import project_requirements_from_document, save_project_from_form
from src.services.talent_service import TalentBeaconService
from src.services.workspace_service import score_employee
from src.utils.skills import contains_all_skills, normalize_skill_key


class SkillNormalizationTests(unittest.TestCase):
    def test_case_and_spacing_are_ignored(self):
        variants = ["Python", "python", " PYTHON ", "Py Thon"]
        self.assertEqual({normalize_skill_key(value) for value in variants}, {"python"})

    def test_common_aliases_are_equivalent(self):
        self.assertEqual(normalize_skill_key("Power BI"), normalize_skill_key("powerbi"))
        self.assertEqual(normalize_skill_key("POWER BI Desktop"), normalize_skill_key("power bi"))
        self.assertEqual(normalize_skill_key("Amazon Web Services"), normalize_skill_key("AWS"))
        self.assertEqual(normalize_skill_key("scikit-learn"), normalize_skill_key("sklearn"))

    def test_multi_skill_matching_is_normalized(self):
        candidate = "python; sql; powerbi; amazon web services"
        required = " PYTHON,SQL, Power BI, AWS "
        self.assertTrue(contains_all_skills(candidate, required))
        self.assertTrue(_skill_filter_match(candidate, required))

    def test_project_scoring_accepts_mixed_case(self):
        employee = {
            "Parsed_Skills": ["python", "sql", "powerbi"],
            "Years_of_Experience": 4,
            "Skills": "python;sql;powerbi",
        }
        requirements = {
            "skills": ["PYTHON", " SQL ", "Power BI"],
            "min_experience": 2,
            "keywords": [],
        }
        score, breakdown = score_employee(employee, requirements)
        self.assertIsNotNone(score)
        self.assertEqual(breakdown["missing_skills"], [])

    def test_project_scoring_ranks_meaningful_partial_match(self):
        employee = {
            "Parsed_Skills": ["python", "sql"],
            "Years_of_Experience": 4,
            "Performance_Score": 5,
            "Skills": "python;sql",
        }
        requirements = {
            "skills": ["Python", "SQL", "Power BI"],
            "min_experience": 0,
            "keywords": [],
        }
        score, breakdown = score_employee(employee, requirements)
        self.assertIsNotNone(score)
        self.assertEqual(breakdown["skill_score"], 66.7)
        self.assertEqual(breakdown["missing_skills"], ["Power BI"])
        self.assertEqual([item["label"] for item in breakdown["score_factors"]], [
            "Skill coverage",
            "Experience fit",
            "Keyword relevance",
            "Performance",
        ])
        self.assertIn("2/3 required skills matched", breakdown["score_explanation"])

    def test_large_project_skill_list_recommends_partial_matches(self):
        employee = {
            "Parsed_Skills": ["Python", "SQL", "FastAPI", "Docker", "Git"],
            "Years_of_Experience": 4,
            "Performance_Score": 5,
            "Skills": "Python;SQL;FastAPI;Docker;Git",
        }
        requirements = {
            "skills": [
                "Data Preprocessing", "Docker", "FastAPI", "Feature Engineering", "Git",
                "Machine Learning", "MongoDB", "NumPy", "Pandas", "Power BI", "Python",
                "SQL", "Scikit-Learn", "TensorFlow", "Azure", "Data Science", "Model Training",
            ],
            "min_experience": 2,
            "keywords": [],
        }
        score, breakdown = score_employee(employee, requirements)
        self.assertIsNotNone(score)
        self.assertEqual(breakdown["skill_score"], 29.4)
        self.assertEqual(set(breakdown["matched_skills"]), {"Docker", "FastAPI", "Git", "Python", "SQL"})

    def test_project_document_nlp_extracts_ml_skill_stack(self):
        text = """Project skills:
        Python
        Machine Learning
        Pandas
        NumPy
        Scikit-learn
        SQL
        FastAPI
        Git
        Data Preprocessing
        Feature Engineering
        """
        parsed = _parse_document_requirements(text)
        self.assertEqual(
            set(parsed["skills"]),
            {
                "Python",
                "Machine Learning",
                "Pandas",
                "NumPy",
                "Scikit-Learn",
                "SQL",
                "FastAPI",
                "Git",
                "Data Preprocessing",
                "Feature Engineering",
            },
        )
        self.assertNotIn("C", parsed["skills"])
        self.assertNotIn("R", parsed["skills"])
        self.assertGreater(parsed["confidence"], 0)
        self.assertIn("Python", parsed["skill_confidences"])

    def test_project_document_ignores_season_spring(self):
        parsed = _parse_document_requirements("This SRS is based on Spring 2004 student submissions.")
        self.assertNotIn("Spring", parsed["skills"])

        parsed = _parse_document_requirements("Required skills: Java, Spring Boot, SQL")
        self.assertIn("Spring", parsed["skills"])

    def test_talent_search_is_case_and_spacing_insensitive(self):
        service = TalentBeaconService()
        service.df = pd.DataFrame([
            {
                "Employee_ID": 1,
                "Display_Employee_ID": 1,
                "Department": "IT",
                "Performance_Score": 5,
                "Years_of_Experience": 4,
                "Parsed_Skills": ["python", "powerbi"],
                "Skills": "python;powerbi",
            },
            {
                "Employee_ID": 2,
                "Display_Employee_ID": 2,
                "Department": "IT",
                "Performance_Score": 5,
                "Years_of_Experience": 4,
                "Parsed_Skills": ["Java"],
                "Skills": "Java",
            },
        ])
        results = service.search_employees(skill=" PYTHON, Power BI ")
        self.assertEqual([item["Employee_ID"] for item in results], [1])

        partial = service.search_employees(skill="Python, Power BI, SQL")
        self.assertEqual([item["Employee_ID"] for item in partial], [1])
        self.assertEqual(partial[0]["Skill_Match_Count"], 2)
        self.assertEqual(partial[0]["Missing_Skills"], ["sql"])

    def test_project_matching_exposes_score_breakdown_reason(self):
        service = TalentBeaconService()
        service.df = pd.DataFrame([
            {
                "Employee_ID": 1,
                "Display_Employee_ID": 1,
                "Department": "IT",
                "Job_Title": "Developer",
                "Performance_Score": 4,
                "Years_of_Experience": 3,
                "Parsed_Skills": ["Python", "SQL"],
                "Parsed_Certifications": [],
                "Skills": "Python;SQL",
            }
        ])
        service.engine = RecommendationEngine(service.df)
        results = service.match_employees_to_project(["Python", "SQL"], min_experience=2)
        self.assertEqual(len(results), 1)
        self.assertIn("score_breakdown", results[0])
        self.assertIn("reason", results[0]["score_breakdown"])

    def test_role_matching_exposes_score_breakdown_reason(self):
        service = TalentBeaconService()
        service.df = pd.DataFrame([
            {
                "Employee_ID": 1,
                "Display_Employee_ID": 1,
                "Department": "Analytics",
                "Job_Title": "Analyst",
                "Performance_Score": 5,
                "Years_of_Experience": 3,
                "Parsed_Skills": ["Python", "SQL", "Excel", "Power BI", "Statistics"],
                "Parsed_Certifications": [],
                "Skills": "Python;SQL;Excel;Power BI;Statistics",
            }
        ])
        service.engine = RecommendationEngine(service.df)
        results = service.match_employees_to_role("Data Analyst", limit=1)
        self.assertEqual(len(results), 1)
        self.assertIn("score_breakdown", results[0])
        self.assertIn("reason", results[0]["score_breakdown"])
        self.assertEqual(
            [item["label"] for item in results[0]["score_breakdown"]["parts"]],
            ["Skills", "Experience", "Performance", "Certifications"],
        )

    def test_visible_employee_id_is_used_before_internal_database_id(self):
        service = TalentBeaconService()
        service.df = pd.DataFrame([
            {
                "Employee_ID": 603,
                "Display_Employee_ID": 1535,
                "Department": "HR",
                "Job_Title": "Developer",
                "Education_Level": "Bachelor",
                "Performance_Score": 4,
                "Years_of_Experience": 5,
                "Projects_Handled": 2,
                "Employee_Satisfaction_Score": 4,
                "Parsed_Skills": ["Python", "SQL"],
                "Parsed_Certifications": [],
                "Skills": "Python;SQL",
            }
        ])
        row = service._find_employee_row(1535)
        self.assertFalse(row.empty)
        self.assertEqual(int(row.iloc[0]["Display_Employee_ID"]), 1535)
        self.assertEqual(int(row.iloc[0]["Employee_ID"]), 603)

    def test_hidden_database_id_is_not_treated_as_uploaded_employee_id(self):
        service = TalentBeaconService()
        service.df = pd.DataFrame([
            {
                "Employee_ID": 55,
                "Display_Employee_ID": 5,
                "Department": "Operations",
                "Job_Title": "Technician",
                "Education_Level": "Bachelor",
                "Performance_Score": 4,
                "Years_of_Experience": 9,
                "Parsed_Skills": ["AWS", "Docker"],
                "Parsed_Certifications": [],
                "Skills": "AWS;Docker",
            }
        ])
        self.assertTrue(service._find_employee_row(55).empty)
        row = service._find_employee_row(5)
        self.assertFalse(row.empty)
        self.assertEqual(int(row.iloc[0]["Display_Employee_ID"]), 5)

    def test_analytics_includes_distribution_rows(self):
        service = TalentBeaconService()
        service.df = pd.DataFrame([
            {
                "Employee_ID": 1,
                "Display_Employee_ID": 1,
                "Department": "Engineering",
                "Performance_Score": 5,
                "Years_of_Experience": 1,
                "Parsed_Skills": ["Python", "SQL"],
                "Skills": "Python;SQL",
            },
            {
                "Employee_ID": 2,
                "Display_Employee_ID": 2,
                "Department": "Analytics",
                "Performance_Score": 4,
                "Years_of_Experience": 6,
                "Parsed_Skills": ["Python"],
                "Skills": "Python",
            },
        ])
        analytics = service.get_analytics()
        self.assertEqual(analytics["total_employees"], 2)
        self.assertEqual(sum(row["count"] for row in analytics["department_rows"]), 2)
        self.assertEqual(sum(row["count"] for row in analytics["experience_rows"]), 2)
        self.assertEqual(analytics["top_skills"][0]["skill"], "Python")
        self.assertEqual(analytics["top_skills"][0]["count"], 2)

    def test_mysql_active_dataset_rows_match_service_dataframe_shape(self):
        rows = [{
            "id": 25,
            "employee_code": "dataset123:TB1002",
            "name": "Ananya Sharma",
            "email": "ananya.sharma@example.com",
            "department": "Engineering",
            "designation": "Data Scientist",
            "years_of_experience": 4,
            "education_level": "Bachelor",
            "performance_score": 5,
            "projects_handled": 3,
            "satisfaction_score": 4.5,
            "dataset_upload_id": 12,
            "dataset_filename": "employees.csv",
            "skills": "Python;SQL;Machine Learning",
            "certifications": "AWS Certified",
        }]
        original = config.MYSQL_READS_ENABLED
        config.MYSQL_READS_ENABLED = True
        try:
            with patch("src.db.repository.get_active_dataset_employees", return_value=rows):
                df = workspace_service._mysql_employee_df()
        finally:
            config.MYSQL_READS_ENABLED = original
        self.assertEqual(len(df), 1)
        self.assertEqual(df.iloc[0]["Employee_ID"], 25)
        self.assertEqual(df.iloc[0]["Display_Employee_ID"], 1002)
        self.assertEqual(df.iloc[0]["Parsed_Skills"], ["Python", "SQL", "Machine Learning"])
        self.assertEqual(df.iloc[0]["Source"], "mysql")

    def test_duplicate_employee_file_upload_is_blocked(self):
        csv_bytes = b"employee_id,skills,department\n1,Python,Engineering\n"
        with TemporaryDirectory() as tmpdir:
            original_state_path = workspace_service.STATE_PATH
            original_upload_dir = config.DATASET_UPLOAD_DIR
            original_mysql_reads = config.MYSQL_READS_ENABLED
            workspace_service.STATE_PATH = Path(tmpdir) / "state.json"
            config.DATASET_UPLOAD_DIR = Path(tmpdir) / "uploads"
            config.MYSQL_READS_ENABLED = False
            try:
                first = FileStorage(stream=BytesIO(csv_bytes), filename="employees.csv")
                process_dataset_upload(first, uploaded_by=100)

                second = FileStorage(stream=BytesIO(csv_bytes), filename="renamed.csv")
                with self.assertRaisesRegex(ValueError, "Duplicate file detected"):
                    process_dataset_upload(second, uploaded_by=100)
            finally:
                workspace_service.STATE_PATH = original_state_path
                config.DATASET_UPLOAD_DIR = original_upload_dir
                config.MYSQL_READS_ENABLED = original_mysql_reads

    def test_duplicate_project_document_upload_is_blocked(self):
        doc_bytes = b"Required skills: Python, SQL, FastAPI. Minimum experience 2 years."
        with TemporaryDirectory() as tmpdir:
            original_state_path = workspace_service.STATE_PATH
            original_project_dir = workspace_service.PROJECT_DOC_DIR
            workspace_service.STATE_PATH = Path(tmpdir) / "state.json"
            workspace_service.PROJECT_DOC_DIR = Path(tmpdir) / "project_docs"
            try:
                first = FileStorage(stream=BytesIO(doc_bytes), filename="project.txt")
                extracted = project_requirements_from_document(first, user_id=200)
                save_project_from_form({
                    "name": "Project",
                    "required_skills": "; ".join(extracted["skills"]),
                    "description": extracted["description"],
                    "min_experience": extracted["min_experience"],
                    "source_filename": extracted["source_filename"],
                    "source_path": extracted["source_path"],
                    "source_hash": extracted["source_hash"],
                }, created_by=200)

                second = FileStorage(stream=BytesIO(doc_bytes), filename="renamed.txt")
                with self.assertRaisesRegex(ValueError, "Duplicate project file detected"):
                    project_requirements_from_document(second, user_id=200)
            finally:
                workspace_service.STATE_PATH = original_state_path
                workspace_service.PROJECT_DOC_DIR = original_project_dir

    def test_skill_gap_is_normalized(self):
        gap = analyze_gap_from_skill_lists(
            ["python", "powerbi"],
            ["PYTHON", "Power BI"],
        )
        self.assertEqual(gap["match_percentage"], 100.0)
        self.assertEqual(gap["missing_skills"], [])

    def test_similarity_is_normalized(self):
        model = SkillSimilarityModel()
        employees = pd.Series(["python;powerbi", "Java"])
        scores = model.calculate_similarity(["PYTHON", "Power BI"], employees)
        self.assertAlmostEqual(float(scores[0]), 1.0, places=6)
        self.assertEqual(float(scores[1]), 0.0)


if __name__ == "__main__":
    unittest.main()
