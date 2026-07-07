"""Replaceable email delivery layer for OTP and onboarding messages."""


def sendOtpEmail(email, otp):
    """Mock OTP delivery.

    Swap this function later with SMTP, SendGrid, AWS SES, or another provider.
    """
    print(f"[TalentBeacon OTP] Sending OTP {otp} to {email}")
    return True
