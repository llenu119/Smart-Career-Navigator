"""
PDF Career Report Generator
============================
Generates a comprehensive downloadable PDF career report using fpdf2.
Includes: profile summary, career recommendations, skill gap analysis,
resume score, improvement suggestions, roadmap, and course recommendations.

Called by: routes/dashboard.py → download_report()
"""

import os
from datetime import datetime
from fpdf import FPDF

# Directory where generated reports are saved
REPORTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'static', 'reports')


class CareerReportPDF(FPDF):
    """
    Custom PDF class with header and footer styling
    for the Smart Career Navigator report.
    """

    def __init__(self, student_name='Student'):
        super().__init__()
        self.student_name = student_name

    def header(self):
        """Page header with title and branding."""
        # Background bar
        self.set_fill_color(79, 70, 229)  # Indigo
        self.rect(0, 0, 210, 18, 'F')

        # Title text
        self.set_text_color(255, 255, 255)
        self.set_font('Helvetica', 'B', 12)
        self.cell(0, 12, 'Smart Career Navigator - Career Report', align='C', new_x="LMARGIN", new_y="NEXT")
        self.ln(10)

        # Reset text color
        self.set_text_color(30, 41, 59)

    def footer(self):
        """Page footer with page number and date."""
        self.set_y(-15)
        self.set_font('Helvetica', 'I', 8)
        self.set_text_color(100, 116, 139)
        self.cell(0, 10, f'Page {self.page_no()}/{{nb}}', align='C')

    # ── Helper Methods ──

    def section_title(self, title, icon_char=''):
        """Print a styled section title with colored bar."""
        self.set_x(self.l_margin)
        self.ln(4)
        self.set_fill_color(79, 70, 229)
        self.rect(10, self.get_y(), 3, 8, 'F')
        self.set_x(16)
        self.set_font('Helvetica', 'B', 13)
        self.set_text_color(30, 41, 59)
        self.cell(0, 8, f'{icon_char} {title}', new_x="LMARGIN", new_y="NEXT")
        self.ln(2)
        # Thin line separator
        self.set_draw_color(229, 231, 235)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(3)

    def sub_title(self, title):
        """Print a sub-section title."""
        self.set_x(self.l_margin)
        self.set_font('Helvetica', 'B', 10)
        self.set_text_color(79, 70, 229)
        self.cell(0, 6, title, new_x="LMARGIN", new_y="NEXT")
        self.ln(1)
        self.set_text_color(30, 41, 59)

    def body_text(self, text):
        """Print normal body text."""
        self.set_x(self.l_margin)
        self.set_font('Helvetica', '', 10)
        self.set_text_color(51, 65, 85)
        self.multi_cell(0, 5, text, new_x="LMARGIN", new_y="NEXT")
        self.ln(1)

    def bullet_item(self, text, indent=15):
        """Print a bulleted list item."""
        self.set_x(indent)
        self.set_font('Helvetica', '', 9)
        self.set_text_color(51, 65, 85)
        self.cell(5, 5, '-')  # Bullet character (latin-1 safe)
        self.multi_cell(0, 5, f' {text}', new_x="LMARGIN", new_y="NEXT")

    def key_value(self, key, value, bold_key=True):
        """Print a key-value pair on one line."""
        self.set_x(self.l_margin)
        if bold_key:
            self.set_font('Helvetica', 'B', 10)
        else:
            self.set_font('Helvetica', '', 10)
        self.set_text_color(30, 41, 59)
        self.cell(50, 6, f'{key}:')
        self.set_font('Helvetica', '', 10)
        self.set_text_color(71, 85, 105)
        self.multi_cell(0, 6, str(value) if value else 'N/A', new_x="LMARGIN", new_y="NEXT")

    def badge_text(self, text, fill_color=(79, 70, 229)):
        """Print a badge-style inline element."""
        self.set_font('Helvetica', '', 8)
        w = self.get_string_width(text) + 6
        self.set_fill_color(*fill_color)
        self.set_text_color(255, 255, 255)
        self.cell(w, 5, text, fill=True, new_x="RIGHT", new_y="TOP")
        self.cell(2)  # Small gap

    def check_page_space(self, needed=40):
        """Add a new page if not enough space remaining."""
        if self.get_y() > (297 - needed):
            self.add_page()


