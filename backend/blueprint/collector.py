"""Pull recent logs (fake ones, from demo_data.py) and turn them into alerts for the ALPHA / BRAVO devices.

For each log line:
  1. find the device it belongs to (hostname, then sender IP, then the device name inside the message);
  2. skip it if it contains one of the device's ignore keywords;
  3. keep it if its severity is one the device alerts on, or it contains one of the device's keywords;
  4. store it acknowledged ("auto_acked") if an auto-ack window covers its time, otherwise open.
In the demo the log source is a generator; only the local alerts table is written.
"""
import json
import os
import re
import sys
import threading
import time
import traceback

from collections import Counter
from datetime import datetime, timedelta

from flask import Blueprint, g, jsonify, request
from sqlalchemy import func, text

from blueprint import audit as audit_mod
from blueprint import muting
from config import COLLECT_INTERVAL_SECONDS, COLLECT_WINDOW_MINUTES
from demo_data import fake_docs
from model import (auto_ack_which_device, collector_run, db, all_the_logs, device_list, ingore_keyword,
                   severity_user_choosen, what_keyword_will_insert_db)

collector = Blueprint("collector", __name__, url_prefix="/api")

INFRAS = ("ALPHA", "BRAVO")

# syslog severity name -> numeric code (0 most severe). Covers the spellings used by cisco / F5 / fortinet.
_CODE_BY_NAME = {"emergency": 0, "emergencies": 0, "alert": 1, "alerts": 1, "critical": 2, "cricital": 2,
                 "error": 3, "errors": 3, "warning": 4, "warnings": 4, "notice": 5, "notification": 5,
                 "notifications": 5, "informational": 6, "information": 6, "debug": 7, "debugging": 7}


def _code(name):
    return _CODE_BY_NAME.get((name or "").strip().lower())


_PAN_START = re.compile(r"\b1,\d{4}/\d\d/\d\d \d\d:\d\d:\d\d,")


def paloalto_severity(message):
    """Palo Alto sends CSV logs; the severity is a field of the CSV (SYSTEM: 13, THREAT: 34), not the syslog header.
    Returns the name capitalised like the severity list ('High', 'Critical'...) or None."""
    m = _PAN_START.search(message or "")
    if not m:
        return None
    fields = message[m.start():].split(",")
    kind = fields[3] if len(fields) > 3 else ""
    idx = {"SYSTEM": 13, "THREAT": 34}.get(kind)
    if idx is None or len(fields) <= idx or not fields[idx].strip():
        return None
    return fields[idx].strip().capitalize()


def _same_pan_severity(a, b):
    fix = lambda x: {"cricital": "critical"}.get((x or "").lower(), (x or "").lower())
    return fix(a) == fix(b)


def _to_local(ts):
    """ES stores UTC; the alerts table stores naive UTC+8."""
    return datetime.strptime(ts[:19], "%Y-%m-%dT%H:%M:%S") + timedelta(hours=8)


def _fetch(minutes, max_docs):
    """Fake log documents for the last `minutes`. Returns (docs, total_hits, truncated)."""
    docs = fake_docs(minutes)
    return docs, len(docs), False


