"""
Email Service
=============
Handles sending OTP codes for email verification and password resets.

If SMTP settings are not configured in .env, it runs in Developer
Sandbox Mode and prints the OTP in the console.
"""

import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


# ============================================================
# SMTP CONFIGURATION
# ============================================================

SMTP_SERVER = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USERNAME = os.environ.get("SMTP_USERNAME", "").strip()
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "").strip()
SMTP_SENDER = os.environ.get(
    "SMTP_SENDER",
    SMTP_USERNAME
).strip()


# ============================================================
# EMAIL VERIFICATION OTP
# ============================================================

def send_otp_email(to_email, otp, username=None):
    """
    Send a 6-digit verification OTP.

    Returns:
        (True, "sent")      -> email sent successfully
        (True, "sandbox")   -> SMTP not configured
        (False, error)      -> email sending failed
    """

    subject = "Verify Your Account - Smart Career Navigator"

    body = f"""
Hi {username or 'User'},

Welcome to Smart Career Navigator!

Your 6-digit verification code is: {otp}

This code is valid for 10 minutes.
Please enter it on the verification page to activate your account.

If you did not request this code, you can safely ignore this email.

Best regards,
The Smart Career Navigator Team
"""

    return _send_email(
        to_email,
        subject,
        body,
        otp,
        "Email Verification"
    )


# ============================================================
# PASSWORD RESET OTP
# ============================================================

def send_password_reset_email(to_email, otp, username=None):
    """
    Send a 6-digit password reset OTP.

    Returns:
        (True, "sent")      -> email sent successfully
        (True, "sandbox")   -> SMTP not configured
        (False, error)      -> email sending failed
    """

    subject = "Reset Your Password - Smart Career Navigator"

    body = f"""
Hi {username or 'User'},

We received a request to reset your password
for your Smart Career Navigator account.

Your 6-digit password reset code is: {otp}

This code is valid for 10 minutes.
Please enter this code on the password reset page.

If you did not request a password reset,
you can safely ignore this email.

Best regards,
The Smart Career Navigator Team
"""

    return _send_email(
        to_email,
        subject,
        body,
        otp,
        "Password Reset"
    )


# ============================================================
# INTERNAL EMAIL SENDER
# ============================================================

def _send_email(to_email, subject, body, otp, email_type):
    """
    Internal helper used to send emails through SMTP.

    If SMTP credentials are missing:
        Developer Sandbox Mode is used.

    If SMTP sending fails:
        The error is printed and the OTP is shown in the
        Render logs as a fallback for development/testing.
    """

    # --------------------------------------------------------
    # Check SMTP configuration
    # --------------------------------------------------------

    if not SMTP_USERNAME or not SMTP_PASSWORD:

        print("\n" + "═" * 50)
        print(" 🔍 DEVELOPER SANDBOX EMAIL")
        print(f"  To:      {to_email}")
        print(f"  Type:    {email_type}")
        print(f"  Subject: {subject}")
        print(f"  OTP:     {otp}")
        print("═" * 50 + "\n")

        return True, "sandbox"

    # --------------------------------------------------------
    # Send email using SMTP
    # --------------------------------------------------------

    try:

        # Create email message
        msg = MIMEMultipart()

        msg["From"] = SMTP_SENDER
        msg["To"] = to_email
        msg["Subject"] = subject

        msg.attach(
            MIMEText(body, "plain")
        )

        # ----------------------------------------------------
        # Connect to SMTP server
        #
        # timeout=15 prevents the Render worker from waiting
        # indefinitely if the SMTP server does not respond.
        # ----------------------------------------------------

        with smtplib.SMTP(
            SMTP_SERVER,
            SMTP_PORT,
            timeout=15
        ) as server:

            # Secure the connection
            server.starttls()

            # Login
            server.login(
                SMTP_USERNAME,
                SMTP_PASSWORD
            )

            # Send email
            server.sendmail(
                SMTP_SENDER,
                to_email,
                msg.as_string()
            )

        print(
            f"✅ {email_type} email sent successfully "
            f"to {to_email}"
        )

        return True, "sent"

    # --------------------------------------------------------
    # Handle SMTP errors
    # --------------------------------------------------------

    except Exception as e:

        print(
            f"❌ Failed to send SMTP email: {e}"
        )

        # Developer fallback
        print("\n" + "═" * 50)
        print(" 🔍 DEVELOPER SANDBOX FALLBACK")
        print(f"  To:      {to_email}")
        print(f"  Type:    {email_type}")
        print(f"  OTP:     {otp}")
        print("═" * 50 + "\n")

        return False, str(e)