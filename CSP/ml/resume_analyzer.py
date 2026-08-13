"""
Resume Analyzer Module
======================
Parses PDF and DOCX resumes using pdfplumber and python-docx.
Extracts skills, education, experience, projects, certifications.
Calculates a resume quality score out of 100 and provides
improvement suggestions.

Compatible with: routes/resume.py → analyze_resume(filepath)
"""

import os
import re

# ── PDF and DOCX parsing libraries ──
import pdfplumber
from docx import Document


# ──────────────────────────────────────────────
# TECHNICAL SKILLS KEYWORD DATABASE
# Used to identify skills mentioned in resumes
# ──────────────────────────────────────────────
KNOWN_SKILLS = [
    # Programming Languages
    'python', 'java', 'javascript', 'c++', 'c#', 'c', 'ruby', 'go', 'golang',
    'rust', 'swift', 'kotlin', 'typescript', 'php', 'r', 'scala', 'perl',
    'matlab', 'dart', 'solidity',

    # Web Technologies
    'html', 'html5', 'css', 'css3', 'sass', 'less', 'bootstrap', 'tailwind',
    'react', 'reactjs', 'react.js', 'angular', 'angularjs', 'vue', 'vuejs',
    'vue.js', 'next.js', 'nextjs', 'nuxt.js', 'svelte', 'jquery',
    'node.js', 'nodejs', 'express', 'express.js', 'django', 'flask',
    'fastapi', 'spring boot', 'spring', 'laravel', 'ruby on rails',

    # Databases
    'sql', 'mysql', 'postgresql', 'postgres', 'mongodb', 'redis', 'sqlite',
    'oracle', 'cassandra', 'dynamodb', 'firebase', 'supabase', 'neo4j',

    # Data Science / ML
    'machine learning', 'deep learning', 'artificial intelligence', 'ai',
    'data science', 'data analysis', 'data analytics', 'natural language processing',
    'nlp', 'computer vision', 'tensorflow', 'pytorch', 'keras', 'scikit-learn',
    'sklearn', 'pandas', 'numpy', 'scipy', 'matplotlib', 'seaborn',
    'tableau', 'power bi', 'excel', 'statistics', 'data visualization',
    'big data', 'hadoop', 'spark', 'apache spark', 'etl',

    # Cloud & DevOps
    'aws', 'amazon web services', 'azure', 'gcp', 'google cloud',
    'docker', 'kubernetes', 'k8s', 'jenkins', 'terraform', 'ansible',
    'ci/cd', 'cicd', 'devops', 'linux', 'unix', 'nginx', 'apache',
    'heroku', 'vercel', 'netlify', 'cloudflare',

    # Tools & Concepts
    'git', 'github', 'gitlab', 'bitbucket', 'jira', 'agile', 'scrum',
    'rest', 'rest api', 'restful', 'graphql', 'microservices',
    'data structures', 'algorithms', 'oop', 'object oriented programming',
    'design patterns', 'system design', 'unit testing', 'testing',
    'selenium', 'junit', 'maven', 'gradle',

    # Cybersecurity
    'cybersecurity', 'network security', 'ethical hacking', 'penetration testing',
    'cryptography', 'firewalls', 'siem', 'risk assessment',

    # Mobile
    'android', 'ios', 'flutter', 'react native', 'xamarin', 'swift ui',

    # Design
    'figma', 'adobe xd', 'sketch', 'photoshop', 'illustrator',
    'wireframing', 'prototyping', 'ui design', 'ux design', 'ui/ux',

    # Blockchain
    'blockchain', 'ethereum', 'smart contracts', 'web3', 'web3.js',
    'hyperledger', 'defi', 'nft',

    # Other
    'shell scripting', 'bash', 'powershell', 'api', 'json', 'xml',
    'websocket', 'rabbitmq', 'kafka', 'elasticsearch', 'monitoring',
    'mlops', 'model deployment'
]