class _Matcher:
    def __init__(self, devices):
        self.by_name = {}        # lower-case name -> [devices]  (two devices can share a name, e.g. BRAVO-CS03)
        self.by_ip = {}
        for d in devices:
            self.by_name.setdefault(d.host_name.lower(), []).append(d)
            self.by_ip.setdefault(d.host_address, d)
        # device names found inside message text (word-boundary match, longest names first)
        names = sorted({d.host_name for d in devices}, key=lambda x: -len(x))
        self.in_text = [(re.compile(r"(?<![A-Za-z0-9_-])" + re.escape(n) + r"(?![A-Za-z0-9_-])", re.I), n.lower()) for n in names]

    @staticmethod
    def _host(src):
        host = src.get("host")
        if isinstance(host, str):                       # some shippers send just a name
            host = {"name": host}
        host = host if isinstance(host, dict) else {}
        ips = host.get("ip")
        ips = [ips] if isinstance(ips, str) else [i for i in (ips or []) if isinstance(i, str)]    # ECS allows a list
        name = host.get("hostname") or host.get("name") or ""
        return (name if isinstance(name, str) else ""), ips

    def _pick(self, candidates, ips):
        """Several devices with the same name: take the one whose IP sent the line."""
        if len(candidates) == 1:
            return candidates[0]
        for d in candidates:
            if d.host_address in ips:
                return d
        return candidates[0]

    def find(self, src, message):
        hostname, ips = self._host(src)
        short = hostname.split(".")[0].lower()
        if short and short in self.by_name:
            return self._pick(self.by_name[short], ips)
        for ip in ips:
            if ip in self.by_ip:
                return self.by_ip[ip]
        # No hostname/IP match. A relay or shipper may have put its own name in `host`, with the real device name in
        # the line's header. A device name mentioned deep in the body ("neighbor X flapped") is NOT the sender, so when
        # the line carries an unknown hostname only the first 96 characters (the header) are searched.
        text = message[:96] if short else message
        for rx, name in self.in_text:
            if rx.search(text):
                return self._pick(self.by_name[name], ips)
        return None

    def sender(self, src):
        hostname, ips = self._host(src)
        return hostname or (ips[0] if ips else "unknown")


def expire_muted():
    """Repeats stored paused by a mute rule are not 'real' pauses. When their time passes: if a rule still covers the
    error (it was extended meanwhile) they stay paused until the rule's time; otherwise they are acknowledged, so
    hundreds of repeats of a flapping error do not all return to the open list at once."""
    now = _now_local()
    rows = all_the_logs.query.filter(
        all_the_logs.who_paused_the_alert.like("muted (same error%"),
        func.coalesce(all_the_logs.alert_acked_or_not, "") != "Acked",
        all_the_logs.pause_the_alert_until_when.isnot(None), all_the_logs.pause_the_alert_until_when <= now).all()
    if rows:
        active = muting.active_map()
        for r in rows:
            sig = muting.signature(r.message)
            until = active.get((r.host_address, sig)) or active.get((r.host_name, sig))
            if until:
                r.pause_the_alert_until_when = until
            else:
                r.alert_acked_or_not, r.who_acked_the_alert = "Acked", "auto_acked (mute ended)"
    db.session.commit()


