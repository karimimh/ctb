from __future__ import annotations
import smtplib
from email.message import EmailMessage
from typing import Sequence
from datetime import datetime, timezone

from ctb.technical_analysis.divergence import DivergenceSignal


def format_email(signals: Sequence[DivergenceSignal]) -> tuple[str, str]:
    now = datetime.now(timezone.utc)
    subject = f"CTON {now.strftime('%Y-%m-%d %H:%MZ')} ({len(signals)} signals)"
    bullish = [s for s in signals if s.kind == 'bullish']
    bearish = [s for s in signals if s.kind == 'bearish']

    def lines(group: Sequence[DivergenceSignal]) -> list[str]:
        out = []
        for s in sorted(group, key=lambda x: (x.timeframe, x.symbol)):
            out.append(
                f"  {s.symbol} {s.timeframe} {s.kind} divergence price {s.price_prev}->{s.price_last} rsi {s.rsi_prev:.1f}->{s.rsi_last:.1f}"
            )
        return out

    body_lines = ["RSI Divergence Signals", "", "Bullish:"] + (
        lines(bullish) or ["  (none)"]) + ["", "Bearish:"] + (lines(bearish)
                                                              or ["  (none)"])
    body = "\n".join(body_lines)
    return subject, body


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
