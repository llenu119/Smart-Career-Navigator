"""
Career Recommendation Engine
=============================
Uses TF-IDF Vectorization and Cosine Similarity to match
student skills/interests with career role requirements.
Falls back to rule-based matching when ML similarity is low.
"""

import pandas as pd
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.db import get_db


def get_all_career_roles():
    """Fetch all career roles from the database."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM career_roles")
    roles = cursor.fetchall()
    conn.close()
    return roles


def prepare_student_profile_text(profile):
    """
    Combine student profile fields into a single text string
    for TF-IDF vectorization.
    """
    parts = []
    if profile.get('technical_skills'):
        parts.append(profile['technical_skills'])
    if profile.get('soft_skills'):
        parts.append(profile['soft_skills'])
    if profile.get('interests'):
        parts.append(profile['interests'])
    if profile.get('preferred_domains'):
        parts.append(profile['preferred_domains'])
    return ' '.join(parts).lower()


def prepare_role_text(role):
    """
    Combine career role fields into a single text string
    for TF-IDF vectorization.
    """
    parts = []
    if role['required_technical_skills']:
        parts.append(role['required_technical_skills'])
    if role['required_soft_skills']:
        parts.append(role['required_soft_skills'])
    if role['preferred_domains']:
        parts.append(role['preferred_domains'])
    if role['description']:
        parts.append(role['description'])
    return ' '.join(parts).lower()


def rule_based_match(student_skills, role_skills):
    """
    Rule-based fallback: calculate percentage of role skills
    matched by the student's skill set.
    """
    student_set = set(s.strip().lower() for s in student_skills.split(',') if s.strip())
    role_set = set(s.strip().lower() for s in role_skills.split(',') if s.strip())

    if not role_set:
        return 0, [], list(role_set)

    matched = student_set.intersection(role_set)
    missing = role_set - student_set
    score = (len(matched) / len(role_set)) * 100

    return round(score, 1), sorted(matched), sorted(missing)


def recommend_careers(profile, top_n=5):
    """
    Main recommendation function. 
    Uses TF-IDF + Cosine Similarity with rule-based fallback.
    
    Args:
        profile: dict with student profile fields
        top_n: number of top recommendations to return
    
    Returns:
        List of dicts with career recommendations and scores
    """
    roles = get_all_career_roles()
    if not roles:
        return []

    # Prepare text corpus for TF-IDF
    student_text = prepare_student_profile_text(profile)
    role_texts = [prepare_role_text(dict(r)) for r in roles]

    # All texts: student profile + all role descriptions
    all_texts = [student_text] + role_texts

    # ── TF-IDF Vectorization ──
    vectorizer = TfidfVectorizer(stop_words='english', max_features=5000)
    tfidf_matrix = vectorizer.fit_transform(all_texts)

    # ── Cosine Similarity ──
    # Compare student vector (index 0) with all role vectors
    student_vector = tfidf_matrix[0:1]
    role_vectors = tfidf_matrix[1:]
    similarities = cosine_similarity(student_vector, role_vectors)[0]

    # ── Combine ML + Rule-based scores ──
    recommendations = []
    student_skills = profile.get('technical_skills', '') + ',' + profile.get('soft_skills', '')

    for i, role in enumerate(roles):
        role_dict = dict(role)
        ml_score = round(similarities[i] * 100, 1)

        # Rule-based matching for skill gap analysis
        role_skills = (role_dict.get('required_technical_skills', '') or '') + ',' + \
                      (role_dict.get('required_soft_skills', '') or '')
        rule_score, matched, missing = rule_based_match(student_skills, role_skills)

        # Weighted combination: 60% ML + 40% rule-based
        combined_score = round(0.6 * ml_score + 0.4 * rule_score, 1)

        recommendations.append({
            'role': role_dict['role_name'],
            'ml_score': ml_score,
            'rule_score': rule_score,
            'combined_score': combined_score,
            'matched_skills': matched,
            'missing_skills': missing,
            'description': role_dict.get('description', ''),
            'min_skill_match': role_dict.get('min_skill_match', 60)
        })

    # Sort by combined score (descending)
    recommendations.sort(key=lambda x: x['combined_score'], reverse=True)

    return recommendations[:top_n]


def get_recommendations_for_user(user_id):
    """
    Get career recommendations based on stored student profile.
    Also saves recommendations to the database.
    """
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM student_profiles WHERE user_id = %s", (user_id,))
    profile_row = cursor.fetchone()

    if not profile_row:
        conn.close()
        return []

    profile = dict(profile_row)
    recommendations = recommend_careers(profile)

    # Clear old recommendations and save new ones
    cursor.execute("DELETE FROM recommendations WHERE user_id = %s", (user_id,))
    for rec in recommendations:
        cursor.execute('''
            INSERT INTO recommendations (user_id, career_role, match_score, matched_skills, missing_skills)
            VALUES (%s, %s, %s, %s, %s)
        ''', (
            user_id,
            rec['role'],
            rec['combined_score'],
            ','.join(rec['matched_skills']),
            ','.join(rec['missing_skills'])
        ))

    conn.commit()
    conn.close()

    return recommendations