# ── Section header patterns ──
# These regex patterns help identify sections in the resume text
SECTION_PATTERNS = {
    'education': r'(?i)(education|academic|qualification|degree|university|college|school|institute|b\.?tech|m\.?tech|b\.?e\b|m\.?e\b|b\.?sc|m\.?sc|b\.?ca|m\.?ca|bachelor|master|ph\.?d)',
    'experience': r'(?i)(experience|work\s*history|employment|professional\s*experience|work\s*experience|internship|intern|job|company|organization)',
    'projects': r'(?i)(project|academic\s*project|personal\s*project|mini\s*project|major\s*project|capstone)',
    'skills': r'(?i)(skill|technical\s*skill|programming|technology|tool|competenc|proficien|expertise|language)',
    'certifications': r'(?i)(certification|certificate|certified|credential|license|accreditation|course\s*completed|training)',
    'contact': r'(?i)(contact|email|phone|mobile|address|linkedin|github|portfolio|website)',
    'summary': r'(?i)(summary|objective|profile|about\s*me|career\s*objective|professional\s*summary)',
    'achievements': r'(?i)(achievement|award|honor|accomplishment|recognition|publication)'
}


# ══════════════════════════════════════════════
# TEXT EXTRACTION FUNCTIONS
# ══════════════════════════════════════════════

def extract_text_from_pdf(filepath):
    """
    Extract all text from a PDF file using pdfplumber.
    Handles multi-page PDFs by concatenating text from each page.
    """
    text = ""
    try:
        with pdfplumber.open(filepath) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
    except Exception as e:
        print(f"Error reading PDF: {e}")
    return text


def extract_text_from_docx(filepath):
    """
    Extract all text from a DOCX file using python-docx.
    Reads each paragraph from the document.
    """
    text = ""
    try:
        doc = Document(filepath)
        for paragraph in doc.paragraphs:
            if paragraph.text.strip():
                text += paragraph.text + "\n"
    except Exception as e:
        print(f"Error reading DOCX: {e}")
    return text


def extract_text(filepath):
    """
    Determine file type and extract text accordingly.
    Supports .pdf and .docx formats.
    """
    ext = os.path.splitext(filepath)[1].lower()
    if ext == '.pdf':
        return extract_text_from_pdf(filepath)
    elif ext == '.docx':
        return extract_text_from_docx(filepath)
    else:
        return ""


# ══════════════════════════════════════════════
# SECTION EXTRACTION FUNCTIONS
# ══════════════════════════════════════════════

def extract_skills(text):
    """
    Extract technical skills by matching against the known skills database.
    Uses word boundary matching to avoid partial matches.
    
    Returns a sorted list of unique skills found in the resume.
    """
    text_lower = text.lower()
    found_skills = set()

    for skill in KNOWN_SKILLS:
        # Use word boundary matching for precision
        # Handle skills with special characters (e.g., C++, Node.js)
        escaped_skill = re.escape(skill)
        pattern = r'(?<![a-zA-Z])' + escaped_skill + r'(?![a-zA-Z])'
        if re.search(pattern, text_lower):
            found_skills.add(skill.title())

    return sorted(found_skills)


def extract_section_content(text, section_name):
    """
    Extract content belonging to a specific section of the resume.
    
    Strategy: Find the section header, then collect lines until
    the next section header or end of text.
    """
    lines = text.split('\n')
    section_lines = []
    in_section = False
    pattern = SECTION_PATTERNS.get(section_name, '')

    if not pattern:
        return []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        # Check if this line is a section header
        is_header = bool(re.search(pattern, stripped)) and len(stripped) < 80

        # Check if this line starts a DIFFERENT section
        is_other_section = False
        if not is_header:
            for other_name, other_pattern in SECTION_PATTERNS.items():
                if other_name != section_name:
                    if re.search(other_pattern, stripped) and len(stripped) < 80:
                        is_other_section = True
                        break

        if is_header:
            in_section = True
            continue  # Skip the header line itself
        elif is_other_section and in_section:
            break  # End of our section, another section starts
        elif in_section:
            section_lines.append(stripped)

    return section_lines


