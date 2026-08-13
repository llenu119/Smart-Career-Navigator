"""
User Model Module
=================
Provides the User class used by Flask-Login for session management.
Separated into its own file to avoid circular imports.
"""

from utils.db import get_db


class User:
    """
    User model class for Flask-Login.
    
    Flask-Login requires certain properties and methods to manage sessions.
    This class wraps a database row and provides those interfaces.
    """

    def __init__(self, id, username, email, role):
        self.id = id
        self.username = username
        self.email = email
        self.role = role

    # ── Flask-Login required properties ──

    @property
    def is_authenticated(self):
        """Returns True if the user is authenticated."""
        return True

    @property
    def is_active(self):
        """Returns True if the user account is active."""
        return True

    @property
    def is_anonymous(self):
        """Returns False — this is a real user, not anonymous."""
        return False

    def get_id(self):
        """Returns the user ID as a string (required by Flask-Login)."""
        return str(self.id)

    # ── Database lookup methods ──

    @staticmethod
    def get_by_id(user_id):
        """Fetch a user from the database by their ID."""
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
        row = cursor.fetchone()
        conn.close()
        if row:
            return User(row['id'], row['username'], row['email'], row['role'])
        return None

    @staticmethod
    def get_by_username(username):
        """Fetch a user from the database by their username."""
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
        row = cursor.fetchone()
        conn.close()
        if row:
            return User(row['id'], row['username'], row['email'], row['role'])
        return None

    @staticmethod
    def get_by_email(email):
        """Fetch a user from the database by their email."""
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
        row = cursor.fetchone()
        conn.close()
        if row:
            return User(row['id'], row['username'], row['email'], row['role'])
        return None
