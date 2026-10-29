from email.message import EmailMessage
from pathlib import Path

import aiosmtplib
from fastapi.templating import Jinja2Templates

from config import settings

# only used to render email bodies to strings, the pages themselves (forgot/reset password) live in the react app
# anchored to Backend/ like the database, so it resolves the same regardless of cwd
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=TEMPLATES_DIR)


async def send_email(
    to_email: str,
    subject: str,
    plain_text: str,
    html_content: str | None = None,
) -> None:
    message = EmailMessage()
    message["From"] = settings.mail_from
    message["To"] = to_email
    message["Subject"] = subject

    message.set_content(plain_text)

    # multipart/alternative: clients that render html show it, the rest fall back to the plain text
    if html_content:
        message.add_alternative(html_content, subtype="html")

    await aiosmtplib.send(
        message,
        hostname=settings.mail_server,
        port=settings.mail_port,
        username=settings.mail_username or None, # None skips login, for local smtp servers without auth
        password=settings.mail_password.get_secret_value() or None,
        start_tls=settings.mail_use_tls,
    )


async def send_password_reset_email(to_email: str, token: str) -> None:
    # the link opens the react app's /reset-password page, which reads ?token= and posts it to /api/users/reset-password
    reset_url = f"{settings.frontend_url}/reset-password?token={token}"
    expire_minutes = settings.reset_token_expire_minutes

    template = templates.env.get_template("email/password_reset.html")
    html_content = template.render(reset_url=reset_url, expire_minutes=expire_minutes)

    plain_text = f"""Hi,

You requested to reset your SNEAKRS. password. Open the link below to set a new password:

{reset_url}

This link will expire in {expire_minutes} minutes.

If you didn't request this, you can safely ignore this email. Your password will stay the same.

- The SNEAKRS. Team
"""

    await send_email(
        to_email=to_email,
        subject="Reset your password - SNEAKRS.",
        plain_text=plain_text,
        html_content=html_content,
    )
