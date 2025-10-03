from __future__ import annotations

import smtplib
from email.message import EmailMessage
from typing import Sequence


def send_email(host: str, port: int, user: str, password: str, starttls: bool,
               email_from: str, recipients: Sequence[str], subject: str,
               body: str) -> None:
    msg = EmailMessage()
    msg["From"] = email_from
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = subject
    msg.set_content(body)
    with smtplib.SMTP(host, port, timeout=30) as smtp:
        if starttls:
            smtp.starttls()
        if user:
            smtp.login(user, password)
        smtp.send_message(msg)
