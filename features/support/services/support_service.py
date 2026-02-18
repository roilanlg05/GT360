import httpx
from shared.settings import settings
from ..templates import get_support_email_template


SUPPORT_EMAIL = "admin@gt360.app"


async def send_support_email(
    name: str,
    email: str,
    category: str,
    subject: str,
    message: str
) -> bool:
    """
    Sends a support request email to admin@gt360.app using Brevo API.

    Args:
        name: Customer's name
        email: Customer's email (used as reply-to)
        category: Category of the request
        subject: Subject of the message
        message: Content of the message

    Returns:
        bool: True if email was sent successfully, False otherwise
    """

    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "api-key": settings.BREVO_KEY
    }

    html_content = get_support_email_template(name, email, category, subject, message)

    payload = {
        "sender": {
            "name": "GT 360 Support",
            "email": "no-reply@gt360.app"
        },
        "to": [{"email": SUPPORT_EMAIL, "name": "GT 360 Admin"}],
        "replyTo": {"email": email, "name": name},
        "subject": f"[{category.upper()}] {subject}",
        "htmlContent": html_content,
        "textContent": f"New support request from {name} ({email})\n\nCategory: {category}\nSubject: {subject}\n\nMessage:\n{message}"
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.brevo.com/v3/smtp/email",
            headers=headers,
            json=payload
        )

    return response.status_code == 201
