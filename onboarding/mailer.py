"""Email the vendor whenever a message to them is sent: action needed, registration confirmed, unable to proceed.

Off until SMTP is set in .env (SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, MAIL_FROM). Until then every
message is still kept in the Outbox and marked "email not set up". MAIL_REDIRECT_TO sends every email to one
inbox instead of the vendor's address: use it for demos, where vendor addresses are example.com.
Each message is emailed at most once (email_deliveries records it). Never raises.
"""

from __future__ import annotations

import asyncio
import logging
import smtplib
import ssl
from email.message import EmailMessage

from sqlalchemy import select

from onboarding.config import get_settings

log = logging.getLogger(__name__)
_tasks: set[asyncio.Task] = set()


def configured() -> bool:
    st = get_settings()
    return bool(st.smtp_host and st.mail_from)


def compose(subject: str, body: str, to: list[str]) -> EmailMessage:
    st = get_settings()
    em = EmailMessage()
    em["From"] = st.mail_from
    em["Subject"] = subject
    if st.mail_redirect_to:
        em["To"] = st.mail_redirect_to
        body = f"[Copy: this email was addressed to {', '.join(to)}]\n\n{body}"
    else:
        em["To"] = to[0]
        if len(to) > 1:
            em["Cc"] = ", ".join(to[1:])
    em.set_content(body)
    return em


def _smtp_send(em: EmailMessage) -> None:
    st = get_settings()
    ctx = ssl.create_default_context()
    if st.smtp_port == 465:
        server = smtplib.SMTP_SSL(st.smtp_host, st.smtp_port, context=ctx, timeout=20)
    else:
        server = smtplib.SMTP(st.smtp_host, st.smtp_port, timeout=20)
        server.starttls(context=ctx)
    with server:
        if st.smtp_user:
            server.login(st.smtp_user, st.smtp_password)
        server.send_message(em)


async def deliver_for_run(run_id: int) -> int:
    """Email every vendor message of this check that is sent but not yet emailed. Returns how many were emailed."""
    from onboarding.models import EmailDelivery, Message, Run
    from onboarding.pipeline import sessions
    try:
        async with sessions()() as s:
            run = await s.get(Run, run_id)
            if not run:
                return 0
            msgs = (await s.execute(select(Message).where(Message.run_id == run_id, Message.audience == "vendor", Message.state == "sent"))).scalars().all()
            done = {d.message_id for d in (await s.execute(select(EmailDelivery).where(EmailDelivery.message_id.in_([m.id for m in msgs] or [-1])))).scalars()}
            f = run.form or {}
            to = [a for a in dict.fromkeys([str(f.get("contact_email") or "").strip(), str(f.get("alt_contact_email") or "").strip()]) if a]
            n = 0
            for m in msgs:
                if m.id in done:
                    continue
                rec = EmailDelivery(message_id=m.id, to_addr=", ".join(to))
                if not to:
                    rec.status = "no_address"
                elif not configured():
                    rec.status = "not_configured"
                else:
                    em = compose(m.subject, m.body, to)
                    rec.delivered_to = ", ".join(x for x in (em["To"], em["Cc"]) if x)
                    try:
                        await asyncio.to_thread(_smtp_send, em)
                        rec.status = "sent"
                        n += 1
                    except Exception as e:   # a mail problem never breaks a decision
                        rec.status, rec.error = "failed", f"{type(e).__name__}: {e}"[:300]
                        log.warning("email for message %s failed: %s", m.id, rec.error)
                s.add(rec)
            await s.commit()
            return n
    except Exception:
        log.exception("email delivery for check %s failed", run_id)
        return 0


async def deliver_note(message_id: int, to_addr: str) -> bool:
    """Email an internal note (an escalation to an employee). Recorded like vendor emails; never raises."""
    from onboarding.models import EmailDelivery, Message
    from onboarding.pipeline import sessions
    try:
        async with sessions()() as s:
            m = await s.get(Message, message_id)
            if not m or (await s.execute(select(EmailDelivery).where(EmailDelivery.message_id == message_id))).scalar():
                return False
            rec = EmailDelivery(message_id=m.id, to_addr=to_addr)
            if not configured():
                rec.status = "not_configured"
            else:
                em = compose(m.subject, m.body, [to_addr])
                rec.delivered_to = to_addr
                try:
                    await asyncio.to_thread(_smtp_send, em)
                    rec.status = "sent"
                except Exception as e:
                    rec.status, rec.error = "failed", f"{type(e).__name__}: {e}"[:300]
            s.add(rec)
            await s.commit()
            return rec.status == "sent"
    except Exception:
        log.exception("email for note %s failed", message_id)
        return False


def start(run_id: int) -> None:
    """Deliver in the background, so a decision page never waits on the mail server."""
    task = asyncio.create_task(deliver_for_run(run_id))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
