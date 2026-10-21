"""'Same error' detection and the pause (mute) rules built on it."""
import hashlib
import re
from datetime import datetime, timedelta

from sqlalchemy import inspect, text

from model import db, pause_rule

_ready = False


def ensure_table():
    global _ready
    if not _ready:
        pause_rule.__table__.create(bind=db.engine, checkfirst=True)
        if "device_ip" not in {c["name"] for c in inspect(db.engine).get_columns("pause_rule")}:
            try:
                db.session.execute(text("ALTER TABLE pause_rule ADD COLUMN device_ip VARCHAR(64) NULL"))
                db.session.commit()
            except Exception:               # another process added it first (reloader parent/child, several workers)
                db.session.rollback()
                if "device_ip" not in {c["name"] for c in inspect(db.engine).get_columns("pause_rule")}:
                    raise
        _ready = True


def _now():
    return datetime.utcnow() + timedelta(hours=8)        # stored zone (UTC+8)


_TIME = re.compile(r"(?:[A-Z][a-z]{2}\s+\d{1,2}(?:\s+\d{4})?\s+)?\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:\s+[A-Z]{3,4}(?=:))?:?")
_DATE = re.compile(r"\d{4}[-/]\d{2}[-/]\d{2}[ T]\d{2}:\d{2}:\d{2}(?:\.\d+)?Z?")
_PAN_START = re.compile(r"\b1,\d{4}/\d\d/\d\d \d\d:\d\d:\d\d,")
# key=value counters/ids that change on every Fortigate-style line (date=, time=, sessionid=, byte counts ...)
_KV = re.compile(r"(?i)\b(date|time|eventtime|tz|sessionid|session_id|duration|sentbyte|rcvdbyte|sentpkt|rcvdpkt|srcport|dstport)=\"?[^\s\"]*\"?")


def signature(message):
    """The message with the parts that change on every occurrence removed: syslog priority, sequence numbers,
    timestamps, process ids, ports and per-event counters. IP addresses stay, so a different neighbor/host is a
    different error. Palo Alto SYSTEM logs (CSV) are reduced to their stable fields."""
    s = message or ""
    m = _PAN_START.search(s)
    if m:
        f = s[m.start():].split(",")
        if len(f) > 14 and f[3] == "SYSTEM":                 # subtype, event id, object, module, severity, description
            return _fit(" ".join(["PAN SYSTEM", f[4], f[8], f[9], f[12], f[13], f[14]]).strip())
    s = re.sub(r"^\s*<\d+>", "", s)
    s = _DATE.sub(" ", s)
    s = _TIME.sub(" ", s)
    s = _KV.sub(lambda mo: mo.group(1).lower() + "=#", s)
    s = re.sub(r"^\s*\d+:\s*", "", s)                  # leading sequence number (cisco)
    s = re.sub(r"\[\d+\]", "[]", s)                    # process id: tmm1[23591]
    s = re.sub(r"(\d{1,3}(?:\.\d{1,3}){3}):\d{1,5}", r"\1:#", s)   # ip:port -> ip:#
    return _fit(re.sub(r"\s+", " ", s).strip())


def _fit(s):
    """Fit the 600-character column without making different long errors look the same: keep the start and add a
    hash of the whole text."""
    if len(s) <= 590:
        return s
    return s[:560] + "#" + hashlib.sha1(s.encode("utf-8", "replace")).hexdigest()[:12]


def prune_expired():
    """Delete mute rules that have ended (called by real collector runs, never by dry runs)."""
    ensure_table()
    pause_rule.query.filter(pause_rule.until <= _now()).delete(synchronize_session=False)
    db.session.commit()


def active_map():
    """{(device ip, signature): until} for rules still in force (rules without an IP are keyed by device name).
    Read-only."""
    ensure_table()
    now = _now()
    out = {}
    for r in pause_rule.query.filter(pause_rule.until > now).all():
        # a rule belongs to the device IP that created it; only rules without an IP fall back to the (shared) name
        out[(r.device_ip or r.device_name, r.signature)] = r.until
    return out


def lookup(mutes, device, sig):
    """The until-time of a rule that mutes this error on this device (by IP first), else None."""
    return mutes.get((device.host_address, sig)) or mutes.get((device.host_name, sig))


def upsert_rule(device_name, device_ip, sig, sample, until, who):
    """Create the rule, or extend an existing one (never shorten it)."""
    ensure_table()
    row = pause_rule.query.filter_by(device_ip=device_ip, signature=sig).first() if device_ip else None
    if row is None:
        row = pause_rule.query.filter_by(device_name=device_name, signature=sig, device_ip=None).first()
    if row is None:
        row = pause_rule(device_name=device_name, device_ip=device_ip, signature=sig, until=until)
        db.session.add(row)
    row.device_name, row.device_ip = device_name, device_ip or row.device_ip
    row.sample, row.who = (sample or "")[:300], who
    row.until = max(until, row.until) if row.until else until
    return row


def delete_rules(device_name, device_ip, sig):
    ensure_table()
    n = pause_rule.query.filter_by(device_ip=device_ip, signature=sig).delete(synchronize_session=False) if device_ip else 0
    return n + pause_rule.query.filter_by(device_name=device_name, device_ip=None, signature=sig).delete(synchronize_session=False)