def collect(minutes=10, dry_run=False, max_docs=5000):
    devices = device_list.query.filter(device_list.deivce_belongs_to_which_folders.in_(INFRAS)).all()
    matcher = _Matcher(devices)

    sev_rows = {r.device_name: r.severity_that_user_selected for r in severity_user_choosen.query.all()}
    ignores, keywords = {}, {}
    for r in ingore_keyword.query.all():
        ignores.setdefault(r.device_name, []).append(r.filter_sub_keyword)
    for r in what_keyword_will_insert_db.query.all():
        keywords.setdefault(r.device_name, []).append(r.keyword_user_input)
    windows = {}
    for w in auto_ack_which_device.query.all():
        windows.setdefault(w.device_name, []).append((w.auto_ack_start_time, w.auto_ack_end_time))

    if not dry_run:
        expire_muted()                    # muted repeats whose mute has ended are acknowledged, not resurrected
        muting.prune_expired()            # (only real runs change data; a dry run is read-only)
    mutes = muting.active_map()           # {(device ip or name, signature): until}: "same error" muted by someone
    docs, total, truncated = _fetch(minutes, max_docs)
    stats = Counter()
    unmatched, per_device, samples = Counter(), Counter(), []
    ignored_kw = {}                                     # which 'never alert' keyword dropped how many lines
    pending = []
    for src in docs:
        try:
            message = (src.get("event") or {}).get("original") or src.get("message") or ""
            if not isinstance(message, str):
                message = str(message)
            device = matcher.find(src, message)
        except Exception:                               # one malformed document must not stop the whole run
            stats["bad_docs"] += 1
            continue
        if device is None:
            unmatched[matcher.sender(src)] += 1
            continue
        stats["matched"] += 1
        name = device.host_name
        ign = next((k for k in ignores.get(name, []) if k and k in message), None)
        if ign is not None:
            stats["ignored_by_keyword"] += 1
            e = ignored_kw.setdefault(ign, {"count": 0, "devices": Counter(), "sample": message[:160]})
            e["count"] += 1
            e["devices"][name] += 1
            continue
        sev = (src.get("log") or {}).get("syslog", {}).get("severity") or {}
        chosen = [x for x in (sev_rows.get(name) or "").split(",") if x]
        hit_keyword = next((k for k in keywords.get(name, []) if k and k in message), None)
        level = sev.get("name") or "Unknown"
        if device.which_vendor == "paloalto":
            pan = paloalto_severity(message)
            qualifies = bool(pan) and any(_same_pan_severity(pan, c) for c in chosen)
            level = pan or level
        else:
            code = sev.get("code") if isinstance(sev.get("code"), int) else _code(sev.get("name"))
            qualifies = code is not None and code in {_code(x) for x in chosen} - {None}
        if not (qualifies or hit_keyword):
            stats["below_threshold"] += 1
            continue
        ts = _to_local(src["@timestamp"])
        acked = any(a < ts < b for a, b in windows.get(name, []))
        muted_until = muting.lookup(mutes, device, muting.signature(message)) if not acked else None
        pending.append((device, ts, message, level, hit_keyword, acked, muted_until))

    # skip lines we already stored (same device, time and text)
    existing = set()
    if pending:
        lo, hi = min(p[1] for p in pending), max(p[1] for p in pending)
        for ip, ts, msg in db.session.query(all_the_logs.host_address, all_the_logs.timestamp, all_the_logs.message)\
                .filter(all_the_logs.timestamp >= lo, all_the_logs.timestamp <= hi):
            existing.add((ip, ts, msg))
    rows = []
    for device, ts, message, level, keyword, acked, muted_until in pending:
        message = message[:9900]                       # the stored form: compare exactly what would be stored
        if (device.host_address, ts, message) in existing:
            stats["already_stored"] += 1
            continue
        existing.add((device.host_address, ts, message))
        if muted_until is not None:
            stats["muted"] += 1                 # stored paused: visible on the Paused page, no alarm
        else:
            per_device[device.host_name] += 1
            stats["auto_acked" if acked else "new_open"] += 1
        if len(samples) < 5:
            samples.append({"device": device.host_name, "level": level, "keyword": keyword, "message": message[:140]})
        rows.append(all_the_logs(
            timestamp=ts, host_address=device.host_address, host_name=device.host_name, log_level=level, message=message,
            service_type=device.which_vendor or "unknown", which_keyword_is_triggered=keyword,
            alert_acked_or_not="Acked" if acked else "alert_not_acked",
            who_acked_the_alert="auto_acked" if acked else None, boolean_for_pausing_alert_checkbox=False,
            pause_the_alert_until_when=muted_until, who_paused_the_alert=("muted (same error as a paused alert)" if muted_until else None),
            insert_by_which_condition="demo",
        ))
    if rows and not dry_run:
        try:
            db.session.add_all(rows)
            db.session.commit()
        except Exception:
            db.session.rollback()
            for row in rows:                           # find the bad row(s); store all the others
                try:
                    db.session.add(row)
                    db.session.commit()
                except Exception:
                    db.session.rollback()
                    stats["rows_failed"] += 1
        stats["new_open"] = max(0, stats["new_open"] - stats["rows_failed"])
    return {
        "dry_run": dry_run, "minutes": minutes, "es_total_in_window": total, "scanned": len(docs),
        "truncated": truncated, "matched_to_a_device": stats["matched"], "unmatched": sum(unmatched.values()),
        "unmatched_top": unmatched.most_common(5), "ignored_by_keyword": stats["ignored_by_keyword"],
        "below_severity_threshold": stats["below_threshold"], "already_stored": stats["already_stored"],
        "new_open_alerts": stats["new_open"], "auto_acked": stats["auto_acked"], "muted": stats["muted"],
        "per_device": dict(per_device), "samples": samples,
        "ignored_top": [{"keyword": k[:120], "count": v["count"], "devices": [d for d, _ in v["devices"].most_common(3)], "sample": v["sample"]}
                        for k, v in sorted(ignored_kw.items(), key=lambda kv: -kv[1]["count"])[:8]], "bad_docs": stats["bad_docs"], "rows_failed": stats["rows_failed"],
    }


