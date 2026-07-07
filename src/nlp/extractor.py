import re
from collections import defaultdict

# Standard list of technical skills to seed matching if dataset is not loaded yet
DEFAULT_SKILL_VOCAB = [
    "Python", "SQL", "Git", "PostgreSQL", "JavaScript", "HTML", "CSS", "Bash", "Shell",
    "Node.js", "TypeScript", "Express", "React.js", "React", "Vue.js", "AWS", "C++", 
    "Java", "Perl", "Ruby", "Ruby on Rails", "Docker", "Kubernetes", "Angular", 
    "Heroku", "DynamoDB", "MySQL", "PHP", "jQuery", "Laravel", "Kotlin",
    "Swift", "Objective-C", "Android", "iOS", "Flutter", "React Native", "Machine Learning",
    "Deep Learning", "NLP", "Computer Vision", "TensorFlow", "PyTorch", "Scikit-Learn",
    "Pandas", "NumPy", "Power BI", "Tableau", "Excel", "Data Science", "C#", ".NET",
    "Scala", "Spark", "Hadoop", "MongoDB", "Redis", "Elasticsearch", "Jenkins",
    "Terraform", "Ansible", "GCP", "Google Cloud", "Azure", "Linux", "Unix",
    "FastAPI", "Flask", "Django", "Data Preprocessing", "Feature Engineering",
    "Data Cleaning", "Data Visualization", "Exploratory Data Analysis", "EDA",
    "Model Training", "Model Evaluation", "MLOps", "REST API", "API Development",
    "Statistics", "Matplotlib", "Seaborn", "Jupyter", "Anaconda"
]

SKILL_ALIASES = {
    "Amazon Web Services": "AWS",
    "aws cloud": "AWS",
    "Google Cloud Platform": "GCP",
    "google cloud platform": "GCP",
    "Microsoft Azure": "Azure",
    "js": "JavaScript",
    "node": "Node.js",
    "nodejs": "Node.js",
    "reactjs": "React.js",
    "vuejs": "Vue.js",
    "ts": "TypeScript",
    "postgres": "PostgreSQL",
    "mongo": "MongoDB",
    "elastic search": "Elasticsearch",
    "k8s": "Kubernetes",
    "kubernetes": "Kubernetes",
    "ci/cd": "Jenkins",
    "cicd": "Jenkins",
    "shell scripting": "Shell",
    "bash scripting": "Bash",
    "ml": "Machine Learning",
    "ai": "Machine Learning",
    "artificial intelligence": "Machine Learning",
    "natural language processing": "NLP",
    "large language models": "NLP",
    "llm": "NLP",
    "llms": "NLP",
    "sklearn": "Scikit-Learn",
    "scikit learn": "Scikit-Learn",
    "scikit": "Scikit-Learn",
    "powerbi": "Power BI",
    "fast api": "FastAPI",
    "fast-api": "FastAPI",
    "data prep": "Data Preprocessing",
    "preprocessing": "Data Preprocessing",
    "feature extraction": "Feature Engineering",
    "feature selection": "Feature Engineering",
    "exploratory data analysis": "Exploratory Data Analysis",
    "spring boot": "Spring",
    "spring framework": "Spring",
    "data viz": "Data Visualization",
    "visualisation": "Data Visualization",
    "r programming": "R",
    "c language": "C",
    "c programming": "C",
}


def _canonical_skill_map(skill_vocab):
    """Builds alias-to-canonical skill lookup from trained and default vocabularies."""
    canonical = {}
    for skill in list(DEFAULT_SKILL_VOCAB) + list(skill_vocab or []):
        if skill and str(skill).strip():
            skill_text = str(skill).strip()
            if len(skill_text) == 1:
                continue
            if skill_text.casefold() == "spring":
                continue
            canonical.setdefault(skill_text.lower(), skill_text)
    for alias, skill in SKILL_ALIASES.items():
        if skill.lower() in canonical:
            canonical[alias.lower()] = canonical[skill.lower()]
        else:
            canonical[alias.lower()] = skill
    return canonical


def _boundary_pattern(term):
    term_clean = term.strip().lower()
    escaped = re.escape(term_clean)
    has_special = any(char in term_clean for char in ['+', '#', '.', '-', '/'])
    if has_special:
        return rf'(?<![a-zA-Z0-9#+./-]){escaped}(?![a-zA-Z0-9#+./-])'
    return rf'\b{escaped}\b'