def extract_education(text):
    """Extract education-related information from the resume."""
    lines = extract_section_content(text, 'education')
    education = []

    for line in lines:
        if len(line) > 10:  # Filter out very short / useless lines
            education.append(line)

    # Also try to find degree patterns anywhere in text
    degree_patterns = [
        r'(?i)(b\.?tech|b\.?e\.?|bachelor)[^.]*',
        r'(?i)(m\.?tech|m\.?e\.?|master|m\.?s\.?)[^.]*',
        r'(?i)(ph\.?d|doctorate)[^.]*',
        r'(?i)(b\.?sc|b\.?ca|m\.?sc|m\.?ca|bba|mba)[^.]*',
        r'(?i)(diploma|12th|10th|hsc|ssc|cbse|icse)[^.]*'
    ]

    if not education:
        for pattern in degree_patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                if isinstance(match, str) and len(match) > 5:
                    education.append(match.strip())

    return education[:10]  # Limit to 10 entries


def extract_experience(text):
    """Extract work experience information from the resume."""
    lines = extract_section_content(text, 'experience')
    experience = []

    for line in lines:
        if len(line) > 10:
            experience.append(line)

    return experience[:15]


def extract_projects(text):
    """Extract project information from the resume."""
    lines = extract_section_content(text, 'projects')
    projects = []

    for line in lines:
        if len(line) > 10:
            projects.append(line)

    return projects[:15]


def extract_certifications(text):
    """Extract certifications from the resume."""
    lines = extract_section_content(text, 'certifications')
    certifications = []

    # Also search for common certification patterns
    cert_patterns = [
        r'(?i)(certified|certificate|certification)\s+[^.]+',
        r'(?i)(aws|azure|google|oracle|cisco|comptia|pmp|scrum)[^.]*certif[^.]*',
        r'(?i)(nptel|coursera|udemy|edx)[^.]*'
    ]

    for line in lines:
        if len(line) > 5:
            certifications.append(line)

    # If no section found, try pattern matching
    if not certifications:
        for pattern in cert_patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                if isinstance(match, str) and len(match) > 5:
                    certifications.append(match.strip())

    return certifications[:10]


def extract_contact(text):
    """
    Extract contact information (email, phone, LinkedIn, GitHub).
    """
    contact = {}

    # Email
    email_match = re.search(r'[\w.+-]+@[\w-]+\.[\w.]+', text)
    if email_match:
        contact['email'] = email_match.group()

    # Phone
    phone_match = re.search(r'(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}', text)
    if phone_match:
        contact['phone'] = phone_match.group()

    # LinkedIn
    linkedin_match = re.search(r'linkedin\.com/in/[\w-]+', text, re.IGNORECASE)
    if linkedin_match:
        contact['linkedin'] = linkedin_match.group()

    # GitHub
    github_match = re.search(r'github\.com/[\w-]+', text, re.IGNORECASE)
    if github_match:
        contact['github'] = github_match.group()

    return contact


# ══════════════════════════════════════════════
# RESUME SCORING ENGINE
# ══════════════════════════════════════════════

