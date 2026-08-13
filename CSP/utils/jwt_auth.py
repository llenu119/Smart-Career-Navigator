"""
JWT Authentication & Security Utilities
=========================================
Handles JWT access token generation/validation, database-backed refresh token rotation,
role-based authorization, and sliding-window rate limiting.
"""

import os
import jwt
import time
import uuid
import logging
from datetime import datetime, timedelta
from functools import wraps
from flask import request, redirect, url_for, flash, jsonify, g, current_app
from flask_login import current_user
from utils.db import get_db
from models import User

SECRET_KEY = os.environ.get("SECRET_KEY", "smart-career-navigator-secret-key-2024")

# Set up logging to database/system.log
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'database')
os.makedirs(LOG_DIR, exist_ok=True)
logging.basicConfig(
    filename=os.path.join(LOG_DIR, 'system.log'),
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)


# ══════════════════════════════════════════════════════════════
# JWT GENERATION AND VALIDATION
# ══════════════════════════════════════════════════════════════

def generate_access_token(user_id, role):
    """Generate a short-lived JWT Access Token (valid for 15 minutes)."""
    payload = {
        'user_id': user_id,
        'role': role,
        'exp': time.time() + 15 * 60,  # 15 minutes
        'iat': time.time()
    }
    return jwt.encode(payload, SECRET_KEY, algorithm='HS256')


def generate_tokens(user_id, role):
    """
    Generate a new Access Token and Refresh Token.
    Stores the Refresh Token in the database.
    """
    access_token = generate_access_token(user_id, role)
    refresh_token = str(uuid.uuid4())
    expiry = (datetime.utcnow() + timedelta(days=7)).strftime('%Y-%m-%d %H:%M:%S')

    conn = get_db()
    cursor = conn.cursor()
    # Store refresh token in database
    cursor.execute(
        "INSERT INTO refresh_tokens (user_id, token, expiry) VALUES (%s, %s, %s)",
        (user_id, refresh_token, expiry)
    )
    conn.commit()
    conn.close()

    return access_token, refresh_token


