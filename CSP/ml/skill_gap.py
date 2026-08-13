"""
Skill Gap Analysis Module
=========================
Compares student skills with required skills for recommended
career roles. Categorizes skills by proficiency level and
generates learning priorities.
"""

import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.db import get_db


# ── Skill difficulty categorization ──
SKILL_LEVELS = {
    'beginner': [
        'html', 'css', 'git', 'excel', 'sql', 'python', 'java', 'javascript',
        'responsive design', 'bootstrap', 'wireframing', 'linux', 'shell scripting',
        'sqlite', 'firebase'
    ],
    'intermediate': [
        'react', 'node.js', 'django', 'flask', 'spring boot', 'rest apis',
        'data structures', 'algorithms', 'oop', 'docker', 'mongodb', 'mysql',
        'postgresql', 'pandas', 'numpy', 'statistics', 'data visualization',
        'tableau', 'power bi', 'unit testing', 'junit', 'maven', 'hibernate',
        'typescript', 'sass', 'ci/cd', 'jenkins', 'networking', 'figma',
        'adobe xd', 'sketch', 'prototyping', 'user research', 'usability testing',
        'kotlin', 'swift', 'flutter', 'react native', 'fastapi', 'etl',
        'cryptography', 'firewalls', 'risk assessment', 'compliance',
        'ansible', 'terraform', 'monitoring', 'microservices'
    ],
    'advanced': [
        'machine learning', 'deep learning', 'tensorflow', 'pytorch',
        'scikit-learn', 'nlp', 'computer vision', 'mlops', 'kubernetes',
        'design patterns', 'system design', 'penetration testing',
        'ethical hacking', 'siem', 'aws', 'azure', 'gcp', 'hyperledger',
        'solidity', 'smart contracts', 'web3.js', 'performance tuning',
        'backup recovery', 'database design', 'oracle'
    ]
}


def categorize_skill(skill):
    """Determine the difficulty level of a skill."""
    skill_lower = skill.strip().lower()
    for level, skills in SKILL_LEVELS.items():
        if skill_lower in skills:
            return level
    return 'intermediate'  # Default to intermediate if unknown


def analyze_skill_gap(user_skills_str, career_role):
    """
    Analyze the skill gap between a student and a career role.
    
    Args:
        user_skills_str: comma-separated string of user skills
        career_role: name of the career role to analyze against
    
    Returns:
        dict with skill gap analysis results
    """
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM career_roles WHERE role_name = %s", (career_role,))
    role = cursor.fetchone()
    conn.close()

    if not role:
        return None

    role = dict(role)

    # Parse skill sets
    user_skills = set(s.strip().lower() for s in user_skills_str.split(',') if s.strip())
    required_tech = set(s.strip().lower() for s in (role.get('required_technical_skills', '') or '').split(',') if s.strip())
    required_soft = set(s.strip().lower() for s in (role.get('required_soft_skills', '') or '').split(',') if s.strip())
    all_required = required_tech.union(required_soft)

    # ── Analysis ──
    existing_skills = user_skills.intersection(all_required)
    missing_skills = all_required - user_skills
    extra_skills = user_skills - all_required  # Skills student has beyond requirements

    # Calculate match percentage
    match_percentage = round((len(existing_skills) / len(all_required)) * 100, 1) if all_required else 0

    # Categorize missing skills by difficulty level
    missing_categorized = {
        'beginner': [],
        'intermediate': [],
        'advanced': []
    }
    for skill in missing_skills:
        level = categorize_skill(skill)
        missing_categorized[level].append(skill.title())

    # Determine priority skills to learn (beginner first, then intermediate)
    priority_skills = missing_categorized['beginner'] + missing_categorized['intermediate'][:5]

    # Categorize existing skills by level
    existing_categorized = {
        'beginner': [],
        'intermediate': [],
        'advanced': []
    }
    for skill in existing_skills:
        level = categorize_skill(skill)
        existing_categorized[level].append(skill.title())

    return {
        'career_role': career_role,
        'total_required': len(all_required),
        'existing_skills': [s.title() for s in sorted(existing_skills)],
        'missing_skills': [s.title() for s in sorted(missing_skills)],
        'extra_skills': [s.title() for s in sorted(extra_skills)],
        'match_percentage': match_percentage,
        'missing_categorized': missing_categorized,
        'existing_categorized': existing_categorized,
        'priority_skills': priority_skills[:8],  # Top 8 priority skills
        'role_description': role.get('description', '')
    }