def calculate_resume_score(extracted_data):
    """
    Calculate a resume quality score out of 100.
    
    Scoring Breakdown:
    ─────────────────────────────
    Skills section:          25 points
    Education section:       15 points
    Projects section:        20 points
    Experience section:      20 points
    Certifications:          10 points
    Contact information:      5 points
    Resume length/depth:      5 points
    ─────────────────────────────
    Total:                  100 points
    """
    score = 0
    breakdown = {}

    # ── Skills (25 points) ──
    num_skills = len(extracted_data.get('skills', []))
    if num_skills >= 10:
        skills_score = 25
    elif num_skills >= 7:
        skills_score = 20
    elif num_skills >= 4:
        skills_score = 15
    elif num_skills >= 1:
        skills_score = 8
    else:
        skills_score = 0
    score += skills_score
    breakdown['skills'] = skills_score

    # ── Education (15 points) ──
    num_edu = len(extracted_data.get('education', []))
    if num_edu >= 2:
        edu_score = 15
    elif num_edu >= 1:
        edu_score = 10
    else:
        edu_score = 0
    score += edu_score
    breakdown['education'] = edu_score

    # ── Projects (20 points) ──
    num_projects = len(extracted_data.get('projects', []))
    if num_projects >= 3:
        proj_score = 20
    elif num_projects >= 2:
        proj_score = 15
    elif num_projects >= 1:
        proj_score = 10
    else:
        proj_score = 0
    score += proj_score
    breakdown['projects'] = proj_score

    # ── Experience (20 points) ──
    num_exp = len(extracted_data.get('experience', []))
    if num_exp >= 3:
        exp_score = 20
    elif num_exp >= 2:
        exp_score = 15
    elif num_exp >= 1:
        exp_score = 10
    else:
        exp_score = 0
    score += exp_score
    breakdown['experience'] = exp_score

    # ── Certifications (10 points) ──
    num_certs = len(extracted_data.get('certifications', []))
    if num_certs >= 3:
        cert_score = 10
    elif num_certs >= 1:
        cert_score = 6
    else:
        cert_score = 0
    score += cert_score
    breakdown['certifications'] = cert_score

    # ── Contact Info (5 points) ──
    contact = extracted_data.get('contact', {})
    contact_items = len(contact)
    if contact_items >= 3:
        contact_score = 5
    elif contact_items >= 2:
        contact_score = 3
    elif contact_items >= 1:
        contact_score = 2
    else:
        contact_score = 0
    score += contact_score
    breakdown['contact'] = contact_score

    # ── Resume Depth (5 points) ──
    total_content = sum([num_skills, num_edu, num_projects, num_exp, num_certs])
    if total_content >= 15:
        depth_score = 5
    elif total_content >= 10:
        depth_score = 3
    elif total_content >= 5:
        depth_score = 2
    else:
        depth_score = 0
    score += depth_score
    breakdown['depth'] = depth_score

    return min(score, 100), breakdown


def generate_suggestions(extracted_data, score, breakdown):
    """
    Generate personalized improvement suggestions based on
    what's missing or weak in the resume.
    """
    suggestions = []

    # ── Missing sections ──
    if not extracted_data.get('skills'):
        suggestions.append({
            'type': 'critical',
            'message': 'Add a dedicated Technical Skills section listing your programming languages, frameworks, and tools.'
        })
    elif len(extracted_data.get('skills', [])) < 5:
        suggestions.append({
            'type': 'improvement',
            'message': f'You have only {len(extracted_data["skills"])} skills listed. Aim for at least 8-10 relevant technical skills.'
        })

    if not extracted_data.get('education'):
        suggestions.append({
            'type': 'critical',
            'message': 'Add your Education section with degree, university name, and graduation year.'
        })

    if not extracted_data.get('projects'):
        suggestions.append({
            'type': 'critical',
            'message': 'Add 2-3 academic or personal projects with descriptions showing technologies used.'
        })
    elif len(extracted_data.get('projects', [])) < 2:
        suggestions.append({
            'type': 'improvement',
            'message': 'Add more projects to showcase your practical experience. Aim for at least 2-3 projects.'
        })

    if not extracted_data.get('experience'):
        suggestions.append({
            'type': 'improvement',
            'message': 'Add internship or work experience. If none, add relevant volunteering, freelancing, or open-source contributions.'
        })

    if not extracted_data.get('certifications'):
        suggestions.append({
            'type': 'improvement',
            'message': 'Add relevant certifications from platforms like Coursera, NPTEL, or AWS to strengthen your profile.'
        })

    contact = extracted_data.get('contact', {})
    if 'email' not in contact:
        suggestions.append({
            'type': 'critical',
            'message': 'Include your email address in the resume for recruiters to contact you.'
        })
    if 'github' not in contact and 'linkedin' not in contact:
        suggestions.append({
            'type': 'improvement',
            'message': 'Add your LinkedIn profile and GitHub link to improve visibility.'
        })

    # ── General quality suggestions ──
    if score < 40:
        suggestions.append({
            'type': 'critical',
            'message': 'Your resume needs significant improvement. Focus on adding Skills, Projects, and Education sections.'
        })
    elif score < 60:
        suggestions.append({
            'type': 'improvement',
            'message': 'Your resume is decent but could be stronger. Add more projects and quantify your achievements.'
        })
    elif score < 80:
        suggestions.append({
            'type': 'good',
            'message': 'Good resume! Consider adding certifications and more detailed project descriptions to push above 80.'
        })
    else:
        suggestions.append({
            'type': 'excellent',
            'message': 'Excellent resume! Keep it updated with your latest projects and skills.'
        })

    return suggestions


