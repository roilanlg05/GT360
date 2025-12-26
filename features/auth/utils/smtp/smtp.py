import httpx
from pydantic import EmailStr
from shared.settings import settings

print("server:", settings.BREVO_KEY)

async def send_email(email: EmailStr, sub: str, html_content: str, confirmation_url : str, name: str | None = None):

    """
    Sends an email using the Brevo SMTP API.

    Args:
        email: Recipient's email address.
        sub: Subject of the email.
        html_content: HTML content of the email.
        confirmation_url: URL to include in the email text content.
        name: Name of the recipient (Optional).

    return -> True if the email was sent successfully, False otherwise.
    """

    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "api-key": settings.BREVO_KEY
    }

    if name:
        recipent = [{"email": email, "name": name}]
    else:
        recipent = [{"email": email}]

    payload = {
        "sender": {
            "name": "Api360",
            "email": "no-reply@api360.app"
        },
        "to": recipent,
        "subject": sub,
        "htmlContent": html_content,
        "textContent": f"Confirm your account at: {confirmation_url}"
    }

    async with httpx.AsyncClient() as client:
        response = await client.post("https://api.brevo.com/v3/smtp/email",
        headers=headers,
        json=payload
    )

    print(f"Ya se envio")
    print(f"Response: {response.text}")
    return response.status_code == 201
