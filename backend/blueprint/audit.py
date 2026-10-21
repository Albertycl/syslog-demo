"""Audit log: who changed what, written for every successful data-changing request."""
import json
from urllib.parse import unquote

from flask import g, request
from sqlalchemy import func

from model import audit_log, db

_ready = False
KEEP = 20000            # rows kept; older ones are pruned


def ensure_table():
    global _ready
    if not _ready:
        audit_log.__table__.create(bind=db.engine, checkfirst=True)
        _ready = True


def actor_from_request():
    """The name the person typed in the portal, sent as the X-User header. Empty means 'not given'."""
    return unquote(request.headers.get("X-User") or "").strip()[:100]   # the browser URI-encodes it (names may be non-ASCII)


def _payload(details):
    """JSON text for the details column. Too large? keep a short valid preview instead of cutting it in half."""
    if details is None:
        return None
    text = json.dumps(details, default=str)
    return text if len(text) <= 20000 else json.dumps({"truncated": True, "preview": text[:2000]})


def record(action, summary, target_type=None, target_id=None, details=None):
    """Add one audit row. Never raises: a logging problem must not break the action that was just done."""
    try:
        ensure_table()
        db.session.add(audit_log(
            actor=getattr(g, "actor", None) or "unknown", action=action, summary=(summary or "")[:600],
            target_type=target_type, target_id=str(target_id) if target_id is not None else None,
            details=_payload(details),
            ip=(request.remote_addr or "")[:64]))       # the connecting address; a client-supplied header could be forged
        db.session.commit()
        last = db.session.query(func.max(audit_log.id)).scalar() or 0
        if last > KEEP and last % 200 == 0:             # occasional, cheap: no COUNT on every request
            audit_log.query.filter(audit_log.id <= last - KEEP).delete(synchronize_session=False)
            db.session.commit()
    except Exception:
        db.session.rollback()