def identify_missing_sections(extracted_data):
    """
    Return a list of resume sections that are empty or missing.
    """
    missing = []
    section_names = {
        'skills': 'Technical Skills',
        'education': 'Education',
        'experience': 'Work Experience / Internships',
        'projects': 'Projects',
        'certifications': 'Certifications'
    }

    for key, display_name in section_names.items():
        if not extracted_data.get(key):
            missing.append(display_name)

    contact = extracted_data.get('contact', {})
    if not contact.get('email'):
        missing.append('Email Address')
    if not contact.get('linkedin') and not contact.get('github'):
        missing.append('LinkedIn / GitHub Profile')

    return missing


# ══════════════════════════════════════════════
# MAIN ANALYSIS FUNCTION
# ══════════════════════════════════════════════

def analyze_resume(filepath):
    """
    Main entry point for resume analysis.
    
    Called by: routes/resume.py → upload()
    
    Args:
        filepath: Absolute path to the uploaded PDF or DOCX file
    
    Returns:
        dict with keys:
        - skills: list of extracted skills
        - education: list of education entries
        - experience: list of experience entries
        - projects: list of project entries
        - certifications: list of certification entries
        - contact: dict with email, phone, linkedin, github
        - resume_score: int score out of 100
        - analysis: dict with breakdown, suggestions, missing_sections, 
                     weak_areas, and overall_rating
    """
    # Step 1: Extract raw text from the file
    text = extract_text(filepath)

    if not text.strip():
        return {
            'skills': [],
            'education': [],
            'experience': [],
            'projects': [],
            'certifications': [],
            'contact': {},
            'resume_score': 0,
            'analysis': {
                'breakdown': {},
                'suggestions': [{
                    'type': 'critical',
                    'message': 'Could not extract text from the resume. Please ensure the file is not image-based or corrupted.'
                }],
                'missing_sections': ['All sections'],
                'weak_areas': ['Unable to parse resume'],
                'overall_rating': 'Poor'
            }
        }

    # Step 2: Extract individual sections
    skills = extract_skills(text)
    education = extract_education(text)
    experience = extract_experience(text)
    projects = extract_projects(text)
    certifications = extract_certifications(text)
    contact = extract_contact(text)

    extracted_data = {
        'skills': skills,
        'education': education,
        'experience': experience,
        'projects': projects,
        'certifications': certifications,
        'contact': contact
    }

    # Step 3: Calculate resume score
    resume_score, breakdown = calculate_resume_score(extracted_data)

    # Step 4: Generate improvement suggestions
    suggestions = generate_suggestions(extracted_data, resume_score, breakdown)

    # Step 5: Identify missing and weak sections
    missing_sections = identify_missing_sections(extracted_data)

    weak_areas = []
    for section, points in breakdown.items():
        max_points = {'skills': 25, 'education': 15, 'projects': 20,
                      'experience': 20, 'certifications': 10, 'contact': 5, 'depth': 5}
        if section in max_points and points < max_points[section] * 0.5:
            weak_areas.append(section.replace('_', ' ').title())

    # Step 6: Determine overall rating
    if resume_score >= 80:
        overall_rating = 'Excellent'
    elif resume_score >= 60:
        overall_rating = 'Good'
    elif resume_score >= 40:
        overall_rating = 'Average'
    elif resume_score >= 20:
        overall_rating = 'Below Average'
    else:
        overall_rating = 'Poor'

    # Step 7: Return the complete analysis result
    return {
        'skills': skills,
        'education': education,
        'experience': experience,
        'projects': projects,
        'certifications': certifications,
        'contact': contact,
        'resume_score': resume_score,
        'analysis': {
            'breakdown': breakdown,
            'suggestions': suggestions,
            'missing_sections': missing_sections,
            'weak_areas': weak_areas,
            'overall_rating': overall_rating,
            'total_skills_found': len(skills),
            'total_sections_filled': 5 - len(missing_sections)
        }
    }