def clean_text_for_matching(text):
    """Normalizes document text for keyword extraction."""
    if not text:
        return ""
    # Convert to lowercase and strip excess spaces
    text = text.lower()
    # Replace newlines with spaces
    text = re.sub(r'\s+', ' ', text)
    return text

def extract_skills(text, skill_vocab=None):
    """
    Extracts known skills from the text based on a vocabulary.
    Handles aliases plus special characters like C++, C#, .NET using boundary-safe matching.
    """
    cleaned_text = clean_text_for_matching(text)
    extracted = {}
    match_counts = defaultdict(int)
    canonical_map = _canonical_skill_map(skill_vocab or DEFAULT_SKILL_VOCAB)

    # Match longer phrases first so "Ruby on Rails" wins before "Ruby".
    for term, canonical in sorted(canonical_map.items(), key=lambda item: len(item[0]), reverse=True):
        if not term:
            continue
        pattern = _boundary_pattern(term)
        if re.search(pattern, cleaned_text):
            extracted[canonical.lower()] = canonical
            match_counts[canonical] += len(re.findall(pattern, cleaned_text))
            cleaned_text = re.sub(pattern, ' [matched] ', cleaned_text)

    return sorted(extracted.values()), dict(match_counts)

def extract_experience(text):
    """
    Extracts the minimum years of experience requirement from project description text.
    """
    cleaned_text = clean_text_for_matching(text)
    
    # Pattern 1: Match ranges like "3-5 yrs" and use the lower bound as minimum.
    pattern_range = r'\b(\d+)\s*(?:-|to)\s*(\d+)\s*(?:years?|yrs?)\b'
    range_matches = re.findall(pattern_range, cleaned_text)
    if range_matches:
        return int(min(int(lo) for lo, _ in range_matches))

    # Pattern 2: Match patterns like "3+ years", "5 years of experience", "2+ yrs"
    pattern1 = r'\b(\d+)\+?\s*(?:years?|yrs?)\b'
    matches1 = re.findall(pattern1, cleaned_text)
    if matches1:
        return int(max([int(m) for m in matches1]))
        
    # Pattern 3: Match patterns like "experience: 3 years", "experience of 5 yrs"
    pattern2 = r'\b(?:experience|exp)\b.{0,30}?\b(\d+)\b'
    matches2 = re.findall(pattern2, cleaned_text)
    if matches2:
        return int(matches2[0])
        
    return 0 # Default to 0 if not found

def extract_certifications(text, known_certs=None):
    """
    Extracts certifications mentioned in the text.
    """
    cleaned_text = clean_text_for_matching(text)
    extracted = []
    
    # A few standard enterprise certifications
    default_certs = [
        "AWS Certified Solutions Architect", "AWS Certified Developer", "AWS Certified DevOps Engineer",
        "AWS Certified Cloud Practitioner", "AWS Certified Big Data", "AWS Certified Specialty",
        "Google Cloud Professional Cloud Architect", "Google Cloud Professional Data Engineer",
        "Google Cloud Professional Machine Learning Engineer", "Azure Solutions Architect",
        "Azure DevOps Engineer", "Azure Data Engineer", "Azure Administrator",
        "Cloudera Certified Professional", "Cloudera Certified Data Architect",
        "Hortonworks Certified Associate", "Red Hat Certified Engineer",
        "Red Hat Certified Specialist", "DevOps Institute", "Scrum Master", "PMP", "CISSP"
    ]
    
    certs_list = known_certs if known_certs else default_certs
    # Clean and sort
    sorted_certs = sorted(list(set(certs_list)), key=len, reverse=True)
    
    for cert in sorted_certs:
        cert_clean = cert.lower().strip()
        escaped_cert = re.escape(cert_clean)
        # Match with boundaries or partial substrings since certification names are long
        pattern = rf'\b{escaped_cert}\b'
        if re.search(pattern, cleaned_text, flags=re.IGNORECASE):
            extracted.append(cert)
        # Also check for acronyms, e.g. "CCP" or "PMP" or "AWS"
        elif len(cert) <= 5 and re.search(rf'\b{re.escape(cert)}\b', text, flags=re.IGNORECASE):
            extracted.append(cert)
            
    return sorted(list(set(extracted)))