_last_manual = {"at": 0.0}


@collector.route("/collect", methods=["POST"])
def collect_route():
    data = request.get_json(silent=True) or {}
    minutes = min(max(int(data.get("minutes") or request.args.get("minutes") or 10), 1), 1440)
    dry = bool(data.get("dry_run")) or request.args.get("dry_run") in ("1", "true")
    if not dry and time.time() - _last_manual["at"] < 10:
        return jsonify({"error": "A pull just ran. Wait a few seconds before pulling again.", "error_kind": "busy"}), 429
    started = _now_local()
    t0 = time.time()
    with collector_lock() as got:                       # never run beside the scheduled collector (it would double-store)
        if not got:
            return jsonify({"error": "A collection is already running. Try again in a moment.", "error_kind": "busy"}), 409
        state["running"] = True
        if not dry:
            _last_manual["at"] = time.time()            # counted only for a pull that really starts
        try:
            result = collect(minutes, dry)
        except Exception as e:      
            db.session.rollback()
            kind, msg = describe_error(e)
            if not dry:
                row = record_run(started, "manual", minutes, None, e)
                if row is not None:
                    row.duration_ms = int((time.time() - t0) * 1000)
                    db.session.commit()
            return jsonify({"error": msg, "error_kind": kind}), 502
        finally:
            state["running"] = False
    if not dry:
        row = record_run(started, "manual", minutes, result, None)
        if row is not None:
            row.duration_ms = int((time.time() - t0) * 1000)
            db.session.commit()
    return jsonify(result)


# ------------------------------------------------------------ run history
_table_ready = False
KEEP_RUNS = 2000
_es_host = "demo log generator"


def _ensure_table():
    global _table_ready
    if not _table_ready:
        collector_run.__table__.create(bind=db.engine, checkfirst=True)
        _table_ready = True


def describe_error(e):
    """(kind, plain-language message) for anything that goes wrong while collecting."""
    return "other", f"Collection failed: {type(e).__name__}: {e}"[:200]


def _now_local():
    return datetime.utcnow() + timedelta(hours=8)


def record_run(started, source, minutes, result=None, error=None):
    """Store one run (success or failure) and prune old history. Never raises: logging must not break collection."""
    try:
        _ensure_table()
        kind = msg = None
        if error is not None:
            kind, msg = describe_error(error)
        r = result or {}
        row = collector_run(
            started_at=started, duration_ms=None,
            source=source, ok=error is None, error_kind=kind, error_message=msg, minutes=minutes,
            scanned=r.get("scanned", 0), matched=r.get("matched_to_a_device", 0), unmatched=r.get("unmatched", 0),
            new_alerts=r.get("new_open_alerts", 0), auto_acked=r.get("auto_acked", 0), ignored=r.get("ignored_by_keyword", 0),
            below_threshold=r.get("below_severity_threshold", 0), already_stored=r.get("already_stored", 0),
            details=json.dumps({"per_device": r.get("per_device", {}), "unmatched_top": r.get("unmatched_top", []),
                                "samples": r.get("samples", []), "ignored_top": r.get("ignored_top", []), "truncated": r.get("truncated", False), "muted": r.get("muted", 0),
                                "bad_docs": r.get("bad_docs", 0), "rows_failed": r.get("rows_failed", 0),
                                "es_total_in_window": r.get("es_total_in_window"), "raw_error": (f"{type(error).__name__}: {error}"[:300] if error else None)}),
        )
        db.session.add(row)
        db.session.commit()
        extra = collector_run.query.count() - KEEP_RUNS
        if extra > 100:
            oldest = collector_run.query.order_by(collector_run.id).limit(extra).all()
            for o in oldest:
                db.session.delete(o)
            db.session.commit()
        return row
    except Exception:
        db.session.rollback()
        return None