def validate_access_token(token):
    """
    Decode and validate a JWT Access Token.
    Returns the payload dict if valid, or None if expired/invalid.
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=['HS256'])
        return payload
    except jwt.ExpiredSignatureError:
        return 'EXPIRED'
    except jwt.InvalidTokenError:
        return None


def rotate_refresh_token(old_token):
    """
    Exchanges an old refresh token for a new access token and a new refresh token.
    Implements Refresh Token Rotation to prevent reuse attacks.
    """
    conn = get_db()
    cursor = conn.cursor()
    
    # Fetch token details
    cursor.execute("SELECT * FROM refresh_tokens WHERE token = %s", (old_token,))
    row = cursor.fetchone()
    
    if not row:
        conn.close()
        return None

    user_id = row['user_id']
    expiry_str = row['expiry']
    expiry = datetime.strptime(expiry_str, '%Y-%m-%d %H:%M:%S')

    # If refresh token is expired, delete it and reject
    if expiry < datetime.utcnow():
        cursor.execute("DELETE FROM refresh_tokens WHERE token = %s", (old_token,))
        conn.commit()
        conn.close()
        return None

    # Delete the used refresh token (rotation)
    cursor.execute("DELETE FROM refresh_tokens WHERE token = %s", (old_token,))
    
    # Get user role
    cursor.execute("SELECT role FROM users WHERE id = %s", (user_id,))
    user_row = cursor.fetchone()
    role = user_row['role'] if user_row else 'student'

    # Generate new tokens
    new_access_token = generate_access_token(user_id, role)
    new_refresh_token = str(uuid.uuid4())
    new_expiry = (datetime.utcnow() + timedelta(days=7)).strftime('%Y-%m-%d %H:%M:%S')

    # Save new refresh token
    cursor.execute(
        "INSERT INTO refresh_tokens (user_id, token, expiry) VALUES (%s, %s, %s)",
        (user_id, new_refresh_token, new_expiry)
    )
    
    conn.commit()
    conn.close()

    return user_id, role, new_access_token, new_refresh_token


# ══════════════════════════════════════════════════════════════
# REQUEST LOADERS AND MIDDLEWARE LOGIC
# ══════════════════════════════════════════════════════════════

def _get_user_and_block_status(user_id):
    """
    Fetch a user plus their is_blocked flag in a single query.
    Combines what used to be two separate DB round-trips
    (User.get_by_id + a follow-up is_blocked check) into one,
    since this runs on every single request via the Flask-Login
    request loader.
    """
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None, False
    user = User(row['id'], row['username'], row['email'], row['role'])
    return user, bool(row['is_blocked'])


def load_user_from_jwt(request):
    """
    Flask-Login request loader callback.
    Authenticates requests via JWT cookie or Authorization Header.
    Performs silent automatic token refreshing if needed.
    """
    # 1. Try to get token from header or cookie
    auth_header = request.headers.get('Authorization')
    access_token = None

    if auth_header and auth_header.startswith('Bearer '):
        access_token = auth_header.split(' ')[1]
    else:
        access_token = request.cookies.get('access_token')

    if access_token:
        payload = validate_access_token(access_token)
        
        # Scenario A: Access token is valid
        if payload and payload != 'EXPIRED':
            user, is_blocked = _get_user_and_block_status(payload['user_id'])
            if user:
                if is_blocked:
                    logging.warning(f"Blocked user login attempt: {user.username}")
                    return None
                return user

        # Scenario B: Access token has expired, check for refresh token
        elif payload == 'EXPIRED':
            refresh_token = request.cookies.get('refresh_token')
            if refresh_token:
                rotated = rotate_refresh_token(refresh_token)
                if rotated:
                    user_id, role, new_access, new_refresh = rotated
                    user, is_blocked = _get_user_and_block_status(user_id)
                    if user:
                        if is_blocked:
                            return None
                        
                        # Queue the new tokens to be set in cookies at the end of the request
                        g.new_access_token = new_access
                        g.new_refresh_token = new_refresh
                        logging.info(f"JWT tokens rotated successfully for user ID: {user_id}")
                        return user

    return None


# ══════════════════════════════════════════════════════════════
# DECORATORS
# ══════════════════════════════════════════════════════════════

def admin_required(f):
    """Restricts route access to administrators."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'admin':
            flash('Access denied. Administrator privileges required.', 'danger')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function


def rate_limit(limit=10, period=60):
    """
    Decorator for database-backed rate limiting (sliding window).
    limit: Max number of requests allowed in the period.
    period: Time window in seconds.
    """
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            # Key rate limits by user ID if logged in, otherwise by client IP
            user_id = current_user.id if current_user.is_authenticated else None
            ip = request.remote_addr
            key = f"{request.endpoint}:{user_id or ip}"

            now = time.time()
            cutoff = now - period

            conn = get_db()
            cursor = conn.cursor()

            # Clean old records
            cursor.execute("DELETE FROM rate_limits WHERE key = %s AND timestamp < %s", (key, cutoff))
            
            # Count recent hits
            cursor.execute("SELECT COUNT(*) as count FROM rate_limits WHERE key = %s", (key,))
            row = cursor.fetchone()
            count = row['count'] if row else 0

            if count >= limit:
                conn.commit()
                conn.close()
                logging.warning(f"Rate limit triggered for key: {key} (Count: {count})")
                
                # Check if it's an API request
                if request.is_json or request.path.startswith('/ai') or request.path.startswith('/resume/ai'):
                    return jsonify({"error": "Too many requests. Please try again later."}), 429
                
                flash("Too many requests. Please slow down and try again.", "warning")
                # Redirect back to where they came from, or dashboard
                return redirect(request.referrer or url_for('dashboard.dashboard'))

            # Insert current hit
            cursor.execute("INSERT INTO rate_limits (key, timestamp) VALUES (%s, %s)", (key, now))
            conn.commit()
            conn.close()

            return f(*args, **kwargs)
        return wrapper
    return decorator


def log_system_event(level, message):
    """Write an audit log entry to database/system.log."""
    if level == 'info':
        logging.info(message)
    elif level == 'warning':
        logging.warning(message)
    elif level == 'error':
        logging.error(message)