def infer_domain(skills):
    """
    Infers the project domain from the extracted list of skills.
    """
    skills_lower = [s.lower() for s in skills]
    
    domain_scores = {
        "Data Science & Artificial Intelligence": 0,
        "Frontend & Mobile Development": 0,
        "Backend & Systems Development": 0,
        "Cloud Engineering & DevOps": 0,
        "Database Administration": 0
    }
    
    ds_skills = ['python', 'r', 'machine learning', 'deep learning', 'nlp', 'computer vision', 'tensorflow', 'pytorch', 'scikit-learn', 'pandas', 'numpy', 'power bi', 'tableau', 'excel', 'data science', 'spark', 'hadoop', 'scala', 'data preprocessing', 'feature engineering', 'data cleaning', 'data visualization', 'exploratory data analysis', 'eda', 'model training', 'model evaluation', 'statistics', 'matplotlib', 'seaborn', 'jupyter', 'anaconda']
    fe_skills = ['html', 'css', 'javascript', 'typescript', 'react', 'react.js', 'angular', 'vue.js', 'vue', 'jquery', 'bootstrap', 'flutter', 'react native', 'swift', 'objective-c', 'android', 'ios']
    be_skills = ['java', 'spring', 'c++', 'c', 'c#', '.net', 'ruby', 'ruby on rails', 'perl', 'php', 'laravel', 'kotlin', 'node.js', 'express', 'django', 'flask', 'fastapi', 'rest api', 'api development']
    cloud_skills = ['aws', 'gcp', 'google cloud', 'azure', 'docker', 'kubernetes', 'jenkins', 'terraform', 'ansible', 'devops', 'bash', 'shell', 'git', 'linux', 'unix', 'heroku']
    db_skills = ['sql', 'postgresql', 'mysql', 'mongodb', 'redis', 'elasticsearch', 'dynamodb', 'oracle', 'nosql']
    
    for skill in skills_lower:
        if skill in ds_skills:
            domain_scores["Data Science & Artificial Intelligence"] += 1
        if skill in fe_skills:
            domain_scores["Frontend & Mobile Development"] += 1
        if skill in be_skills:
            domain_scores["Backend & Systems Development"] += 1
        if skill in cloud_skills:
            domain_scores["Cloud Engineering & DevOps"] += 1
        if skill in db_skills:
            domain_scores["Database Administration"] += 1
            
    # Return the domain with the highest score, default if none scored
    max_score = max(domain_scores.values())
    if max_score == 0:
        return "General Software Engineering"
        
    best_domains = [domain for domain, score in domain_scores.items() if score == max_score]
    return best_domains[0]

def parse_project_requirements(text, skill_vocab=None, known_certs=None):
    """
    Main function to analyze project description and extract structured requirements.
    
    Args:
        text (str): Project description text.
        skill_vocab (list): List of skills in employee database.
        known_certs (list): List of certifications in employee database.
        
    Returns:
        dict: Parsed requirements.
    """
    skills, match_counts = extract_skills(text, skill_vocab)
    experience = extract_experience(text)
    certs = extract_certifications(text, known_certs)
    domain = infer_domain(skills)
    max_hits = max(match_counts.values() or [1])
    skill_confidences = {
        skill: round(min(0.99, 0.70 + (match_counts.get(skill, 1) / max_hits) * 0.25), 2)
        for skill in skills
    }
    confidence = round(
        (
            (0.45 if skills else 0)
            + (0.20 if experience else 0)
            + (0.15 if certs else 0)
            + (0.20 if domain != "General Software Engineering" else 0.10)
        ),
        2,
    )
    
    return {
        "skills": skills,
        "min_experience": experience,
        "certifications": certs,
        "domain": domain,
        "skill_match_counts": match_counts,
        "skill_confidences": skill_confidences,
        "confidence": min(confidence, 0.99),
    }

if __name__ == '__main__':
    # Test Parser
    test_text = "Looking for a Senior Data Scientist with 5+ years of experience. Must know Python, SQL, Machine Learning, and GCP. AWS certified solutions architect is a plus."
    res = parse_project_requirements(test_text)
    print("NLP Extraction Test:")
    print(f"Extracted Skills: {res['skills']}")
    print(f"Extracted Experience: {res['min_experience']} years")
    print(f"Extracted Certs: {res['certifications']}")
    print(f"Inferred Domain: {res['domain']}")