# ------------------------------------------------------------------ schedule
LOCK_NAME = "syslog_collector"
state = {"running": False}
_started = False


MAX_CATCH_UP_MINUTES = 1440


def catch_up_window(source):
    """Minutes to read: the configured window, or longer when the last successful *scheduled* run is older than that
    (the backend was down), so a gap never loses logs. Capped at 24 hours."""
    window = COLLECT_WINDOW_MINUTES
    try:
        _ensure_table()
        last_ok = collector_run.query.filter_by(ok=True, source="schedule").order_by(collector_run.id.desc()).first()
        if last_ok is not None:
            behind = int((_now_local() - last_ok.started_at).total_seconds() // 60) + 2     # +2 = overlap
            window = max(window, min(behind, MAX_CATCH_UP_MINUTES))
    except Exception:
        db.session.rollback()
    return window


from contextlib import contextmanager


@contextmanager
def collector_lock():
    """Hold the collector lock on one dedicated database connection. Yields True when we own it.

    The lock belongs to a *connection*, so it is taken and released on a connection held for the whole run.
    (Releasing it through the normal session/pool can use a different connection, leave the lock held by an idle
    one, and make every later run skip silently.)"""
    with db.engine.connect() as conn:
        got = bool(conn.execute(text("SELECT GET_LOCK(:n, 0)"), {"n": LOCK_NAME}).scalar())
        try:
            yield got
        finally:
            if got:
                try:
                    conn.execute(text("SELECT RELEASE_LOCK(:n)"), {"n": LOCK_NAME})
                except Exception:
                    pass      # the connection is closed right after; if even that fails the server drops the lock when the session ends


def run_once(app, minutes=None, source="schedule"):
    """One scheduled collection run (skipped when another run, scheduled or manual, holds the lock)."""
    with app.app_context():
        with collector_lock() as got:
            if not got:
                return None
            state["running"] = True
            try:
                started = _now_local()
                t0 = time.time()
                window = minutes or catch_up_window(source)
                result = error = None
                try:
                    result = collect(window, False)
                except Exception as e:
                    db.session.rollback()
                    error = e
                row = record_run(started, source, window, result, error)
                if row is not None:
                    row.duration_ms = int((time.time() - t0) * 1000)
                    try:
                        db.session.commit()
                    except Exception:
                        db.session.rollback()
                return result
            finally:
                state["running"] = False


def should_autostart(app):
    """(start?, reason). Importing the app from a script or a test must NOT start a collector thread; a real
    server process should. COLLECTOR_AUTOSTART=1/0 overrides the guess (e.g. `flask run --debug --no-reload`)."""
    flag = os.environ.get("COLLECTOR_AUTOSTART", "").strip().lower()
    if flag in ("0", "false", "no"):
        return False, "COLLECTOR_AUTOSTART=0"
    if flag in ("1", "true", "yes"):
        return True, "COLLECTOR_AUTOSTART=1"
    if os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        return True, "reloader child process"
    arg0 = (sys.argv[0] if sys.argv else "").lower().replace("\\", "/")
    prog = os.path.basename(arg0)
    if prog == "__main__.py":                     # `python -m gunicorn ...` / `python -m flask run`
        prog = os.path.basename(os.path.dirname(arg0))
    if any(k in prog for k in ("gunicorn", "waitress", "uwsgi", "hypercorn", "uvicorn")):
        return True, "running under a production server"
    if prog == "flask" or prog == "flask.exe":
        if "run" not in sys.argv[1:]:              # `flask shell`, `flask db upgrade` ... are not servers
            return False, "flask command other than run"
        return (False, "flask reloader parent: the child process collects") if app.debug else (True, "flask run")
    return False, "not a server process (script or test import)"


def start_scheduler(app):
    """Start the background thread once per process (no-op when COLLECT_INTERVAL_SECONDS is 0)."""
    global _started
    if _started or COLLECT_INTERVAL_SECONDS <= 0:
        return
    _started = True

    def loop():
        time.sleep(3)                         # let the app finish starting
        while True:
            started = time.time()
            try:
                run_once(app)
            except Exception:
                traceback.print_exc()          # e.g. the database was briefly unreachable: log it and try again next tick
            time.sleep(max(1, COLLECT_INTERVAL_SECONDS - (time.time() - started)))

    threading.Thread(target=loop, name="alert-collector", daemon=True).start()


def _iso(ts):
    return f"{ts.isoformat()}+08:00" if ts else None


def _run_json(r, with_details=False):
    out = {"id": r.id, "started_at": _iso(r.started_at), "duration_ms": r.duration_ms, "source": r.source, "ok": bool(r.ok),
           "error_kind": r.error_kind, "error_message": r.error_message, "minutes": r.minutes, "scanned": r.scanned,
           "matched": r.matched, "unmatched": r.unmatched, "new_alerts": r.new_alerts, "auto_acked": r.auto_acked,
           "ignored": r.ignored, "below_threshold": r.below_threshold, "already_stored": r.already_stored}
    if with_details:
        try:
            out["details"] = json.loads(r.details or "{}")
        except ValueError:
            out["details"] = {}
    return out


@collector.route("/collect/status")
def collect_status():
    """Current health of the collector, derived from the stored run history (so it survives restarts)."""
    _ensure_table()
    enabled = COLLECT_INTERVAL_SECONDS > 0
    last = collector_run.query.order_by(collector_run.id.desc()).first()
    last_ok_row = collector_run.query.filter_by(ok=True).order_by(collector_run.id.desc()).first()
    since = _now_local() - timedelta(hours=24)
    recent = collector_run.query.filter(collector_run.started_at >= since).all()
    stale = False
    if enabled and last is not None:
        stale = (_now_local() - last.started_at).total_seconds() > max(3 * COLLECT_INTERVAL_SECONDS, 180)
    return jsonify({
        "enabled": enabled, "interval_seconds": COLLECT_INTERVAL_SECONDS, "window_minutes": COLLECT_WINDOW_MINUTES,
        "running": state["running"], "last_run": _iso(last.started_at) if last else None,
        "last_ok": last.ok if last else None, "error_kind": last.error_kind if last else None,
        "error_message": last.error_message if last else None,
        "last_success": _iso(last_ok_row.started_at) if last_ok_row else None, "stale": stale,
        "elasticsearch": _es_host, "runs_24h": len(recent), "failed_24h": sum(1 for r in recent if not r.ok),
        "new_alerts_24h": sum(r.new_alerts or 0 for r in recent),
        "last_truncated": bool(last and json.loads(last.details or "{}").get("truncated")),
        "last_problems": (lambda d: int(d.get("bad_docs", 0)) + int(d.get("rows_failed", 0)))(json.loads(last.details or "{}")) if last else 0,
    })


@collector.route("/collect/runs")
def collect_runs():
    _ensure_table()
    limit = min(max(request.args.get("limit", 100, type=int), 1), 500)
    q = collector_run.query
    if request.args.get("errors") in ("1", "true"):
        q = q.filter_by(ok=False)
    rows = q.order_by(collector_run.id.desc()).limit(limit).all()
    return jsonify([_run_json(r, with_details=True) for r in rows])


@collector.before_request
def _require_name():
    if request.method == "POST":
        who = audit_mod.actor_from_request()
        if not who:
            return jsonify({"error": "Enter your name before making changes.", "code": "name_required"}), 400
        g.actor = who
    return None


@collector.after_request
def _log_manual_pull(resp):
    if request.method == "POST" and request.path.endswith("/collect") and resp.status_code < 400:
        body = request.get_json(silent=True) or {}
        out = resp.get_json(silent=True) or {}
        if not out.get("dry_run"):
            audit_mod.record("collector.run", f"Pulled demo logs (looked back {out.get('minutes')} min): {out.get('new_open_alerts')} new alert(s)",
                             "collector", None, {"request": body, "result": {k: out.get(k) for k in ("scanned", "matched_to_a_device", "new_open_alerts", "auto_acked", "ignored_by_keyword")}})
    return resp