def generate_career_report(profile, recommendations, resume=None, username='Student'):
    """
    Main function to generate the career report PDF.

    Args:
        profile: dict with student profile fields
        recommendations: list of dicts with career recommendations
        resume: dict with resume analysis data (optional)
        username: student's username

    Returns:
        str: absolute path to the generated PDF file
    """
    # Ensure the reports directory exists
    os.makedirs(REPORTS_DIR, exist_ok=True)

    student_name = profile.get('name', username) or username
    pdf = CareerReportPDF(student_name=student_name)
    pdf.alias_nb_pages()
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()

    # ══════════════════════════════════════════════
    # REPORT TITLE PAGE SECTION
    # ══════════════════════════════════════════════
    pdf.ln(5)
    pdf.set_font('Helvetica', 'B', 22)
    pdf.set_text_color(79, 70, 229)
    pdf.cell(0, 12, 'Career Guidance Report', align='C', new_x="LMARGIN", new_y="NEXT")

    pdf.set_font('Helvetica', '', 11)
    pdf.set_text_color(100, 116, 139)
    pdf.cell(0, 7, f'Prepared for: {student_name}', align='C', new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 7, f'Generated on: {datetime.now().strftime("%B %d, %Y at %I:%M %p")}', align='C', new_x="LMARGIN", new_y="NEXT")
    pdf.ln(8)

    # ══════════════════════════════════════════════
    # 1. PROFILE SUMMARY
    # ══════════════════════════════════════════════
    pdf.section_title('Student Profile Summary')
    pdf.key_value('Name', student_name)
    pdf.key_value('Branch', profile.get('branch', 'N/A'))
    pdf.key_value('Year of Study', profile.get('year_of_study', 'N/A'))
    pdf.key_value('Academic Performance', profile.get('academic_performance', 'N/A'))
    pdf.ln(2)

    # Technical skills
    tech_skills = profile.get('technical_skills', '')
    if tech_skills:
        pdf.sub_title('Technical Skills')
        skills_list = [s.strip() for s in tech_skills.split(',') if s.strip()]
        skills_text = ', '.join(skills_list)
        pdf.body_text(skills_text)

    # Soft skills
    soft_skills = profile.get('soft_skills', '')
    if soft_skills:
        pdf.sub_title('Soft Skills')
        pdf.body_text(soft_skills)

    # Interests
    interests = profile.get('interests', '')
    if interests:
        pdf.sub_title('Interests & Preferred Domains')
        domains = profile.get('preferred_domains', '')
        pdf.body_text(f'Interests: {interests}')
        if domains:
            pdf.body_text(f'Preferred Domains: {domains}')

    # ══════════════════════════════════════════════
    # 2. CAREER RECOMMENDATIONS
    # ══════════════════════════════════════════════
    pdf.check_page_space(60)
    pdf.section_title('Career Recommendations')

    if recommendations:
        pdf.body_text(f'Based on your skills and interests, we found {len(recommendations)} career matches:')
        pdf.ln(2)

        for i, rec in enumerate(recommendations, 1):
            pdf.check_page_space(35)

            role = rec.get('career_role', 'Unknown')
            score = rec.get('match_score', 0)
            matched = rec.get('matched_skills', '')
            missing = rec.get('missing_skills', '')

            # Role header with score
            pdf.set_font('Helvetica', 'B', 11)
            pdf.set_text_color(30, 41, 59)
            pdf.cell(130, 7, f'{i}. {role}')
            
            # Score badge
            if score >= 70:
                pdf.set_fill_color(22, 163, 74)  # Green
            elif score >= 40:
                pdf.set_fill_color(234, 179, 8)   # Yellow
            else:
                pdf.set_fill_color(220, 38, 38)   # Red

            pdf.set_font('Helvetica', 'B', 10)
            pdf.set_text_color(255, 255, 255)
            score_text = f'{score:.0f}% Match'
            sw = pdf.get_string_width(score_text) + 8
            pdf.cell(sw, 7, score_text, fill=True, align='C', new_x="LMARGIN", new_y="NEXT")
            pdf.set_text_color(30, 41, 59)
            pdf.ln(2)

            # Matched skills
            if matched:
                pdf.set_font('Helvetica', 'I', 9)
                pdf.set_text_color(22, 163, 74)
                matched_list = [s.strip() for s in matched.split(',') if s.strip()]
                pdf.set_x(15)
                pdf.multi_cell(0, 5, f'Matching Skills: {", ".join(matched_list[:8])}', new_x="LMARGIN", new_y="NEXT")

            # Missing skills
            if missing:
                pdf.set_font('Helvetica', 'I', 9)
                pdf.set_text_color(220, 38, 38)
                missing_list = [s.strip() for s in missing.split(',') if s.strip()]
                pdf.set_x(15)
                pdf.multi_cell(0, 5, f'Skills to Learn: {", ".join(missing_list[:8])}', new_x="LMARGIN", new_y="NEXT")

            pdf.set_text_color(30, 41, 59)
            pdf.ln(3)
    else:
        pdf.body_text('No career recommendations generated yet. Please complete your profile and click "Get Recommendations" on the dashboard.')

    # ══════════════════════════════════════════════
    # 3. SKILL GAP ANALYSIS
    # ══════════════════════════════════════════════
    if recommendations:
        pdf.check_page_space(50)
        pdf.section_title('Skill Gap Overview')

        # Aggregate all matched and missing skills across recommendations
        all_matched = set()
        all_missing = set()
        for rec in recommendations:
            matched = rec.get('matched_skills', '')
            missing = rec.get('missing_skills', '')
            for s in matched.split(','):
                if s.strip():
                    all_matched.add(s.strip().title())
            for s in missing.split(','):
                if s.strip():
                    all_missing.add(s.strip().title())

        pdf.sub_title(f'Your Existing Skills ({len(all_matched)})')
        if all_matched:
            pdf.body_text(', '.join(sorted(all_matched)))
        else:
            pdf.body_text('None identified from profile.')

        pdf.sub_title(f'Skills to Develop ({len(all_missing)})')
        if all_missing:
            pdf.body_text(', '.join(sorted(all_missing)))
        else:
            pdf.body_text('Great! No major skill gaps identified.')

    # ══════════════════════════════════════════════
    # 4. RESUME ANALYSIS
    # ══════════════════════════════════════════════
    if resume:
        pdf.check_page_space(50)
        pdf.section_title('Resume Analysis')

        resume_score = resume.get('resume_score', 0)
        pdf.key_value('Resume File', resume.get('filename', 'N/A'))
        pdf.key_value('Quality Score', f'{resume_score:.0f} / 100')

        # Rating
        if resume_score >= 80:
            rating = 'Excellent'
        elif resume_score >= 60:
            rating = 'Good'
        elif resume_score >= 40:
            rating = 'Average'
        else:
            rating = 'Needs Improvement'
        pdf.key_value('Rating', rating)
        pdf.ln(2)

        # Extracted skills from resume
        extracted = resume.get('extracted_skills', '')
        if extracted:
            pdf.sub_title('Skills Found in Resume')
            skills_list = [s.strip() for s in extracted.split(',') if s.strip()]
            pdf.body_text(', '.join(skills_list))

        # Analysis suggestions
        import json
        analysis_json = resume.get('analysis_result', '{}')
        try:
            analysis = json.loads(analysis_json) if isinstance(analysis_json, str) else analysis_json
        except (json.JSONDecodeError, TypeError):
            analysis = {}

        suggestions = analysis.get('suggestions', [])
        if suggestions:
            pdf.check_page_space(30)
            pdf.sub_title('Improvement Suggestions')
            for suggestion in suggestions:
                msg = suggestion.get('message', '') if isinstance(suggestion, dict) else str(suggestion)
                stype = suggestion.get('type', 'info') if isinstance(suggestion, dict) else 'info'
                prefix = {'critical': '[!]', 'improvement': '[+]', 'good': '[OK]', 'excellent': '[*]'}.get(stype, '[-]')
                pdf.bullet_item(f'{prefix} {msg}')

        missing_sections = analysis.get('missing_sections', [])
        if missing_sections:
            pdf.sub_title('Missing Resume Sections')
            for section in missing_sections:
                pdf.bullet_item(section)

    # ══════════════════════════════════════════════
    # 5. LEARNING ROADMAP (for top recommendation)
    # ══════════════════════════════════════════════
    if recommendations:
        top_role = recommendations[0].get('career_role', '')
        if top_role:
            pdf.check_page_space(60)
            pdf.section_title(f'Learning Roadmap: {top_role}')

            # Import roadmap generator
            try:
                from ml.skill_gap import generate_roadmap
                roadmap = generate_roadmap(top_role)

                for level_name, color_label in [('beginner', 'BEGINNER'), ('intermediate', 'INTERMEDIATE'), ('advanced', 'ADVANCED')]:
                    level_data = roadmap.get(level_name, {})
                    if level_data:
                        pdf.check_page_space(30)
                        duration = level_data.get('duration', '')
                        pdf.sub_title(f'Stage: {color_label} ({duration})')

                        pdf.set_font('Helvetica', 'I', 9)
                        pdf.set_text_color(100, 116, 139)
                        pdf.cell(0, 5, 'Skills:', new_x="LMARGIN", new_y="NEXT")
                        pdf.set_text_color(30, 41, 59)
                        for skill in level_data.get('skills', []):
                            pdf.bullet_item(skill, indent=18)

                        if level_data.get('projects'):
                            pdf.set_font('Helvetica', 'I', 9)
                            pdf.set_text_color(100, 116, 139)
                            pdf.cell(0, 5, 'Projects:', new_x="LMARGIN", new_y="NEXT")
                            pdf.set_text_color(30, 41, 59)
                            for project in level_data.get('projects', []):
                                pdf.bullet_item(project, indent=18)
                        pdf.ln(2)

                # Certifications
                certs = roadmap.get('certifications', [])
                if certs:
                    pdf.check_page_space(20)
                    pdf.sub_title('Recommended Certifications')
                    for cert in certs:
                        pdf.bullet_item(cert)

                pdf.ln(2)
                pdf.set_font('Helvetica', 'B', 10)
                pdf.set_text_color(79, 70, 229)
                pdf.cell(0, 6, f'Estimated Timeline: {roadmap.get("timeline", "6 months")}', new_x="LMARGIN", new_y="NEXT")
                pdf.set_text_color(30, 41, 59)

            except Exception as e:
                pdf.body_text(f'Roadmap generation unavailable: {str(e)}')

    # ══════════════════════════════════════════════
    # 6. COURSE RECOMMENDATIONS
    # ══════════════════════════════════════════════
    if recommendations:
        # Get missing skills from top 3 recommendations
        top_missing = set()
        for rec in recommendations[:3]:
            missing = rec.get('missing_skills', '')
            for s in missing.split(','):
                if s.strip():
                    top_missing.add(s.strip())

        if top_missing:
            try:
                from ml.skill_gap import get_course_recommendations
                courses = get_course_recommendations(list(top_missing)[:10])

                if courses:
                    pdf.check_page_space(50)
                    pdf.section_title('Recommended Courses')
                    pdf.body_text('Based on your skill gaps, here are recommended courses:')
                    pdf.ln(2)

                    # Table header
                    pdf.set_font('Helvetica', 'B', 8)
                    pdf.set_fill_color(241, 245, 249)
                    pdf.set_text_color(30, 41, 59)
                    pdf.cell(25, 7, 'Skill', border=1, fill=True)
                    pdf.cell(65, 7, 'Course', border=1, fill=True)
                    pdf.cell(30, 7, 'Platform', border=1, fill=True)
                    pdf.cell(25, 7, 'Level', border=1, fill=True)
                    pdf.cell(20, 7, 'Price', border=1, fill=True, new_x="LMARGIN", new_y="NEXT")

                    # Table rows
                    pdf.set_font('Helvetica', '', 8)
                    for course in courses[:15]:  # Limit to 15 courses
                        pdf.check_page_space(10)
                        pdf.set_text_color(51, 65, 85)

                        # Truncate long names to fit cells
                        skill_name = str(course.get('skill', ''))[:15]
                        course_name = str(course.get('course_name', ''))[:38]
                        platform = str(course.get('platform', ''))[:17]
                        difficulty = str(course.get('difficulty', ''))[:14]
                        price = str(course.get('free_paid', ''))[:10]

                        pdf.cell(25, 6, skill_name, border=1)
                        pdf.cell(65, 6, course_name, border=1)
                        pdf.cell(30, 6, platform, border=1)
                        pdf.cell(25, 6, difficulty, border=1)
                        pdf.cell(20, 6, price, border=1, new_x="LMARGIN", new_y="NEXT")

            except Exception:
                pass

    # ══════════════════════════════════════════════
    # DISCLAIMER FOOTER
    # ══════════════════════════════════════════════
    pdf.check_page_space(30)
    pdf.ln(10)
    pdf.set_draw_color(229, 231, 235)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(5)
    pdf.set_font('Helvetica', 'I', 8)
    pdf.set_text_color(148, 163, 184)
    pdf.set_x(pdf.l_margin)
    pdf.multi_cell(0, 4,
        'Disclaimer: This report is generated by Smart Career Navigator, an AI-powered career guidance tool. '
        'Recommendations are based on pattern matching and should be used as guidance only. '
        'Please consult career counselors for personalized professional advice.',
        new_x="LMARGIN", new_y="NEXT"
    )
    pdf.ln(3)
    pdf.set_x(pdf.l_margin)
    pdf.set_font('Helvetica', 'B', 8)
    pdf.set_text_color(79, 70, 229)
    pdf.cell(0, 5, 'Smart Career Navigator - AI-Powered Career Development Platform', align='C')

    # ── Save the PDF ──
    filename = f'Career_Report_{username}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.pdf'
    filepath = os.path.join(REPORTS_DIR, filename)
    pdf.output(filepath)

    return filepath