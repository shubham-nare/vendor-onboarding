"""Chasing vendors who haven't answered.

When a registration is waiting on the vendor ("Pending: vendor to fix"), someone used to have to remember to
chase them. This does it on a schedule:

  day 0   we tell the vendor exactly what is needed (the decision's message, or a reviewer's question)
  day 3   a reminder to the vendor, quoting what we asked for
  day 7   a second reminder, and a note to the employee who asked for this vendor: they know the vendor and
          can pick up the phone. The registration stays pending; nothing is closed automatically.

The clock starts when the vendor was last asked (the check's finish time, or the latest "ask the vendor"
by a reviewer) and restarts when they resubmit (a new check). Each step is recorded in `follow_ups`, keyed by
the check, so the job can run as often as it likes and never sends a step twice.

The job runs inside the app every few hours, and anyone on the procurement team can run it from the System page.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from onboarding.models import Application, Bill, Employee, FollowUp, HumanAction, Invite, Message, Run, now

log = logging.getLogger("onboarding.followups")

REMIND_AFTER_DAYS = 3
ESCALATE_AFTER_DAYS = 7
EVERY_HOURS = 6          # how often the app runs the job by itself


def _aware(d: datetime | None) -> datetime | None:
    return d.replace(tzinfo=timezone.utc) if d is not None and d.tzinfo is None else d


def day(d: datetime | None) -> str:
    return _aware(d).strftime("%d %b %Y") if d else ""


@dataclass
class Waiting:
    app: Application
    run: Run
    since: datetime              # when the vendor was last asked
    days: int
    asked: Message | None        # what we asked them for
    reminded: FollowUp | None
    escalated: FollowUp | None
    requester: Employee | None

    @property
    def next_step(self) -> tuple[str, datetime] | None:
        if not self.reminded:
            return "Reminder to the vendor", self.since + timedelta(days=REMIND_AFTER_DAYS)
        if not self.escalated:
            return "Second reminder, and a note to " + (self.requester.name if self.requester else "the requester"), self.since + timedelta(days=ESCALATE_AFTER_DAYS)
        return None

    @property
    def tone(self) -> str:   # the colour language: amber while we wait, red once it has been escalated
        return "red" if self.escalated else "amber"


async def waiting(s, at: datetime | None = None) -> list[Waiting]:
    """Every registration that is waiting on the vendor, longest wait first."""
    at = _aware(at or now())
    apps = (await s.execute(select(Application).where(Application.current_status == "PENDING_VENDOR"))).scalars().all()
    if not apps:
        return []
    ids = [a.id for a in apps]
    latest = dict((await s.execute(select(Run.application_id, func.max(Run.id)).where(Run.application_id.in_(ids)).group_by(Run.application_id))).all())
    runs = {r.id: r for r in (await s.execute(select(Run).where(Run.id.in_(list(latest.values()) or [-1])))).scalars()}
    asks = {}
    for run_id, at_ in (await s.execute(select(HumanAction.run_id, func.max(HumanAction.at)).where(
            HumanAction.run_id.in_(list(runs) or [-1]), HumanAction.action == "ask_vendor").group_by(HumanAction.run_id))).all():
        asks[run_id] = at_
    steps: dict[int, dict[str, FollowUp]] = {}
    for f in (await s.execute(select(FollowUp).where(FollowUp.run_id.in_(list(runs) or [-1])))).scalars():
        steps.setdefault(f.run_id, {})[f.kind] = f
    chased = {f.message_id for d in steps.values() for f in d.values() if f.message_id}
    msgs: dict[int, Message] = {}
    for m in (await s.execute(select(Message).where(Message.run_id.in_(list(runs) or [-1]), Message.audience == "vendor",
                                                    Message.state == "sent").order_by(Message.id))).scalars():
        if m.id not in chased:
            msgs[m.run_id] = m     # the latest real request, not a reminder of it
    invites = {i.id: i for i in (await s.execute(select(Invite).where(Invite.id.in_([a.invite_id for a in apps if a.invite_id] or [-1])))).scalars()}
    bills = {b.application_id: b for b in (await s.execute(select(Bill).where(Bill.application_id.in_(ids)))).scalars()}
    emps = {e.id: e for e in (await s.execute(select(Employee))).scalars()}
    out = []
    for a in apps:
        run = runs.get(latest.get(a.id))
        if not run or run.state != "done":
            continue
        since = max(x for x in (_aware(run.finished_at or run.started_at), _aware(asks.get(run.id))) if x)
        inv, b = invites.get(a.invite_id), bills.get(a.id)
        req = emps.get(inv.sponsor_id) if inv else (emps.get(b.engaged_employee_id) if b and b.engaged_employee_id else None)
        st = steps.get(run.id, {})
        out.append(Waiting(app=a, run=run, since=since, days=max(0, (at - since).days), asked=msgs.get(run.id),
                           reminded=st.get("reminder"), escalated=st.get("escalation"), requester=req))
    out.sort(key=lambda w: w.since)
    return out


def _vendor_reminder(w: Waiting, second: bool) -> tuple[str, str]:
    f = w.run.form or {}
    hi = f"Hello {f.get('contact_name') or 'there'},"
    when = day(w.since)
    subject = f"{'Second reminder' if second else 'Reminder'}: we still need a few things for your registration (Ref {w.app.ref})"
    quoted = ("\n".join("  " + line for line in (w.asked.body or "").strip().splitlines())) if w.asked else ""
    body = (f"{hi}\n\nOn {when} we asked you for a few things so we can finish registering {w.app.legal_name} as a supplier. "
            f"We haven't received them yet, and your registration is on hold until we do.\n\n"
            + (f"Here is what we asked for:\n\n{quoted}\n\n" if quoted else "")
            + "Please update your registration from your supplier account, or with the link in our first message. "
              "If something is unclear or you can't provide a document, reply to this email and tell us; we can usually find another way.\n\n"
              "Vendor Onboarding Team")
    return subject, body


def _requester_note(w: Waiting) -> tuple[str, str]:
    f = w.run.form or {}
    name = w.requester.name.split()[0] if w.requester else "Hello"
    contact = ", ".join(x for x in (f.get("contact_name"), f.get("contact_email"), f.get("contact_phone")) if x)
    subject = f"{w.app.legal_name} hasn't replied for {w.days} days (Ref {w.app.ref})"
    body = (f"{name},\n\nYou asked us to register {w.app.legal_name}. On {day(w.since)} we asked them to fix a few things"
            + (f", and we sent a reminder on {day(w.reminded.at)}" if w.reminded else "")
            + f". They haven't answered in {w.days} days, so the registration is still on hold.\n\n"
            f"You know this vendor: could you contact them" + (f" ({contact})" if contact else "")
            + " and ask them to update their registration? They can see exactly what is needed in their supplier account.\n\n"
              "Nothing has been closed; the registration continues as soon as they resubmit.\n\nVendor Onboarding")
    return subject, body


async def run_once(at: datetime | None = None) -> dict:
    """Send every reminder and escalation that is due. Safe to run any number of times."""
    from onboarding import mailer
    from onboarding.pipeline import sessions
    at = _aware(at or now())
    sent = dict(reminders=0, escalations=0, waiting=0)
    touched: list[int] = []
    notes: list[tuple[int, str]] = []
    async with sessions()() as s:
        for w in await waiting(s, at):
            sent["waiting"] += 1
            step = None
            if w.days >= ESCALATE_AFTER_DAYS and not w.escalated:
                step = "escalation"
            elif w.days >= REMIND_AFTER_DAYS and not w.reminded:
                step = "reminder"
            if not step:
                continue
            subject, body = _vendor_reminder(w, second=bool(w.reminded))
            m = Message(run_id=w.run.id, audience="vendor", subject=subject, body=body, state="sent", created_at=at)
            s.add(m)
            await s.flush()
            fu = FollowUp(run_id=w.run.id, application_id=w.app.id, kind=step, message_id=m.id, waiting_days=w.days, at=at)
            if step == "escalation":
                w.escalated = fu
                ns, nb = _requester_note(w)
                note = Message(run_id=w.run.id, audience="internal", subject=ns, body=nb, state="sent", created_at=at)
                s.add(note)
                await s.flush()
                fu.note_id, fu.to_employee_id = note.id, (w.requester.id if w.requester else None)
                if w.requester and w.requester.email:
                    notes.append((note.id, w.requester.email))
                sent["escalations"] += 1
            else:
                sent["reminders"] += 1
            s.add(fu)
            touched.append(w.run.id)
        await s.commit()
    for run_id in dict.fromkeys(touched):
        await mailer.deliver_for_run(run_id)
    for note_id, to in notes:
        await mailer.deliver_note(note_id, to)
    if sent["reminders"] or sent["escalations"]:
        log.info("follow-ups: %s reminder(s), %s escalation(s), %s waiting", sent["reminders"], sent["escalations"], sent["waiting"])
    return sent


async def loop() -> None:
    """The schedule: shortly after start-up, then every few hours."""
    await asyncio.sleep(60)
    while True:
        try:
            await run_once()
        except Exception:
            log.exception("follow-up job failed; it tries again at the next interval")
        await asyncio.sleep(EVERY_HOURS * 3600)