def get_course_recommendations(missing_skills, career_role=None):
    """
    Get course recommendations for missing skills.
    
    Args:
        missing_skills: list of skills to find courses for
        career_role: optional career role to filter courses
    
    Returns:
        list of course recommendation dicts
    """
    conn = get_db()
    cursor = conn.cursor()

    courses = []
    for skill in missing_skills:
        skill_clean = skill.strip().lower()
        cursor.execute(
            "SELECT * FROM courses WHERE LOWER(skill) = %s ORDER BY difficulty",
            (skill_clean,)
        )
        skill_courses = cursor.fetchall()

        for course in skill_courses:
            courses.append({
                'skill': skill,
                'course_name': course['course_name'],
                'platform': course['platform'],
                'free_paid': course['free_paid'],
                'difficulty': course['difficulty'],
                'link': course['link']
            })

    conn.close()
    return courses


def generate_roadmap(career_role):
    """
    Generate a structured learning roadmap for a given career role.
    
    Returns a roadmap with beginner, intermediate, and advanced stages
    along with project suggestions and certification recommendations.
    """
    # ── Predefined roadmaps for each career ──
    roadmaps = {
        'Machine Learning Engineer': {
            'beginner': {
                'duration': '1-2 months',
                'skills': ['Python Programming', 'Mathematics (Linear Algebra, Calculus)', 'NumPy & Pandas', 'Data Visualization (Matplotlib)'],
                'projects': ['Data Analysis with Pandas', 'Statistical Analysis Project']
            },
            'intermediate': {
                'duration': '2-3 months',
                'skills': ['Machine Learning Algorithms', 'Scikit-learn', 'Data Preprocessing', 'Feature Engineering', 'Model Evaluation'],
                'projects': ['House Price Prediction', 'Customer Churn Analysis', 'Spam Email Classifier']
            },
            'advanced': {
                'duration': '2-3 months',
                'skills': ['Deep Learning (TensorFlow/PyTorch)', 'NLP', 'Computer Vision', 'Model Deployment', 'MLOps Basics'],
                'projects': ['Image Classification App', 'Chatbot with NLP', 'End-to-end ML Pipeline']
            },
            'certifications': ['TensorFlow Developer Certificate', 'AWS ML Specialty', 'Google ML Engineer'],
            'timeline': '6 months'
        },
        'Data Scientist': {
            'beginner': {
                'duration': '1-2 months',
                'skills': ['Python', 'Statistics & Probability', 'SQL', 'Data Manipulation (Pandas)', 'Data Visualization'],
                'projects': ['Exploratory Data Analysis', 'SQL Data Report']
            },
            'intermediate': {
                'duration': '2-3 months',
                'skills': ['Machine Learning', 'Scikit-learn', 'Feature Engineering', 'A/B Testing', 'Statistical Modeling'],
                'projects': ['Predictive Analytics Dashboard', 'Customer Segmentation', 'Recommendation System']
            },
            'advanced': {
                'duration': '2-3 months',
                'skills': ['Deep Learning', 'NLP', 'Big Data Tools', 'Model Deployment', 'Research Methods'],
                'projects': ['Sentiment Analysis Engine', 'Time Series Forecasting', 'End-to-end Data Pipeline']
            },
            'certifications': ['IBM Data Science Professional', 'Google Data Analytics', 'AWS Data Analytics'],
            'timeline': '6 months'
        },
        'Software Developer': {
            'beginner': {
                'duration': '1-2 months',
                'skills': ['Programming Fundamentals (Python/Java)', 'Data Structures', 'Git & Version Control', 'Basic SQL'],
                'projects': ['Console-based Application', 'Simple CRUD App']
            },
            'intermediate': {
                'duration': '2-3 months',
                'skills': ['Algorithms', 'OOP & Design Patterns', 'REST APIs', 'Database Design', 'Unit Testing'],
                'projects': ['RESTful API Service', 'Library Management System', 'Blog Platform']
            },
            'advanced': {
                'duration': '2-3 months',
                'skills': ['System Design', 'Microservices', 'Docker', 'CI/CD', 'Cloud Deployment'],
                'projects': ['Microservice Architecture App', 'Open Source Contribution', 'Full Production App']
            },
            'certifications': ['AWS Developer Associate', 'Oracle Java Certification', 'Microsoft Azure Developer'],
            'timeline': '6 months'
        },
        'Web Developer': {
            'beginner': {
                'duration': '1-2 months',
                'skills': ['HTML5 & Semantic HTML', 'CSS3 & Flexbox/Grid', 'JavaScript Basics', 'Responsive Design', 'Git'],
                'projects': ['Personal Portfolio Website', 'Landing Page Clone']
            },
            'intermediate': {
                'duration': '2-3 months',
                'skills': ['React/Vue.js', 'Node.js & Express', 'REST APIs', 'Database Integration', 'Authentication'],
                'projects': ['E-commerce Frontend', 'Weather App with API', 'Blog with CMS']
            },
            'advanced': {
                'duration': '2-3 months',
                'skills': ['TypeScript', 'Testing Frameworks', 'Performance Optimization', 'SEO', 'Deployment'],
                'projects': ['Full Stack SaaS App', 'Progressive Web App', 'Open Source UI Library']
            },
            'certifications': ['Meta Front-End Developer', 'freeCodeCamp Certification', 'Google Mobile Web Specialist'],
            'timeline': '6 months'
        },
        'Full Stack Developer': {
            'beginner': {
                'duration': '1-2 months',
                'skills': ['HTML, CSS, JavaScript', 'Git & GitHub', 'Basic SQL', 'Command Line Basics', 'REST Concepts'],
                'projects': ['Static Portfolio Site', 'Simple To-Do App']
            },
            'intermediate': {
                'duration': '2-3 months',
                'skills': ['React', 'Node.js & Express', 'MongoDB/PostgreSQL', 'Authentication (JWT)', 'API Development'],
                'projects': ['Task Management App', 'Social Media Clone', 'Real-time Chat App']
            },
            'advanced': {
                'duration': '2-3 months',
                'skills': ['TypeScript', 'Docker', 'CI/CD', 'Cloud Deployment (AWS/GCP)', 'System Design'],
                'projects': ['Full SaaS Platform', 'Microservice E-commerce', 'DevOps Pipeline Setup']
            },
            'certifications': ['Meta Full-Stack Engineer', 'AWS Developer Associate', 'MongoDB Developer'],
            'timeline': '6 months'
        },
        'Data Analyst': {
            'beginner': {
                'duration': '1-2 months',
                'skills': ['Excel Advanced', 'SQL Fundamentals', 'Basic Python', 'Statistics Basics', 'Data Cleaning'],
                'projects': ['Sales Data Analysis in Excel', 'SQL Query Practice']
            },
            'intermediate': {
                'duration': '2-3 months',
                'skills': ['Python (Pandas, NumPy)', 'Data Visualization (Tableau/Power BI)', 'Statistical Analysis', 'ETL Processes'],
                'projects': ['Dashboard Creation', 'Market Research Analysis', 'Survey Data Report']
            },
            'advanced': {
                'duration': '1-2 months',
                'skills': ['Advanced SQL', 'Machine Learning Basics', 'A/B Testing', 'Business Intelligence Tools'],
                'projects': ['Predictive Dashboard', 'Automated Reporting System', 'Business Case Analysis']
            },
            'certifications': ['Google Data Analytics', 'Microsoft Power BI', 'Tableau Desktop Specialist'],
            'timeline': '3-6 months'
        },
        'Java Developer': {
            'beginner': {
                'duration': '1-2 months',
                'skills': ['Java Fundamentals', 'OOP Concepts', 'Data Structures in Java', 'Git', 'Basic SQL'],
                'projects': ['Console Banking App', 'Student Management System']
            },
            'intermediate': {
                'duration': '2-3 months',
                'skills': ['Spring Boot', 'Hibernate/JPA', 'REST APIs', 'Maven/Gradle', 'JUnit Testing'],
                'projects': ['REST API with Spring Boot', 'E-commerce Backend', 'Blog Platform API']
            },
            'advanced': {
                'duration': '2-3 months',
                'skills': ['Microservices', 'Docker', 'Kubernetes', 'Message Queues', 'System Design'],
                'projects': ['Microservice Architecture', 'Cloud-deployed App', 'Enterprise Integration']
            },
            'certifications': ['Oracle Java SE Certification', 'Spring Professional', 'AWS Developer'],
            'timeline': '6 months'
        },
        'Python Developer': {
            'beginner': {
                'duration': '1-2 months',
                'skills': ['Python Fundamentals', 'Data Structures', 'File Handling', 'Git', 'SQL Basics'],
                'projects': ['Automation Scripts', 'CLI Tool']
            },
            'intermediate': {
                'duration': '2-3 months',
                'skills': ['Django/Flask', 'REST APIs', 'Database Design', 'Testing', 'Docker Basics'],
                'projects': ['Web Application with Django', 'API Service', 'Task Automation Suite']
            },
            'advanced': {
                'duration': '2-3 months',
                'skills': ['FastAPI', 'Async Programming', 'System Design', 'CI/CD', 'Cloud Deployment'],
                'projects': ['Production API Service', 'Microservice App', 'Open Source Package']
            },
            'certifications': ['PCEP/PCAP Python', 'Django Developer', 'AWS Developer'],
            'timeline': '6 months'
        },
        'Cybersecurity Analyst': {
            'beginner': {
                'duration': '1-2 months',
                'skills': ['Networking Fundamentals', 'Linux Basics', 'Cybersecurity Concepts', 'Python Scripting'],
                'projects': ['Network Scanner Script', 'Security Audit Checklist']
            },
            'intermediate': {
                'duration': '2-3 months',
                'skills': ['Ethical Hacking', 'SIEM Tools', 'Firewalls & IDS', 'Cryptography', 'Risk Assessment'],
                'projects': ['Vulnerability Assessment', 'SIEM Dashboard Setup', 'Penetration Testing Report']
            },
            'advanced': {
                'duration': '2-3 months',
                'skills': ['Advanced Penetration Testing', 'Incident Response', 'Compliance (ISO 27001)', 'Threat Intelligence'],
                'projects': ['Security Operations Center Setup', 'Red Team Exercise', 'Security Framework Implementation']
            },
            'certifications': ['CompTIA Security+', 'CEH (Certified Ethical Hacker)', 'OSCP'],
            'timeline': '6 months'
        },
        'Cloud Engineer': {
            'beginner': {
                'duration': '1-2 months',
                'skills': ['Linux Fundamentals', 'Networking Basics', 'Cloud Concepts (AWS/Azure/GCP)', 'Python/Bash Scripting'],
                'projects': ['Deploy a Static Website on Cloud', 'Basic Cloud Infrastructure']
            },
            'intermediate': {
                'duration': '2-3 months',
                'skills': ['Docker', 'Terraform', 'CI/CD Pipelines', 'Cloud Networking', 'IAM & Security'],
                'projects': ['Containerized Application Deployment', 'Infrastructure as Code Project', 'Multi-tier Cloud Architecture']
            },
            'advanced': {
                'duration': '2-3 months',
                'skills': ['Kubernetes', 'Serverless Architecture', 'Cost Optimization', 'Multi-cloud Strategy', 'Monitoring'],
                'projects': ['Kubernetes Cluster Management', 'Serverless Application', 'Cloud Migration Project']
            },
            'certifications': ['AWS Solutions Architect', 'Azure Administrator', 'GCP Cloud Engineer'],
            'timeline': '6 months'
        },
        'UI/UX Designer': {
            'beginner': {
                'duration': '1-2 months',
                'skills': ['Design Principles', 'Figma Basics', 'Color Theory & Typography', 'Wireframing', 'HTML/CSS Basics'],
                'projects': ['Mobile App Wireframes', 'Portfolio Website Mockup']
            },
            'intermediate': {
                'duration': '2-3 months',
                'skills': ['Prototyping', 'User Research', 'Usability Testing', 'Design Systems', 'Interaction Design'],
                'projects': ['Complete App Redesign', 'User Research Case Study', 'Design System Creation']
            },
            'advanced': {
                'duration': '2-3 months',
                'skills': ['Advanced Prototyping', 'Accessibility (a11y)', 'Motion Design', 'Frontend Implementation'],
                'projects': ['End-to-end Product Design', 'Accessibility Audit', 'Design for Large Scale Product']
            },
            'certifications': ['Google UX Design Certificate', 'Interaction Design Foundation', 'Adobe Certified Expert'],
            'timeline': '6 months'
        },
        'DevOps Engineer': {
            'beginner': {
                'duration': '1-2 months',
                'skills': ['Linux Administration', 'Git & GitHub', 'Python/Bash Scripting', 'Networking Basics'],
                'projects': ['Automated Backup Script', 'Git Workflow Setup']
            },
            'intermediate': {
                'duration': '2-3 months',
                'skills': ['Docker', 'Jenkins/GitHub Actions', 'CI/CD Pipelines', 'Terraform', 'AWS Basics'],
                'projects': ['CI/CD Pipeline for Web App', 'Docker Compose Multi-container', 'Infrastructure Provisioning']
            },
            'advanced': {
                'duration': '2-3 months',
                'skills': ['Kubernetes', 'Monitoring (Prometheus/Grafana)', 'Service Mesh', 'GitOps', 'Security in DevOps'],
                'projects': ['Kubernetes Production Setup', 'Full GitOps Pipeline', 'Monitoring Dashboard']
            },
            'certifications': ['AWS DevOps Engineer', 'CKA (Kubernetes)', 'Docker Certified Associate'],
            'timeline': '6 months'
        },
        'Mobile App Developer': {
            'beginner': {
                'duration': '1-2 months',
                'skills': ['Java/Kotlin or Swift', 'Mobile UI Basics', 'Git', 'REST API Concepts'],
                'projects': ['Calculator App', 'Notes App']
            },
            'intermediate': {
                'duration': '2-3 months',
                'skills': ['Flutter/React Native', 'State Management', 'Firebase', 'API Integration', 'Local Storage'],
                'projects': ['Weather App', 'Chat Application', 'E-commerce App']
            },
            'advanced': {
                'duration': '2-3 months',
                'skills': ['Advanced Animations', 'Push Notifications', 'App Performance', 'CI/CD for Mobile', 'App Store Deployment'],
                'projects': ['Social Media App', 'Real-time Tracking App', 'Published App on Store']
            },
            'certifications': ['Google Associate Android Developer', 'Meta React Native', 'Apple Developer'],
            'timeline': '6 months'
        },
        'Database Administrator': {
            'beginner': {
                'duration': '1-2 months',
                'skills': ['SQL Fundamentals', 'Database Concepts', 'MySQL/PostgreSQL Setup', 'Basic Linux'],
                'projects': ['Database Design for E-commerce', 'SQL Query Optimization']
            },
            'intermediate': {
                'duration': '2-3 months',
                'skills': ['Advanced SQL', 'Database Design & Normalization', 'Backup & Recovery', 'Performance Tuning', 'MongoDB'],
                'projects': ['Multi-database Integration', 'Automated Backup System', 'Query Performance Report']
            },
            'advanced': {
                'duration': '2-3 months',
                'skills': ['Oracle/Enterprise DB', 'High Availability', 'Replication', 'Cloud Databases', 'Security & Compliance'],
                'projects': ['Database Migration Project', 'HA Cluster Setup', 'Enterprise DB Management']
            },
            'certifications': ['Oracle DBA Certification', 'Microsoft Azure Database', 'MongoDB DBA'],
            'timeline': '6 months'
        },
        'Blockchain Developer': {
            'beginner': {
                'duration': '1-2 months',
                'skills': ['Blockchain Concepts', 'Cryptography Basics', 'JavaScript/Python', 'Git'],
                'projects': ['Simple Blockchain Implementation', 'Crypto Wallet Tracker']
            },
            'intermediate': {
                'duration': '2-3 months',
                'skills': ['Solidity', 'Ethereum Development', 'Smart Contracts', 'Web3.js', 'Truffle/Hardhat'],
                'projects': ['ERC-20 Token', 'Decentralized Voting App', 'NFT Marketplace']
            },
            'advanced': {
                'duration': '2-3 months',
                'skills': ['DeFi Protocols', 'Hyperledger', 'Layer 2 Solutions', 'Smart Contract Security', 'dApp Architecture'],
                'projects': ['DeFi Application', 'Enterprise Blockchain Solution', 'Cross-chain Bridge']
            },
            'certifications': ['Certified Blockchain Developer', 'Ethereum Developer Certification', 'Hyperledger Fabric'],
            'timeline': '6 months'
        },
        'Accountant': {
            'beginner': {'duration': '2-3 months', 'skills': ['Financial Accounting basics', 'Bookkeeping principles', 'MS Excel', 'Tally/QuickBooks', 'Tax fundamentals (GST, Income Tax)'], 'projects': ['Prepare a trial balance', 'Create financial statements in Excel']},
            'intermediate': {'duration': '3-4 months', 'skills': ['Advanced Tally/ERP', 'SAP FICO basics', 'Auditing principles', 'Financial reporting standards (GAAP/IFRS)', 'Cost accounting'], 'projects': ['Audit simulation project', 'SAP FICO case study']},
            'advanced': {'duration': '3-4 months', 'skills': ['Advanced SAP FICO', 'Consolidated financial statements', 'Tax planning & compliance', 'Financial analysis & forecasting', 'ERP implementation'], 'projects': ['End-to-end accounting system', 'Tax filing automation project']},
            'certifications': ['Tally Certified Professional', 'SAP FICO Certification', 'CA Intermediate', 'CMA', 'CPA (US)'],
            'timeline': '10 months'
        },
        'Financial Analyst': {
            'beginner': {'duration': '2-3 months', 'skills': ['MS Excel (advanced)', 'Financial statements analysis', 'Basic accounting', 'Financial modeling fundamentals', 'PowerPoint for presentations'], 'projects': ['Company financial health report', 'Excel financial model for a startup']},
            'intermediate': {'duration': '3-4 months', 'skills': ['Financial modeling & valuation', 'DCF & comparable analysis', 'Investment analysis', 'Risk management', 'SQL for finance', 'Tableau/Power BI'], 'projects': ['Full company valuation model', 'Investment thesis presentation']},
            'advanced': {'duration': '3-4 months', 'skills': ['Advanced financial modeling', 'M&A modeling', 'Portfolio management', 'Derivatives & hedging', 'Python for finance', 'Quantitative analysis'], 'projects': ['Merger model from scratch', 'Algorithmic trading strategy backtest']},
            'certifications': ['CFA Level 1', 'Financial Modeling Certification (FMVA)', 'NISM Series', 'FRM'],
            'timeline': '10 months'
        },
        'Business Analyst': {
            'beginner': {'duration': '2-3 months', 'skills': ['MS Excel', 'SQL basics', 'Business process mapping', 'Requirements gathering', 'Documentation (BRD/FRD)', 'JIRA basics'], 'projects': ['Process flow diagram project', 'Requirements specification document']},
            'intermediate': {'duration': '3-4 months', 'skills': ['Advanced SQL', 'Data analysis with Python/Pandas', 'Power BI/Tableau', 'Agile & Scrum methodologies', 'Stakeholder management', 'UML diagrams'], 'projects': ['Data analysis dashboard', 'Product requirement document for an app']},
            'advanced': {'duration': '3-4 months', 'skills': ['Advanced analytics & forecasting', 'Business intelligence tools', 'Data warehousing concepts', 'Project management', 'Consulting frameworks', 'Python automation'], 'projects': ['End-to-end business intelligence solution', 'Process automation case study']},
            'certifications': ['CBAP (IIBA)', 'PMP', 'Google Data Analytics', 'AWS Cloud Practitioner'],
            'timeline': '10 months'
        },
        'Marketing Manager': {
            'beginner': {'duration': '2-3 months', 'skills': ['Marketing fundamentals', 'Digital marketing basics', 'Content creation', 'Social media platforms', 'MS Excel', 'Google Analytics'], 'projects': ['Social media campaign plan', 'Content calendar creation']},
            'intermediate': {'duration': '3-4 months', 'skills': ['SEO/SEM strategies', 'Google Ads & Facebook Ads', 'Email marketing tools', 'CRM (HubSpot/Salesforce)', 'Brand management', 'Market research'], 'projects': ['Full marketing campaign', 'Brand strategy document']},
            'advanced': {'duration': '3-4 months', 'skills': ['Marketing analytics & ROI modeling', 'Growth hacking strategies', 'Product marketing', 'Budget management', 'Team leadership', 'Data-driven decision making'], 'projects': ['Revenue growth strategy', 'Marketing automation funnel']},
            'certifications': ['Google Digital Marketing Certificate', 'HubSpot Academy Certifications', 'Facebook Blueprint', 'Google Analytics Individual Qualification'],
            'timeline': '10 months'
        },
        'Human Resources Manager': {
            'beginner': {'duration': '2-3 months', 'skills': ['HR fundamentals & policies', 'Recruitment & onboarding', 'MS Excel', 'Payroll basics', 'Employment law essentials'], 'projects': ['Recruitment process flowchart', 'Employee handbook draft']},
            'intermediate': {'duration': '3-4 months', 'skills': ['HRMS tools (Keka/Zoho/ZingHR)', 'Performance management', 'Training & development', 'Compensation & benefits', 'HR analytics', 'Advanced labor laws'], 'projects': ['HR dashboard creation', 'Training needs analysis report']},
            'advanced': {'duration': '3-4 months', 'skills': ['Strategic HRM', 'Organizational development', 'Talent management strategy', 'Change management', 'HR budgeting', 'Leadership coaching'], 'projects': ['HR strategy for organizational growth', 'Employee engagement improvement plan']},
            'certifications': ['SHRM-CP / SHRM-SCP', 'HRCI PHR/SPHR', 'NIPM Certification', 'Advanced HR Analytics'],
            'timeline': '10 months'
        },
        'Content Writer': {
            'beginner': {'duration': '1-2 months', 'skills': ['Grammar & writing basics', 'Research skills', 'SEO fundamentals', 'Blogging platforms (WordPress)', 'Content formatting'], 'projects': ['Write 5 blog posts', 'Create content style guide']},
            'intermediate': {'duration': '2-3 months', 'skills': ['Advanced SEO writing', 'Content strategy', 'Copywriting', 'Editing & proofreading', 'CMS expertise', 'Social media content'], 'projects': ['Full content strategy for a brand', 'Website copywriting project']},
            'advanced': {'duration': '2-3 months', 'skills': ['Technical writing', 'UX writing', 'Content marketing strategy', 'Analytics & performance tracking', 'Thought leadership writing', 'AI writing tools'], 'projects': ['Technical documentation suite', 'Thought leadership article series']},
            'certifications': ['HubSpot Content Marketing', 'Copywriting Course (AWAI)', 'Google Digital Marketing'],
            'timeline': '6 months'
        },
        'Digital Marketing Specialist': {
            'beginner': {'duration': '2-3 months', 'skills': ['Digital marketing fundamentals', 'Social media platforms', 'Google Analytics', 'SEO basics', 'Content creation (Canva)', 'MS Excel'], 'projects': ['Social media audit report', 'Basic SEO optimization for a website']},
            'intermediate': {'duration': '3-4 months', 'skills': ['Google Ads certification', 'Facebook/Instagram Ads', 'Email marketing platforms', 'SEM & PPC strategies', 'Conversion optimization', 'CRM tools'], 'projects': ['Full PPC campaign setup & management', 'Email marketing automation flow']},
            'advanced': {'duration': '3-4 months', 'skills': ['Multi-channel marketing strategy', 'Marketing automation (HubSpot/Marketo)', 'ROI attribution modeling', 'A/B testing & experimentation', 'Team management', 'Budget planning'], 'projects': ['Quarterly digital marketing strategy', 'Growth hacking experiment']},
            'certifications': ['Google Digital Marketing Certificate', 'Facebook Blueprint', 'HubSpot Inbound Marketing', 'Google Ads Certifications'],
            'timeline': '10 months'
        },
        'Graphic Designer': {
            'beginner': {'duration': '2-3 months', 'skills': ['Design principles & color theory', 'Typography', 'Adobe Photoshop', 'Adobe Illustrator', 'Canva', 'File formats & prepress'], 'projects': ['Logo design project', 'Social media graphics set']},
            'intermediate': {'duration': '3-4 months', 'skills': ['Adobe InDesign', 'Brand identity design', 'UI/UX basics (Figma)', 'Motion graphics basics', 'Packaging design', 'Portfolio building'], 'projects': ['Full brand identity package', 'Website UI mockup']},
            'advanced': {'duration': '3-4 months', 'skills': ['Advanced typography & layout', 'Art direction', '3D design basics', 'Advanced motion graphics', 'Design system creation', 'Client management'], 'projects': ['Complete design system for an app', 'Advertising campaign creative suite']},
            'certifications': ['Adobe Certified Professional', 'Google UX Design Certificate', 'Interaction Design Foundation'],
            'timeline': '10 months'
        },
        'Social Media Manager': {
            'beginner': {'duration': '2-3 months', 'skills': ['Social media platform expertise', 'Content calendar planning', 'Content creation (Canva)', 'Basic analytics & reporting', 'Community management'], 'projects': ['Social media content calendar', 'Community engagement report']},
            'intermediate': {'duration': '3-4 months', 'skills': ['Advanced content strategy', 'Paid social campaigns', 'Influencer marketing', 'Social listening tools', 'Crisis management', 'Brand voice development'], 'projects': ['Paid social campaign setup', 'Brand voice guideline document']},
            'advanced': {'duration': '3-4 months', 'skills': ['Multi-platform growth strategy', 'Social media ROI analysis', 'Team leadership', 'Viral marketing strategy', 'Advanced analytics & insights', 'Trend forecasting'], 'projects': ['Social media growth blueprint', 'Viral campaign strategy document']},
            'certifications': ['Meta Certified Digital Marketing Associate', 'HubSpot Social Media Certification', 'Hootsuite Social Marketing Certification'],
            'timeline': '10 months'
        },
        'Operations Manager': {
            'beginner': {'duration': '2-3 months', 'skills': ['Operations fundamentals', 'MS Excel (intermediate)', 'Supply chain basics', 'Inventory management', 'Process documentation'], 'projects': ['Process mapping project', 'Inventory optimization report']},
            'intermediate': {'duration': '3-4 months', 'skills': ['ERP systems (SAP/Oracle)', 'Project management tools', 'Quality management', 'Budgeting & cost control', 'Vendor management', 'Data analysis'], 'projects': ['ERP implementation case study', 'Cost reduction analysis project']},
            'advanced': {'duration': '3-4 months', 'skills': ['Strategic operations planning', 'Lean/Six Sigma methodologies', 'Business continuity planning', 'Leadership & team management', 'Advanced supply chain strategy', 'Digital transformation'], 'projects': ['Operations strategy roadmap', 'Lean transformation project']},
            'certifications': ['Six Sigma Green Belt', 'APICS CPIM', 'PMP', 'SAP Certified Application Associate'],
            'timeline': '10 months'
        },
        'Research Scientist': {
            'beginner': {'duration': '2-3 months', 'skills': ['Research methodology', 'Scientific writing', 'Literature review techniques', 'Statistical analysis (SPSS/R)', 'Lab safety & techniques', 'Data collection methods'], 'projects': ['Literature review paper', 'Research proposal draft']},
            'intermediate': {'duration': '3-4 months', 'skills': ['Advanced statistical methods', 'Python/R for data analysis', 'Experimental design', 'Grant writing', 'Peer review process', 'Scientific presentation skills'], 'projects': ['Full research paper', 'Grant proposal submission']},
            'advanced': {'duration': '4-6 months', 'skills': ['Independent research design', 'Advanced data modeling', 'Mentoring & collaboration', 'Publication strategy', 'Interdisciplinary research', 'Research project management'], 'projects': ['Lead research study from conception to publication', 'Cross-institutional research collaboration']},
            'certifications': ['Good Clinical Practice (GCP)', 'Responsible Conduct of Research (RCR)', 'Statistical Analysis Certification'],
            'timeline': '12 months'
        },
        'Project Manager': {
            'beginner': {'duration': '2-3 months', 'skills': ['Project management fundamentals', 'Agile & Scrum basics', 'JIRA/Trello/Asana', 'MS Excel', 'Documentation & reporting', 'Communication skills'], 'projects': ['Project charter document', 'Project plan in MS Project']},
            'intermediate': {'duration': '3-4 months', 'skills': ['Advanced project planning', 'Risk management', 'Budgeting & cost management', 'Stakeholder management', 'Agile/Scrum mastery', 'Quality management'], 'projects': ['Full project plan for a software launch', 'Risk register & mitigation plan']},
            'advanced': {'duration': '3-4 months', 'skills': ['Program & portfolio management', 'Strategic alignment', 'Change management', 'Leadership & conflict resolution', 'Negotiation skills', 'Advanced methodologies (PRINCE2, Lean)'], 'projects': ['Complex multi-team project', 'Organizational change management plan']},
            'certifications': ['PMP (PMI)', 'Certified Scrum Master (CSM)', 'PRINCE2 Practitioner', 'Google Project Management Certificate'],
            'timeline': '10 months'
        },
        'Management Consultant': {
            'beginner': {'duration': '2-3 months', 'skills': ['Business fundamentals', 'MS Excel (advanced)', 'PowerPoint for presentations', 'Analytical problem solving', 'Market research', 'Financial literacy'], 'projects': ['Market entry analysis', 'Competitive landscape report']},
            'intermediate': {'duration': '3-4 months', 'skills': ['Consulting frameworks (MECE, 4P, BCG matrix)', 'Financial modeling', 'Data analysis with SQL/Python', 'Client communication', 'Hypothesis-driven problem solving', 'Interviewing & data gathering'], 'projects': ['Business strategy recommendation', 'Operations improvement case']},
            'advanced': {'duration': '3-4 months', 'skills': ['Advanced strategy development', 'M&A advisory', 'Organizational design', 'Digital transformation strategy', 'Thought leadership', 'Practice/business development'], 'projects': ['Full due diligence report', 'Digital transformation roadmap']},
            'certifications': ['Management Consulting Certification (IBS)', 'PMP', 'CFA Level 1 (for finance consulting)', 'Six Sigma Green Belt'],
            'timeline': '12 months'
        }
    }

    # Return the roadmap for the specified role, or a generic one
    if career_role in roadmaps:
        return roadmaps[career_role]

    # Generic roadmap if role not found
    return {
        'beginner': {
            'duration': '1-2 months',
            'skills': ['Core fundamentals of the domain', 'Basic programming skills', 'Version control (Git)', 'Problem-solving techniques'],
            'projects': ['Starter project in the domain', 'Practice exercises']
        },
        'intermediate': {
            'duration': '2-3 months',
            'skills': ['Framework/tool proficiency', 'Project development', 'Testing & debugging', 'Collaboration skills'],
            'projects': ['Medium-complexity project', 'Team collaboration project']
        },
        'advanced': {
            'duration': '2-3 months',
            'skills': ['Advanced concepts & specialization', 'System design', 'Production deployment', 'Best practices'],
            'projects': ['Production-grade project', 'Open source contribution']
        },
        'certifications': ['Industry-relevant certifications'],
        'timeline': '6 months'
    }