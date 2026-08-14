
"""
Email Service
=============
Handles sending OTP codes for email verification
and password resets using Resend.
"""

import os
import resend


# ============================================================
# RESEND CONFIGURATION
# ============================================================

RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "").strip()

RESEND_SENDER = os.environ.get(
    "RESEND_SENDER",
    "onboarding@resend.dev"
).strip()

# Configure Resend only when an API key is available
if RESEND_API_KEY:
    resend.api_key = RESEND_API_KEY

print("RESEND API KEY FOUND:", bool(RESEND_API_KEY))
print("RESEND SENDER:", RESEND_SENDER)


# ============================================================
# EMAIL VERIFICATION OTP
# ============================================================

def send_otp_email(to_email, otp, username=None):
    """
    Send a 6-digit verification OTP.

    Returns:
        (True, "sent")    -> email sent successfully
        (True, "sandbox") -> API key is not configured
        (False, error)    -> email sending failed
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
        (True, "sent")    -> email sent successfully
        (True, "sandbox") -> API key is not configured
        (False, error)    -> email sending failed
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
    Send an email using Resend.

    If RESEND_API_KEY is missing:
        Developer Sandbox Mode is used.

    If Resend fails:
        The error is printed to the Render logs.
    """

    # --------------------------------------------------------
    # Check Resend API key
    # --------------------------------------------------------

    if not RESEND_API_KEY:

        print("\n" + "=" * 50)
        print("DEVELOPER SANDBOX EMAIL")
        print(f"To:      {to_email}")
        print(f"Type:    {email_type}")
        print(f"Subject: {subject}")
        print(f"OTP:     {otp}")
        print("=" * 50 + "\n")

        return True, "sandbox"


    # --------------------------------------------------------
    # Send email through Resend
    # --------------------------------------------------------

    try:

        params = {
            "from": RESEND_SENDER,
            "to": [to_email],
            "subject": subject,
            "html": body.replace("\n", "<br>")
        }

        response = resend.Emails.send(params)

        print(
            f"SUCCESS: {email_type} email sent to {to_email}"
        )

        print(f"Resend response: {response}")

        return True, "sent"


    # --------------------------------------------------------
    # Handle Resend errors
    # --------------------------------------------------------

    except Exception as e:

        print(
            f"ERROR: Failed to send {email_type} email"
        )

        print(f"Resend error: {e}")

        return False, str(e)

