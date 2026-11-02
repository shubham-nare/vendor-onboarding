"""Write-once audit events for material actions."""

from __future__ import annotations

from onboarding.ap.models import AuditEvent


def record(s, *, entity: str, entity_id, action: str, actor=None, actor_label: str = "", entity_label: str = "", vendor_pk=None,
           reason: str = "", detail: dict | None = None, override: bool = False) -> AuditEvent:
    ev = AuditEvent(entity=entity, entity_id=str(entity_id), action=action, actor_id=getattr(actor, "id", None),
                    actor_label=actor_label or (getattr(actor, "name", "") or "system"), entity_label=entity_label, vendor_pk=vendor_pk,
                    reason=reason or "", detail=detail or {}, override=override)
    s.add(ev)
    return ev
