"""JSON API for the rebuilt frontend: infras (ALPHA / BRAVO), devices, alerts."""
import ipaddress
import json
import re
import time
from datetime import datetime, timedelta
from collections import Counter

from flask import Blueprint, g, jsonify, request
from sqlalchemy import func, inspect, text

from blueprint import audit as audit_mod
from blueprint import muting
from model import (audit_log, auto_ack_which_device, db, all_the_logs, device_list, folder_list, ingore_keyword,
                   keyword_rule, pause_rule, predefine_severity, severity_user_choosen, what_keyword_will_insert_db)

api = Blueprint("api", __name__, url_prefix="/api")

INFRAS = ("ALPHA", "BRAVO")
# Role folders inside each infra (ALPHA / BRAVO). Order is the display order.
DEFAULT_FOLDERS = ("Routers", "Switches", "OOB", "LTM", "Firewall", "Other")
PROTECTED_FOLDER = "Other"      # catch-all: always exists, cannot be renamed or deleted
FOLDERS = DEFAULT_FOLDERS       # kept for callers that only need the default names
STORED_TZ_OFFSET = "+08:00"   # the collectors store naive timestamps in UTC+8 (model.utc_8)
SEVERITIES = ("critical", "error", "warning", "notice", "info")

# Raw syslog level text (as stored by the collectors) -> normalised severity.
_SEVERITY_BY_LEVEL = {
    "emergency": "critical", "emergencies": "critical", "alert": "critical", "alerts": "critical",
    "critical": "critical", "cricital": "critical",
    "high": "error",
    "medium": "warning",
    "low": "notice",
    "error": "error", "errors": "error",
    "warning": "warning", "warnings": "warning",
    "notice": "notice", "notifications": "notice", "notification": "notice",
    "information": "info", "informational": "info", "debug": "info", "debugging": "info",
}


def _clean_old_folder_rows():
    """The first version stored one row per infra (name == classification). Folders are rows under an infra now."""
    folder_list.query.filter(folder_list.folder_for_outer_layer == folder_list.folder_belongs_to_which_classification).delete(synchronize_session=False)


_folders_ready = False


def ensure_folders():
    """First use: create the default folders under each infra (and make sure 'Other' exists)."""
    global _folders_ready
    if _folders_ready:
        return
    _clean_old_folder_rows()
    for infra in INFRAS:
        rows = folder_list.query.filter_by(folder_belongs_to_which_classification=infra).all()
        have = {r.folder_for_outer_layer for r in rows}
        wanted = DEFAULT_FOLDERS if not rows else ((PROTECTED_FOLDER,) if PROTECTED_FOLDER not in have else ())
        for name in wanted:
            db.session.add(folder_list(folder_for_outer_layer=name, folder_belongs_to_which_classification=infra,
                                       how_many_alert_for_this_folder=0, how_many_alerts_need_to_escalate_to_net=0))
    db.session.commit()
    _folders_ready = True


def folder_names(infra):
    """Folder names of one infra, in display order (Other last)."""
    ensure_folders()
    rows = folder_list.query.filter_by(folder_belongs_to_which_classification=infra).order_by(folder_list.id).all()
    names = [r.folder_for_outer_layer for r in rows]
    return [n for n in names if n != PROTECTED_FOLDER] + ([PROTECTED_FOLDER] if PROTECTED_FOLDER in names else [])


def folder_for_new_device(name, infra):
    """Suggested folder if it exists in that infra, else the catch-all."""
    suggestion = default_folder(name)
    return suggestion if suggestion in folder_names(infra) else PROTECTED_FOLDER


def default_folder(name):
    """Best-guess folder from the device naming convention (BRAVO-BR01, ALPHA-LTM01, BRAVO-OOB2S03_4Y02 ...)."""
    n = (name or "").upper()
    if "LTM" in n:
        return "LTM"
    if re.search(r"(^|-)FW\d", n):
        return "Firewall"
    if "OOB" in n:
        return "OOB"
    if re.search(r"(^|-)(BR|ER)\d", n) and "ER2S" not in n:
        return "Routers"
    if re.search(r"(^|-)(CS|IS|OS)\d|C\d-CS|ER2S|OS2S|IS3S", n):
        return "Switches"
    return "Other"


# ---- per-device alert settings (what the collectors read to decide which log lines become alerts)
# Vendor -> predefine_severity.service_type, and which severities alert by default.
_SERVICE_BY_VENDOR = {"cisco": "cisco", "LTM": "ltm", "fortigate": "fortinet", "paloalto": "paloalto", "arbor": "arbor"}
_DEFAULT_SEVERITIES = {
    "cisco": "Errors,Critical,Alerts,Emergencies", "ltm": "Emergency,Alert,Critical,Error",
    "fortinet": "Emergency,Alert,Critical,Error", "paloalto": "Cricital,High", "arbor": "Alert,Crit,Err",
}
_GENERIC_SEVERITIES = ["Emergency", "Alert", "Critical", "Error", "Warning", "Notice", "Informational", "Debug"]
_GENERIC_DEFAULT = "Emergency,Alert,Critical,Error"


def severity_options(vendor):
    service = _SERVICE_BY_VENDOR.get(vendor)
    rows = predefine_severity.query.filter_by(service_type=service).order_by(predefine_severity.id).all() if service else []
    seen = []
    for r in rows:
        if r.severity_for_the_device not in seen:
            seen.append(r.severity_for_the_device)
    return seen or list(_GENERIC_SEVERITIES)


def default_severities(vendor):
    return _DEFAULT_SEVERITIES.get(_SERVICE_BY_VENDOR.get(vendor), _GENERIC_DEFAULT)


def _folder_label(infra, folder):
    return f"{infra}_{folder}"


def ensure_severity_row(device):
    """Collectors only store a device's alerts when it has a severity row, so every device needs one."""
    row = severity_user_choosen.query.filter_by(device_name=device.host_name).first()
    label = _folder_label(device.deivce_belongs_to_which_folders, device.device_folder or default_folder(device.host_name))
    if row is None:
        db.session.add(severity_user_choosen(device_name=device.host_name, folder_name=label,
                                             severity_that_user_selected=default_severities(device.which_vendor)))
    else:
        row.folder_name = label


_SETTINGS = ((severity_user_choosen, "severity_that_user_selected"), (what_keyword_will_insert_db, "keyword_user_input"),
             (ingore_keyword, "filter_sub_keyword"))


def _other_devices_named(name, except_id):
    return device_list.query.filter(device_list.host_name == name, device_list.id != except_id).count()


def rename_device_settings(old_name, new_name, device_id=None, device_ip=None):
    """A device's rules are stored under its name. If another device still has the old name (e.g. the two
    BRAVO-CS03), the rules are copied to the new name instead of moved, so neither device loses its rules."""
    if old_name == new_name:
        return
    shared = device_id is not None and _other_devices_named(old_name, device_id) > 0
    if device_id is not None and _other_devices_named(new_name, device_id) > 0:
        # that name already has its own rules: do not merge onto it. The old name's rules go away with this device
        # (unless another device still uses the old name) so they do not wait for a future device of that name.
        if not shared:
            if device_ip:                                 # this device's own muted errors (keyed by IP) stay with it
                pause_rule.query.filter(pause_rule.device_ip == device_ip).update({"device_name": new_name}, synchronize_session=False)
            delete_device_settings(old_name)
        return
    for model, _col in (_SETTINGS + ((auto_ack_which_device, None),) if shared else _SETTINGS):
        if shared:
            for row in model.query.filter_by(device_name=old_name).all():
                data = {c.name: getattr(row, c.name) for c in model.__table__.columns if c.name not in ("id", "timestamp")}
                data["device_name"] = new_name
                db.session.add(model(**data))
        else:
            model.query.filter_by(device_name=old_name).update({"device_name": new_name}, synchronize_session=False)
    if not shared:                                    # maintenance windows and muted errors follow the device
        auto_ack_which_device.query.filter_by(device_name=old_name).update({"device_name": new_name}, synchronize_session=False)
        pause_rule.query.filter_by(device_name=old_name).update({"device_name": new_name}, synchronize_session=False)


def delete_device_settings(name):
    if device_list.query.filter_by(host_name=name).count() > 0:   # another device shares the name (and its settings)
        return
    for model, _col in _SETTINGS:
        model.query.filter_by(device_name=name).delete(synchronize_session=False)
    auto_ack_which_device.query.filter_by(device_name=name).delete(synchronize_session=False)
    pause_rule.query.filter_by(device_name=name, device_ip=None).delete(synchronize_session=False)   # IP-keyed mutes go with their device


# ---- keyword rules that span devices ("Login Success" on every device, now and in the future)
_RULE_KINDS = ("ignore", "alert")
_tables_ready = False


def ensure_rule_tables():
    global _tables_ready
    if not _tables_ready:
        keyword_rule.__table__.create(bind=db.engine, checkfirst=True)
        cols = {c["name"] for c in inspect(db.engine).get_columns("keyword_rule")}
        if "vendor" not in cols:                       # table created before vendor scopes existed
            db.session.execute(text("ALTER TABLE keyword_rule ADD COLUMN vendor VARCHAR(32) NULL"))
            db.session.commit()
        _tables_ready = True


def _device_folder_of(d):
    return d.device_folder or default_folder(d.host_name)


def _rule_matches_device(rule, d):
    return ((not rule.infra or rule.infra == d.deivce_belongs_to_which_folders)
            and (not rule.folder or rule.folder == _device_folder_of(d))
            and (not rule.vendor or rule.vendor == d.which_vendor))


def _device_has_keyword(kind, d, keyword):
    if kind == "ignore":
        return ingore_keyword.query.filter_by(device_name=d.host_name, filter_sub_keyword=keyword).first() is not None
    return what_keyword_will_insert_db.query.filter_by(device_name=d.host_name, keyword_user_input=keyword).first() is not None


def _add_device_keyword(kind, d, keyword):
    if _device_has_keyword(kind, d, keyword):
        return False
    if kind == "ignore":
        db.session.add(ingore_keyword(device_name=d.host_name, filter_sub_keyword=keyword))
    else:
        db.session.add(what_keyword_will_insert_db(device_name=d.host_name, device_ip=d.host_address,
                                                   contain_or_not_contain="Match", keyword_user_input=keyword))
    return True


def apply_rules_to_new_device(d):
    """A device added later gets every rule whose scope covers it."""
    ensure_rule_tables()
    for rule in keyword_rule.query.all():
        if _rule_matches_device(rule, d):
            _add_device_keyword(rule.kind, d, rule.keyword)


def _iso(ts):
    return f"{ts.isoformat()}{STORED_TZ_OFFSET}" if ts else None


def severity_of(level):
    return _SEVERITY_BY_LEVEL.get((level or "").strip().lower(), "info")


def _levels_for(severity):
    return [lvl for lvl, sev in _SEVERITY_BY_LEVEL.items() if sev == severity]


def _error(message, status=400):
    return jsonify({"error": message}), status


ESCALATED = "Already Escalated to Net"   # value the old UI stored in all_the_logs.escalate_to_net


def _now():
    """Current time in the zone the collectors store timestamps in (naive UTC+8)."""
    return datetime.utcnow() + timedelta(hours=8)


def _acked_clause():
    return func.coalesce(all_the_logs.alert_acked_or_not, "") == "Acked"


def _paused_clause():
    """Not acknowledged and paused until a time that has not passed yet."""
    return db.and_(~_acked_clause(), all_the_logs.pause_the_alert_until_when.isnot(None),
                   all_the_logs.pause_the_alert_until_when > _now())


def _open_clause():
    """Open = not acknowledged and not currently paused. Every count and list uses this one definition."""
    return db.and_(func.coalesce(all_the_logs.alert_acked_or_not, "") != "Acked",
                   db.or_(all_the_logs.pause_the_alert_until_when.is_(None), all_the_logs.pause_the_alert_until_when <= _now()))


def _is_open(log):
    return (log.alert_acked_or_not or "") != "Acked"


def _is_paused(log):
    return _is_open(log) and bool(log.pause_the_alert_until_when) and log.pause_the_alert_until_when > _now()


def _device_json(d, open_alerts=0):
    return {
        "id": d.id,
        "infra": d.deivce_belongs_to_which_folders,
        "name": d.host_name,
        "ip": d.host_address,
        "vendor": d.which_vendor,
        "folder": d.device_folder or default_folder(d.host_name),
        "open_alerts": open_alerts,
    }


def _alert_json(log, infra_by_ip):
    return {
        "id": log.id,
        "timestamp": _iso(log.timestamp),
        "host_name": log.host_name,
        "host_address": log.host_address,
        "infra": infra_by_ip.get(log.host_address),
        "severity": severity_of(log.log_level),
        "level": log.log_level,
        "message": log.message,
        "service": log.service_type,
        "acked": not _is_open(log),
        "acked_by": log.who_acked_the_alert,
        "keyword": log.which_keyword_is_triggered or None,
        "paused": _is_paused(log),
        "paused_until": _iso(log.pause_the_alert_until_when) if _is_paused(log) else None,
        "paused_by": log.who_paused_the_alert if _is_paused(log) else None,
        "escalated": log.escalate_to_net == ESCALATED,
        "escalated_by": log.who_acked_the_alert if log.escalate_to_net == ESCALATED and _is_open(log) else None,
    }


def _open_alert_counts():
    """{host_address: open alert count}"""
    rows = (
        db.session.query(all_the_logs.host_address, func.count(all_the_logs.id))
        .filter(_open_clause())
        .group_by(all_the_logs.host_address)
        .all()
    )
    return dict(rows)


def _infra_devices():
    return device_list.query.filter(device_list.deivce_belongs_to_which_folders.in_(INFRAS)).all()


def _paused_rows(infra_by_ip, infra):
    ips = [ip for ip, i in infra_by_ip.items() if i == infra]
    cols = (all_the_logs.id, all_the_logs.host_address)
    return db.session.query(*cols).filter(_paused_clause()).filter(all_the_logs.host_address.in_(ips or [""])).all()


# --------------------------------------------------------------------- infras
_last_release = {"at": 0.0}


def _release_ended_mutes():
    """Muted repeats whose mute ended are acknowledged now, not only at the next collector run."""
    from blueprint.collector import expire_muted
    if time.time() - _last_release["at"] < 30:          # polls from every browser: at most every 30 s per process
        return
    _last_release["at"] = time.time()
    try:
        expire_muted()
    except Exception:
        db.session.rollback()


@api.route("/infras")
def list_infras():
    _release_ended_mutes()
    devices = _infra_devices()
    infra_by_ip = {d.host_address: d.deivce_belongs_to_which_folders for d in devices}
    cols = (all_the_logs.id, all_the_logs.host_address, all_the_logs.log_level, all_the_logs.escalate_to_net, all_the_logs.timestamp)
    open_logs = (
        db.session.query(*cols).filter(_open_clause())
        .filter(all_the_logs.host_address.in_(list(infra_by_ip) or [""]))
        .all()
    )
    result = []
    for name in INFRAS:
        logs = [l for l in open_logs if infra_by_ip.get(l.host_address) == name]
        by_sev = Counter(severity_of(l.log_level) for l in logs)
        last = max((l.timestamp for l in logs if l.timestamp), default=None)
        paused_logs = _paused_rows(infra_by_ip, name)
        folders = []
        for f in folder_names(name):
            in_folder = [d for d in devices if d.deivce_belongs_to_which_folders == name and _device_folder_of(d) == f]
            if not in_folder and f == PROTECTED_FOLDER:
                continue
            ips = {d.host_address for d in in_folder}
            flogs = [l for l in logs if l.host_address in ips]
            fpaused = sum(1 for l in paused_logs if l.host_address in ips)
            fsev = Counter(severity_of(l.log_level) for l in flogs)
            folders.append({"name": f, "devices": len(in_folder), "open_alerts": len(flogs), "paused": fpaused,
                            "escalated": sum(1 for l in flogs if l.escalate_to_net == ESCALATED),
                            "by_severity": {s: fsev.get(s, 0) for s in SEVERITIES}})
        result.append({
            "folders": folders,
            "name": name,
            "devices": sum(1 for d in devices if d.deivce_belongs_to_which_folders == name),
            "open_alerts": len(logs),
            "escalated": sum(1 for l in logs if l.escalate_to_net == ESCALATED),
            "paused": len(paused_logs),
            "by_severity": {s: by_sev.get(s, 0) for s in SEVERITIES},
            "last_alert": _iso(last),
            "newest_id": max((l.id for l in logs), default=0),
        })
    return jsonify(result)


@api.route("/folders")
def list_folders():
    ensure_folders()
    infra = request.args.get("infra")
    if infra and infra not in INFRAS:
        return _error(f"infra must be one of {', '.join(INFRAS)}")
    devices = _infra_devices()
    out = []
    for name in INFRAS:
        if infra and name != infra:
            continue
        rows = {r.folder_for_outer_layer: r for r in folder_list.query.filter_by(folder_belongs_to_which_classification=name).all()}
        for f in folder_names(name):
            out.append({"id": rows[f].id, "name": f, "infra": name, "protected": f == PROTECTED_FOLDER,
                        "devices": sum(1 for d in devices if d.deivce_belongs_to_which_folders == name and _device_folder_of(d) == f)})
    return jsonify(out)


def _clean_folder_name(data):
    name = (data.get("name") or "").strip()
    if not name or len(name) > 60:
        return None, "folder name is required (max 60 characters)"
    return name, None


@api.route("/folders", methods=["POST"])
def create_folder():
    ensure_folders()
    data = request.get_json(silent=True) or {}
    infra = (data.get("infra") or "").strip().upper()
    name, msg = _clean_folder_name(data)
    if infra not in INFRAS:
        return _error(f"infra must be one of {', '.join(INFRAS)}")
    if msg:
        return _error(msg)
    if name.lower() in (n.lower() for n in folder_names(infra)):
        return _error(f"{infra} already has a folder called {name}")
    row = folder_list(folder_for_outer_layer=name, folder_belongs_to_which_classification=infra,
                      how_many_alert_for_this_folder=0, how_many_alerts_need_to_escalate_to_net=0)
    db.session.add(row)
    db.session.commit()
    return jsonify({"id": row.id, "name": name, "infra": infra, "protected": False, "devices": 0}), 201


@api.route("/folders/<int:folder_id>", methods=["PUT"])
def rename_folder(folder_id):
    ensure_folders()
    row = db.session.get(folder_list, folder_id)
    if row is None:
        return _error("folder not found", 404)
    old, infra = row.folder_for_outer_layer, row.folder_belongs_to_which_classification
    if old == PROTECTED_FOLDER:
        return _error(f"'{PROTECTED_FOLDER}' cannot be renamed")
    name, msg = _clean_folder_name(request.get_json(silent=True) or {})
    if msg:
        return _error(msg)
    if name.lower() != old.lower() and name.lower() in (n.lower() for n in folder_names(infra)):
        return _error(f"{infra} already has a folder called {name}")
    row.folder_for_outer_layer = name
    for d in device_list.query.filter_by(deivce_belongs_to_which_folders=infra, device_folder=old).all():
        d.device_folder = name
        ensure_severity_row(d)
    keyword_rule.query.filter_by(infra=infra, folder=old).update({"folder": name}, synchronize_session=False)
    db.session.commit()
    return jsonify({"id": row.id, "name": name, "infra": infra})


@api.route("/folders/<int:folder_id>", methods=["DELETE"])
def delete_folder(folder_id):
    """Devices in the folder move to 'Other'; the folder row is removed."""
    ensure_folders()
    row = db.session.get(folder_list, folder_id)
    if row is None:
        return _error("folder not found", 404)
    name, infra = row.folder_for_outer_layer, row.folder_belongs_to_which_classification
    if name == PROTECTED_FOLDER:
        return _error(f"'{PROTECTED_FOLDER}' cannot be deleted")
    moved = 0
    for d in device_list.query.filter_by(deivce_belongs_to_which_folders=infra, device_folder=name).all():
        d.device_folder = PROTECTED_FOLDER
        ensure_severity_row(d)
        moved += 1
    keyword_rule.query.filter_by(infra=infra, folder=name).delete(synchronize_session=False)
    db.session.delete(row)
    db.session.commit()
    return jsonify({"deleted": name, "devices_moved_to": PROTECTED_FOLDER, "moved": moved})


# -------------------------------------------------------------------- devices
@api.route("/devices")
def list_devices():
    infra = request.args.get("infra")
    folder = request.args.get("folder")
    if infra and infra not in INFRAS:
        return _error(f"infra must be one of {', '.join(INFRAS)}")
    counts = _open_alert_counts()
    q = device_list.query.filter(device_list.deivce_belongs_to_which_folders.in_([infra] if infra else INFRAS))
    devices = sorted(q.all(), key=lambda d: (d.deivce_belongs_to_which_folders, _ip_key(d.host_address)))
    out = [_device_json(d, counts.get(d.host_address, 0)) for d in devices]
    return jsonify([d for d in out if not folder or d["folder"] == folder])


def _ip_key(ip):
    try:
        return int(ipaddress.ip_address(ip))
    except ValueError:
        return 0


def _validated_device_payload(data, current=None):
    """Return (clean, error). `current` is the existing row on update."""
    infra = (data.get("infra") or "").strip().upper()
    name = (data.get("name") or "").strip()
    ip = (data.get("ip") or "").strip()
    vendor = (data.get("vendor") or "").strip() or None
    if infra not in INFRAS:
        return None, f"infra must be one of {', '.join(INFRAS)}"
    folder = (data.get("folder") or "").strip() or folder_for_new_device(name, infra)
    if folder not in folder_names(infra):
        return None, f"folder must be one of {', '.join(folder_names(infra))}"
    if not name or len(name) > 100:
        return None, "device name is required (max 100 characters)"
    try:
        ip = str(ipaddress.ip_address(ip))
    except ValueError:
        return None, "IP address is not valid"
    clash = device_list.query.filter(device_list.host_address == ip)
    if current is not None:
        clash = clash.filter(device_list.id != current.id)
    if clash.first():
        return None, f"IP {ip} is already registered"
    return {"infra": infra, "name": name, "ip": ip, "vendor": vendor, "folder": folder}, None


@api.route("/devices", methods=["POST"])
def create_device():
    clean, err = _validated_device_payload(request.get_json(silent=True) or {})
    if err:
        return _error(err)
    d = device_list(
        host_name=clean["name"], host_address=clean["ip"],
        deivce_belongs_to_which_folders=clean["infra"], which_vendor=clean["vendor"], device_folder=clean["folder"],
    )
    db.session.add(d)
    db.session.flush()
    ensure_severity_row(d)
    apply_rules_to_new_device(d)
    db.session.commit()
    return jsonify(_device_json(d)), 201


@api.route("/devices/<int:device_id>", methods=["PUT"])
def update_device(device_id):
    d = db.session.get(device_list, device_id)
    if d is None:
        return _error("device not found", 404)
    clean, err = _validated_device_payload(request.get_json(silent=True) or {}, current=d)
    if err:
        return _error(err)
    old_name, old_ip = d.host_name, d.host_address
    d.host_name, d.host_address = clean["name"], clean["ip"]
    if (old_ip, old_name) != (d.host_address, d.host_name):          # alerts are matched to devices by IP
        all_the_logs.query.filter(all_the_logs.host_address == old_ip).update(
            {"host_address": d.host_address, "host_name": d.host_name}, synchronize_session=False)
        if old_ip != d.host_address:                                 # muted errors are keyed by IP
            muting.ensure_table()
            pause_rule.query.filter(pause_rule.device_ip == old_ip).update({"device_ip": d.host_address}, synchronize_session=False)
    d.deivce_belongs_to_which_folders, d.which_vendor = clean["infra"], clean["vendor"]
    d.device_folder = clean["folder"]
    rename_device_settings(old_name, d.host_name, d.id, d.host_address)
    ensure_severity_row(d)
    db.session.commit()
    return jsonify(_device_json(d))


@api.route("/devices/<int:device_id>", methods=["DELETE"])
def delete_device(device_id):
    d = db.session.get(device_list, device_id)
    if d is None:
        return _error("device not found", 404)
    name = d.host_name
    muting.ensure_table()
    pause_rule.query.filter(pause_rule.device_ip == d.host_address).delete(synchronize_session=False)   # a later device reusing the IP must not inherit the mutes
    db.session.delete(d)
    db.session.flush()
    delete_device_settings(name)
    db.session.commit()
    return "", 204




@api.route("/rules")
def list_rules():
    """Every ALPHA/BRAVO device with the alert rules that apply to it (one call, for the Alert rules page)."""
    devices = _infra_devices()
    severities = {r.device_name: [x for x in (r.severity_that_user_selected or "").split(",") if x]
                  for r in severity_user_choosen.query.all()}
    keywords, ignores = {}, {}
    for k in what_keyword_will_insert_db.query.order_by(what_keyword_will_insert_db.id).all():
        keywords.setdefault(k.device_name, []).append({"id": k.id, "keyword": k.keyword_user_input})
    for k in ingore_keyword.query.order_by(ingore_keyword.id).all():
        ignores.setdefault(k.device_name, []).append({"id": k.id, "keyword": k.filter_sub_keyword})

    def order(d):
        names = folder_names(d.deivce_belongs_to_which_folders)
        folder = _device_folder_of(d)
        return (INFRAS.index(d.deivce_belongs_to_which_folders), names.index(folder) if folder in names else len(names), _ip_key(d.host_address))

    counts = _open_alert_counts()
    options = {}

    def options_for(vendor):
        if vendor not in options:
            options[vendor] = severity_options(vendor)
        return options[vendor]

    return jsonify([
        {**_device_json(d, counts.get(d.host_address, 0)), "severities": severities.get(d.host_name, []),
         "severity_options": options_for(d.which_vendor),
         "keywords": keywords.get(d.host_name, []), "ignore": ignores.get(d.host_name, [])}
        for d in sorted(devices, key=order)
    ])




# ----------------------------------------------------------------- auto-ack
def _parse_window(data):
    try:
        start = datetime.strptime((data.get("start") or "").strip(), "%Y-%m-%d %H:%M")
        end = datetime.strptime((data.get("end") or "").strip(), "%Y-%m-%d %H:%M")
    except ValueError:
        return None, None, "start and end must look like 2026-10-15 09:30"
    if end <= start:
        return None, None, "the end must be after the start"
    return start, end, None


def _window_json(w, device):
    now = _now()
    state = "active" if w.auto_ack_start_time <= now <= w.auto_ack_end_time else ("upcoming" if w.auto_ack_start_time > now else "ended")
    return {"id": w.id, "device_name": w.device_name, "device_id": device.id if device else None,
            "infra": device.deivce_belongs_to_which_folders if device else None,
            "folder": _device_folder_of(device) if device else None,
            "start": _iso(w.auto_ack_start_time), "end": _iso(w.auto_ack_end_time), "state": state}


def autoack_open_alerts(device, start, end):
    """Acknowledge open alerts of a device whose timestamp falls inside the window (as the old version did)."""
    return (all_the_logs.query
            .filter(all_the_logs.host_address == device.host_address, _open_clause(),
                    all_the_logs.timestamp >= start, all_the_logs.timestamp <= end)
            .update({"alert_acked_or_not": "Acked", "who_acked_the_alert": "auto_acked",
                     "insert_by_which_condition": "caseE_auto_acked_due_to_match_ack_the_whole_device"},
                    synchronize_session=False))


@api.route("/auto-ack")
def list_auto_ack():
    by_name = {}
    for d in _infra_devices():
        by_name.setdefault(d.host_name, d)
    rows = auto_ack_which_device.query.order_by(auto_ack_which_device.auto_ack_start_time.desc(), auto_ack_which_device.id.desc()).all()
    out = [_window_json(w, by_name.get(w.device_name)) for w in rows if w.device_name in by_name]
    return jsonify(out)


@api.route("/auto-ack", methods=["POST"])
def add_auto_ack():
    data = request.get_json(silent=True) or {}
    ids = data.get("device_ids")
    if not isinstance(ids, list) or not ids or not all(isinstance(i, int) for i in ids):
        return _error("device_ids must be a non-empty list of device ids")
    start, end, msg = _parse_window(data)
    if msg:
        return _error(msg)
    devices = device_list.query.filter(device_list.id.in_(ids)).all()
    if len(devices) != len(set(ids)):
        return _error("one or more devices were not found", 404)
    created, acked, seen = 0, 0, set()
    for d in devices:
        if d.host_name in seen:
            continue
        seen.add(d.host_name)
        exists = auto_ack_which_device.query.filter_by(device_name=d.host_name, auto_ack_start_time=start, auto_ack_end_time=end).first()
        if not exists:
            db.session.add(auto_ack_which_device(device_name=d.host_name, auto_ack_start_time=start, auto_ack_end_time=end))
            created += 1
        acked += autoack_open_alerts(d, start, end)
    db.session.commit()
    return jsonify({"devices": len(seen), "created": created, "auto_acked": acked}), 201


@api.route("/auto-ack/<int:window_id>", methods=["DELETE"])
def delete_auto_ack(window_id):
    row = db.session.get(auto_ack_which_device, window_id)
    if row is None:
        return _error("auto-ack window not found", 404)
    db.session.delete(row)
    db.session.commit()
    return "", 204


# ------------------------------------------------- keywords across devices
def _scope_label(rule):
    where = f"{rule.infra} / {rule.folder}" if rule.infra and rule.folder else (rule.infra or "")
    if rule.vendor:
        return f"{where + ' ' if where else 'All '}{rule.vendor} devices"
    return where or "All devices"


@api.route("/keyword-summary")
def keyword_summary():
    """Every keyword in use (per kind) with the devices it applies to and the scope it was created with."""
    ensure_rule_tables()
    devices = _infra_devices()
    by_name = {}
    for d in devices:
        by_name.setdefault(d.host_name, d)
    rows = {}
    for kind, model, attr in (("ignore", ingore_keyword, "filter_sub_keyword"), ("alert", what_keyword_will_insert_db, "keyword_user_input")):
        for r in model.query.order_by(model.id).all():
            d = by_name.get(r.device_name)
            kw = getattr(r, attr)
            if d is None or not kw:
                continue          # rules of decommissioned devices are not shown
            entry = rows.setdefault((kind, kw), {"kind": kind, "keyword": kw, "devices": [], "rule": None})
            entry["devices"].append({"id": d.id, "name": d.host_name, "infra": d.deivce_belongs_to_which_folders, "folder": _device_folder_of(d)})
    for rule in keyword_rule.query.order_by(keyword_rule.id).all():
        entry = rows.setdefault((rule.kind, rule.keyword), {"kind": rule.kind, "keyword": rule.keyword, "devices": [], "rule": None})
        scopes = entry.setdefault("scopes", [])
        scopes.append(_scope_label(rule))
        entry["rule"] = {"id": rule.id, "scope": "; ".join(scopes), "infra": rule.infra, "folder": rule.folder, "vendor": rule.vendor}
    total = len(by_name)
    out = []
    for e in rows.values():
        e["device_count"] = len(e["devices"])
        e["all_devices"] = e["device_count"] >= total > 0
        out.append(e)
    out.sort(key=lambda e: (e["kind"] != "ignore", -e["device_count"], e["keyword"].lower()))
    return jsonify({"total_devices": total, "keywords": out})


def apply_keyword_rule(kind, keyword, infra=None, folder=None, vendor=None):
    """Create (or reuse) a rule and put it on every device it covers. The keyword is used exactly as given
    (spaces matter: ' ha ' is not 'ha'). Returns a summary dict. Caller commits nothing else."""
    ensure_rule_tables()
    rule = keyword_rule.query.filter_by(kind=kind, keyword=keyword, infra=infra, folder=folder, vendor=vendor).first()
    if rule is None:
        rule = keyword_rule(kind=kind, keyword=keyword, infra=infra, folder=folder, vendor=vendor)
        db.session.add(rule)
    targets = [d for d in _infra_devices() if _rule_matches_device(rule, d)]
    seen, added = set(), 0
    for d in targets:
        if d.host_name in seen:
            continue
        seen.add(d.host_name)
        added += _add_device_keyword(kind, d, keyword)
    auto_acked = 0
    if kind == "ignore" and targets:
        # like the old version: alerts already open that contain an ignored word are cleared too
        ips = [d.host_address for d in targets]
        # the database match is a cheap pre-filter (escaped, but case-insensitive); the exact, case-sensitive test
        # is the same one the collector uses
        for r in (all_the_logs.query
                  .filter(all_the_logs.host_address.in_(ips), _open_clause(), all_the_logs.message.contains(keyword, autoescape=True))
                  .all()):
            if keyword in (r.message or ""):
                r.alert_acked_or_not, r.who_acked_the_alert = "Acked", "auto_acked (ignore keyword)"
                auto_acked += 1
    db.session.commit()
    return {"keyword": keyword, "kind": kind, "scope": _scope_label(rule), "devices": len(seen),
            "added": added, "already_had": len(seen) - added, "auto_acked": auto_acked}


@api.route("/keyword-rules", methods=["POST"])
def add_keyword_rule():
    ensure_rule_tables()
    data = request.get_json(silent=True) or {}
    kind = data.get("kind")
    keyword, msg = _clean_keyword(data)
    infra = (data.get("infra") or "").strip().upper() or None
    folder = (data.get("folder") or "").strip() or None
    vendor = (data.get("vendor") or "").strip() or None
    if kind not in _RULE_KINDS:
        return _error("kind must be 'ignore' or 'alert'")
    if msg:
        return _error(msg)
    if infra and infra not in INFRAS:
        return _error(f"infra must be one of {', '.join(INFRAS)}")
    if folder and not infra:
        return _error("choose an infra when you choose a folder")
    if folder and folder not in folder_names(infra):
        return _error(f"folder {folder} does not exist in {infra}")
    if vendor and vendor not in {d.which_vendor for d in _infra_devices() if d.which_vendor}:
        return _error(f"no device has vendor {vendor}")
    return jsonify(apply_keyword_rule(kind, keyword, infra, folder, vendor)), 201


@api.route("/keyword-rules/remove", methods=["POST"])
def remove_keyword_rule():
    """Remove a keyword from every device (and its rule, so future devices don't get it)."""
    ensure_rule_tables()
    data = request.get_json(silent=True) or {}
    kind = data.get("kind")
    keyword = data.get("keyword") if isinstance(data.get("keyword"), str) else ""
    if kind not in _RULE_KINDS or not keyword.strip():        # spaces are part of a keyword (' ha '): do not strip it
        return _error("kind and keyword are required")
    keyword_rule.query.filter_by(kind=kind, keyword=keyword).delete(synchronize_session=False)
    model, attr = (ingore_keyword, "filter_sub_keyword") if kind == "ignore" else (what_keyword_will_insert_db, "keyword_user_input")
    removed = model.query.filter(getattr(model, attr) == keyword).delete(synchronize_session=False)
    db.session.commit()
    return jsonify({"removed_from": removed})


def _keyword_device_args():
    """(kind, keyword exactly as stored, device, error) from the request body of the per-keyword device endpoints."""
    data = request.get_json(silent=True) or {}
    kind, keyword = data.get("kind"), data.get("keyword")
    if kind not in _RULE_KINDS or not isinstance(keyword, str) or not keyword.strip() or len(keyword) > 200:
        return None, None, None, _error("kind and keyword are required (at most 200 characters)")
    did = data.get("device_id")
    d = db.session.get(device_list, did) if type(did) is int and 0 < did < 2 ** 31 else None
    if d is None or d.deivce_belongs_to_which_folders not in INFRAS:
        return None, None, None, _error("device not found", 404)
    return kind, keyword, d, None


@api.route("/keyword-devices", methods=["POST"])
def add_keyword_device():
    """Put one existing keyword on one more device (the device list of a keyword is editable)."""
    kind, keyword, d, err = _keyword_device_args()
    if err:
        return err
    added = _add_device_keyword(kind, d, keyword)
    auto_acked = 0
    if added and kind == "ignore":                      # like a new ignore rule: matching open alerts of this device are cleared
        ips = [x.host_address for x in device_list.query.filter_by(host_name=d.host_name).all()]     # devices sharing a name share the keyword
        for r in all_the_logs.query.filter(all_the_logs.host_address.in_(ips), _open_clause(),
                                           all_the_logs.message.contains(keyword, autoescape=True)).all():
            if keyword in (r.message or ""):
                r.alert_acked_or_not, r.who_acked_the_alert = "Acked", "auto_acked (ignore keyword)"
                auto_acked += 1
    db.session.commit()
    return jsonify({"keyword": keyword, "kind": kind, "device": d.host_name, "added": bool(added), "auto_acked": auto_acked})


@api.route("/keyword-devices/remove", methods=["POST"])
def remove_keyword_device():
    """Take one keyword off one device. The keyword's rule is kept, so it still applies to devices added later."""
    kind, keyword, d, err = _keyword_device_args()
    if err:
        return err
    model, attr = (ingore_keyword, "filter_sub_keyword") if kind == "ignore" else (what_keyword_will_insert_db, "keyword_user_input")
    removed = model.query.filter(model.device_name == d.host_name, getattr(model, attr) == keyword).delete(synchronize_session=False)
    db.session.commit()
    return jsonify({"keyword": keyword, "kind": kind, "device": d.host_name, "removed": removed})


# ------------------------------------------------------- per-device settings
def _device_or_404(device_id):
    d = db.session.get(device_list, device_id)
    return d, (None if d else _error("device not found", 404))


def _clean_keyword(data):
    kw = (data.get("keyword") or "").strip()
    if not kw or len(kw) > 200:
        return None, "keyword is required (max 200 characters)"
    return kw, None


@api.route("/devices/<int:device_id>/settings")
def device_settings(device_id):
    d, err = _device_or_404(device_id)
    if err:
        return err
    sev = severity_user_choosen.query.filter_by(device_name=d.host_name).first()
    keywords = what_keyword_will_insert_db.query.filter_by(device_name=d.host_name).order_by(what_keyword_will_insert_db.id).all()
    ignores = ingore_keyword.query.filter_by(device_name=d.host_name).order_by(ingore_keyword.id).all()
    return jsonify({
        "device": _device_json(d),
        "severity_options": severity_options(d.which_vendor),
        "severities": [x for x in (sev.severity_that_user_selected or "").split(",") if x] if sev else [],
        "keywords": [{"id": k.id, "keyword": k.keyword_user_input} for k in keywords],
        "ignore": [{"id": k.id, "keyword": k.filter_sub_keyword} for k in ignores],
    })


@api.route("/devices/<int:device_id>/severities", methods=["PUT"])
def set_device_severities(device_id):
    d, err = _device_or_404(device_id)
    if err:
        return err
    chosen = (request.get_json(silent=True) or {}).get("severities")
    options = severity_options(d.which_vendor)
    if not isinstance(chosen, list) or not all(c in options for c in chosen):
        return _error(f"severities must be a list drawn from: {', '.join(options)}")
    ensure_severity_row(d)
    row = severity_user_choosen.query.filter_by(device_name=d.host_name).first()
    row.severity_that_user_selected = ",".join(c for c in options if c in chosen)   # keep vocabulary order
    db.session.commit()
    return jsonify({"severities": [c for c in options if c in chosen]})


@api.route("/devices/<int:device_id>/keywords", methods=["POST"])
def add_keyword(device_id):
    d, err = _device_or_404(device_id)
    if err:
        return err
    kw, msg = _clean_keyword(request.get_json(silent=True) or {})
    if msg:
        return _error(msg)
    if what_keyword_will_insert_db.query.filter_by(device_name=d.host_name, keyword_user_input=kw).first():
        return _error("that keyword is already set for this device")
    row = what_keyword_will_insert_db(device_name=d.host_name, device_ip=d.host_address,
                                      contain_or_not_contain="Match", keyword_user_input=kw)
    db.session.add(row)
    db.session.commit()
    return jsonify({"id": row.id, "keyword": kw}), 201


@api.route("/keywords/<int:keyword_id>", methods=["DELETE"])
def delete_keyword(keyword_id):
    row = db.session.get(what_keyword_will_insert_db, keyword_id)
    if row is None:
        return _error("keyword not found", 404)
    db.session.delete(row)
    db.session.commit()
    return "", 204


@api.route("/devices/<int:device_id>/ignore", methods=["POST"])
def add_ignore(device_id):
    d, err = _device_or_404(device_id)
    if err:
        return err
    kw, msg = _clean_keyword(request.get_json(silent=True) or {})
    if msg:
        return _error(msg)
    if ingore_keyword.query.filter_by(device_name=d.host_name, filter_sub_keyword=kw).first():
        return _error("that keyword is already ignored for this device")
    row = ingore_keyword(device_name=d.host_name, filter_sub_keyword=kw)
    db.session.add(row)
    db.session.commit()
    return jsonify({"id": row.id, "keyword": kw}), 201


@api.route("/ignore/<int:ignore_id>", methods=["DELETE"])
def delete_ignore(ignore_id):
    row = db.session.get(ingore_keyword, ignore_id)
    if row is None:
        return _error("keyword not found", 404)
    db.session.delete(row)
    db.session.commit()
    return "", 204


# --------------------------------------------------------------------- alerts
@api.route("/alerts")
def list_alerts():
    _release_ended_mutes()
    infra = request.args.get("infra")
    status = request.args.get("status", "open")          # open | paused | acked | all
    escalated_only = request.args.get("escalated") in ("1", "true")
    severity = request.args.get("severity")
    device_id = request.args.get("device_id", type=int)
    folder = request.args.get("folder")
    since_id = request.args.get("since_id", type=int)      # only alerts newer than this id
    keyword_only = request.args.get("keyword") in ("1", "true")
    text = (request.args.get("q") or "").strip()
    limit = min(max(request.args.get("limit", 100, type=int), 1), 500)
    offset = max(request.args.get("offset", 0, type=int), 0)

    if infra and infra not in INFRAS:
        return _error(f"infra must be one of {', '.join(INFRAS)}")
    if severity and severity not in SEVERITIES:
        return _error(f"severity must be one of {', '.join(SEVERITIES)}")
    if status not in ("open", "paused", "acked", "all"):
        return _error("status must be open, paused, acked or all")

    devices = _infra_devices()
    infra_by_ip = {d.host_address: d.deivce_belongs_to_which_folders for d in devices}
    ips = [d.host_address for d in devices
           if (not infra or d.deivce_belongs_to_which_folders == infra) and (not device_id or d.id == device_id)
           and (not folder or (d.device_folder or default_folder(d.host_name)) == folder)]

    q = all_the_logs.query.filter(all_the_logs.host_address.in_(ips or [""]))
    if status == "open":
        q = q.filter(_open_clause())
    elif status == "paused":
        q = q.filter(_paused_clause())
    elif status == "acked":
        q = q.filter(_acked_clause())
    if escalated_only:
        q = q.filter(all_the_logs.escalate_to_net == ESCALATED)
    if since_id is not None:
        q = q.filter(all_the_logs.id > since_id)
    if keyword_only:
        q = q.filter(func.coalesce(all_the_logs.which_keyword_is_triggered, "") != "")
    if severity:
        q = q.filter(func.lower(all_the_logs.log_level).in_(_levels_for(severity)))
    if text:
        like = f"%{text}%"
        q = q.filter(db.or_(all_the_logs.message.like(like), all_the_logs.host_name.like(like)))

    total = q.count()
    rows = q.order_by(all_the_logs.timestamp.desc(), all_the_logs.id.desc()).offset(offset).limit(limit).all()
    return jsonify({"total": total, "items": [_alert_json(r, infra_by_ip) for r in rows]})


@api.route("/alerts/ack", methods=["POST"])
def ack_alerts():
    data = request.get_json(silent=True) or {}
    ids = data.get("ids")
    if not isinstance(ids, list) or not ids or not all(isinstance(i, int) for i in ids):
        return _error("ids must be a non-empty list of alert ids")
    who = _who(data)
    updated = (
        all_the_logs.query.filter(all_the_logs.id.in_(ids), ~_acked_clause())      # never overwrite who acked first
        .update({"alert_acked_or_not": "Acked", "who_acked_the_alert": who}, synchronize_session=False)
    )
    db.session.commit()
    return jsonify({"acked": updated})


def _alert_ids(data):
    ids = data.get("ids")
    if not isinstance(ids, list) or not ids or not all(isinstance(i, int) for i in ids):
        return None
    return ids


def _who(data):
    return getattr(g, "actor", None) or (data.get("who") or "").strip()[:100] or "web"


@api.route("/alerts/pause", methods=["POST"])
def pause_alerts():
    """Hide alerts from the open list until a future time (YYYY-MM-DD HH:MM, in the stored UTC+8 zone)."""
    data = request.get_json(silent=True) or {}
    ids = _alert_ids(data)
    if ids is None:
        return _error("ids must be a non-empty list of alert ids")
    try:
        until = datetime.strptime((data.get("until") or "").strip(), "%Y-%m-%d %H:%M")
    except ValueError:
        return _error("until must look like 2026-10-15 09:30")
    if until <= _now():
        return _error("Choose a time in the future")
    who = _who(data)
    rows = all_the_logs.query.filter(all_the_logs.id.in_(ids), ~_acked_clause()).all()
    mute = data.get("mute_same", True) is not False          # default: also mute the same error
    muted_rules, also, seen = 0, 0, set()
    for r in rows:
        r.pause_the_alert_until_when, r.who_paused_the_alert = until, who
        r.paused_by_which_folder = (data.get("folder") or "")[:100] or None
        if mute:
            key = (r.host_address, muting.signature(r.message))
            if key not in seen and len(seen) < MAX_MUTE_RULES_PER_REQUEST:
                seen.add(key)
                muting.upsert_rule(r.host_name, r.host_address, key[1], r.message, until, who)
                muted_rules += 1
    if mute and seen:
        # the other open alerts that are the same error on the same device are paused too
        chosen_ids = {r.id for r in rows}
        for ip in {k[0] for k in seen}:
            for o in all_the_logs.query.filter(all_the_logs.host_address == ip, _open_clause()).all():
                if o.id not in chosen_ids and (ip, muting.signature(o.message)) in seen:
                    o.pause_the_alert_until_when, o.who_paused_the_alert = until, who
                    also += 1
    db.session.commit()
    return jsonify({"paused": len(rows) + also, "also_paused": also, "until": _iso(until), "muted_rules": muted_rules})


def _first_by_name(devices):
    out = {}
    for d in devices:
        out.setdefault(d.host_name, d)
    return out


def _device_for_rule(r, by_ip, by_name):
    return by_ip.get(r.device_ip) if r.device_ip else by_name.get(r.device_name)


@api.route("/pause-rules")
def list_pause_rules():
    """Errors currently muted ('same error from this device') and how many paused alerts each one covers."""
    muting.ensure_table()
    devices = _infra_devices()
    by_ip = {d.host_address: d for d in devices}
    by_name = _first_by_name(devices)
    rules = pause_rule.query.filter(pause_rule.until > _now()).order_by(pause_rule.id.desc()).all()
    counts = {}                                       # signatures of each device's paused alerts, computed once per device
    for ip in {(_device_for_rule(r, by_ip, by_name) or None) and _device_for_rule(r, by_ip, by_name).host_address for r in rules} - {None}:
        counts[ip] = Counter(muting.signature(m) for (m,) in db.session.query(all_the_logs.message).filter(all_the_logs.host_address == ip, _paused_clause()))
    out = []
    for r in rules:
        d = _device_for_rule(r, by_ip, by_name)
        if d is None:
            continue
        out.append({"id": r.id, "device_id": d.id, "device_name": d.host_name, "infra": d.deivce_belongs_to_which_folders,
                    "folder": _device_folder_of(d), "sample": r.sample, "signature": r.signature, "until": _iso(r.until),
                    "who": r.who, "created": _iso(r.created), "covers_alerts": counts.get(d.host_address, Counter()).get(r.signature, 0)})
    return jsonify(out)


@api.route("/pause-rules/<int:rule_id>", methods=["DELETE"])
def delete_pause_rule(rule_id):
    """Stop muting an error. With ?unpause=1 the alerts already paused for it come back to the open list too."""
    muting.ensure_table()
    r = db.session.get(pause_rule, rule_id)
    if r is None:
        return _error("muted error not found", 404)
    unpaused = 0
    if request.args.get("unpause") in ("1", "true"):
        devices = _infra_devices()
        d = _device_for_rule(r, {x.host_address: x for x in devices}, _first_by_name(devices))
        if d is not None:
            for a in all_the_logs.query.filter(all_the_logs.host_address == d.host_address, _paused_clause()).all():
                if muting.signature(a.message) == r.signature:
                    a.pause_the_alert_until_when, a.who_paused_the_alert, a.paused_by_which_folder = None, None, None
                    unpaused += 1
    db.session.delete(r)
    db.session.commit()
    return jsonify({"released": True, "unpaused": unpaused})


@api.route("/alerts/unpause", methods=["POST"])
def unpause_alerts():
    ids = _alert_ids(request.get_json(silent=True) or {})
    if ids is None:
        return _error("ids must be a non-empty list of alert ids")
    rows = all_the_logs.query.filter(all_the_logs.id.in_(ids)).all()
    removed, changed, handled = 0, 0, set()
    for r in rows:                                   # unpausing also stops muting that same error on that device
        sig = muting.signature(r.message)
        n = muting.delete_rules(r.host_name, r.host_address, sig)
        removed += n
        if r.pause_the_alert_until_when is not None and r.pause_the_alert_until_when > _now() and r.alert_acked_or_not != "Acked":
            changed += 1
        r.pause_the_alert_until_when, r.who_paused_the_alert, r.paused_by_which_folder = None, None, None
        if n and (r.host_address, sig) not in handled:   # repeats already stored as 'muted' come back with the rule
            handled.add((r.host_address, sig))
            for o in all_the_logs.query.filter(all_the_logs.host_address == r.host_address,
                                               all_the_logs.who_paused_the_alert.like("muted (same error%"), _paused_clause()).all():
                if muting.signature(o.message) == sig:
                    o.pause_the_alert_until_when, o.who_paused_the_alert, o.paused_by_which_folder = None, None, None
                    changed += 1
    db.session.commit()
    return jsonify({"unpaused": changed, "rules_removed": removed})


@api.route("/alerts/escalate", methods=["POST"])
def escalate_alerts():
    """Mark alerts as handed over to the network team (NET). Does not acknowledge them."""
    data = request.get_json(silent=True) or {}
    ids = _alert_ids(data)
    if ids is None:
        return _error("ids must be a non-empty list of alert ids")
    updated = all_the_logs.query.filter(all_the_logs.id.in_(ids), ~_acked_clause(),
                                        func.coalesce(all_the_logs.escalate_to_net, "") != ESCALATED).update(
        {"escalate_to_net": ESCALATED, "who_acked_the_alert": _who(data)}, synchronize_session=False)
    db.session.commit()
    return jsonify({"escalated": updated})


@api.route("/alerts/unescalate", methods=["POST"])
def unescalate_alerts():
    ids = _alert_ids(request.get_json(silent=True) or {})
    if ids is None:
        return _error("ids must be a non-empty list of alert ids")
    updated = all_the_logs.query.filter(all_the_logs.id.in_(ids), ~_acked_clause(),
                                        all_the_logs.escalate_to_net == ESCALATED).update(
        {"escalate_to_net": "escalate", "who_acked_the_alert": None}, synchronize_session=False)
    db.session.commit()
    return jsonify({"unescalated": updated})


# ======================================================================= audit log
# Every change made through the API needs a person's name (X-User header) and is written to the audit log.
MUTATING = ("POST", "PUT", "DELETE")
MAX_MUTE_RULES_PER_REQUEST = 100

ACTIONS = {   # endpoint -> (code, label shown on the Log page)
    "create_device": ("device.add", "Device added"), "update_device": ("device.edit", "Device edited"),
    "delete_device": ("device.remove", "Device removed"), "set_device_severities": ("severity.change", "Severity changed"),
    "add_keyword": ("keyword.add", "Keyword added"), "delete_keyword": ("keyword.remove", "Keyword removed"),
    "add_ignore": ("ignore.add", "Ignore keyword added"), "delete_ignore": ("ignore.remove", "Ignore keyword removed"),
    "add_keyword_rule": ("keyword.rule", "Keyword applied to devices"), "remove_keyword_rule": ("keyword.rule.remove", "Keyword removed everywhere"),
    "add_keyword_device": ("keyword.device.add", "Keyword added to a device"), "remove_keyword_device": ("keyword.device.remove", "Keyword removed from a device"),
    "create_folder": ("folder.add", "Folder added"), "rename_folder": ("folder.rename", "Folder renamed"),
    "delete_folder": ("folder.remove", "Folder deleted"), "add_auto_ack": ("autoack.add", "Auto-ack started"),
    "delete_auto_ack": ("autoack.remove", "Auto-ack removed"), "ack_alerts": ("alert.ack", "Alerts acknowledged"),
    "pause_alerts": ("alert.pause", "Alerts paused"), "unpause_alerts": ("alert.unpause", "Alerts unpaused"),
    "delete_pause_rule": ("pause.rule.remove", "Muted error released"), "escalate_alerts": ("alert.escalate", "Escalated to NET"), "unescalate_alerts": ("alert.unescalate", "Escalation undone"),
}
ACTION_LABELS = {code: label for code, label in ACTIONS.values()}
ACTION_LABELS["collector.run"] = "Logs pulled manually"


def _device_snapshot(d):
    return {"name": d.host_name, "ip": d.host_address, "infra": d.deivce_belongs_to_which_folders,
            "folder": _device_folder_of(d), "vendor": d.which_vendor}


def _alerts_snapshot(ids):
    rows = all_the_logs.query.filter(all_the_logs.id.in_(ids[:2000])).all()
    names = Counter(r.host_name for r in rows)
    return {"count": len(rows), "devices": names.most_common(3), "more_devices": max(0, len(names) - 3),
            "samples": [{"id": r.id, "device": r.host_name, "message": (r.message or "")[:90]} for r in rows[:3]]}


def _snapshot_before():
    """What is about to change, captured before the change (so a deletion can still say what was deleted)."""
    ep = (request.endpoint or "").split(".")[-1]
    va, body, b = request.view_args or {}, request.get_json(silent=True) or {}, {}
    if ep in ("update_device", "delete_device", "set_device_severities", "add_keyword", "add_ignore"):
        d = db.session.get(device_list, va["device_id"])
        b["device"] = _device_snapshot(d) if d else None
        if d and ep == "set_device_severities":
            row = severity_user_choosen.query.filter_by(device_name=d.host_name).first()
            b["severities"] = [x for x in ((row.severity_that_user_selected if row else "") or "").split(",") if x]
    elif ep == "delete_keyword":
        r = db.session.get(what_keyword_will_insert_db, va["keyword_id"])
        b["keyword"], b["device_name"] = (r.keyword_user_input, r.device_name) if r else (None, None)
    elif ep == "delete_ignore":
        r = db.session.get(ingore_keyword, va["ignore_id"])
        b["keyword"], b["device_name"] = (r.filter_sub_keyword, r.device_name) if r else (None, None)
    elif ep in ("rename_folder", "delete_folder"):
        r = db.session.get(folder_list, va["folder_id"])
        b["folder"] = {"name": r.folder_for_outer_layer, "infra": r.folder_belongs_to_which_classification} if r else None
    elif ep == "delete_auto_ack":
        r = db.session.get(auto_ack_which_device, va["window_id"])
        b["window"] = {"device": r.device_name, "start": _iso(r.auto_ack_start_time), "end": _iso(r.auto_ack_end_time)} if r else None
    elif ep == "delete_pause_rule":
        r = db.session.get(pause_rule, va["rule_id"])
        b["rule"] = {"device": r.device_name, "sample": (r.sample or "")[:120]} if r else None
    elif ep in ("ack_alerts", "pause_alerts", "unpause_alerts", "escalate_alerts", "unescalate_alerts"):
        ids = body.get("ids")
        if isinstance(ids, list) and all(isinstance(i, int) for i in ids):
            b["alerts"] = _alerts_snapshot(ids)
    return b


def _alert_names(b):
    a = (b or {}).get("alerts") or {}
    names = ", ".join(f"{n}" + (f" ×{c}" if c > 1 else "") for n, c in a.get("devices", []))
    return names + (f" and {a['more_devices']} more device(s)" if a.get("more_devices") else "")


def _describe(resp):
    """(action code, sentence, target type, target id, details) for the request that just succeeded."""
    ep = (request.endpoint or "").split(".")[-1]
    va, body, before = request.view_args or {}, request.get_json(silent=True) or {}, getattr(g, "before", {}) or {}
    out = resp.get_json(silent=True) if resp.status_code != 204 and resp.is_json else None
    out = out if isinstance(out, dict) else {}
    code, _label = ACTIONS.get(ep, (f"other.{ep}", ep))
    q = lambda x: f"'{x}'"
    details = {"request": {k: (v[:50] if isinstance(v, list) else v) for k, v in body.items()}, "result": out}
    ttype, tid = None, None
    if ep == "create_device":
        sent = out or {}
        text = f"Added device {sent.get('name')} ({sent.get('ip')}) to {sent.get('infra')} / {sent.get('folder')}"
        ttype, tid = "device", sent.get("id")
    elif ep == "update_device":
        old, new = before.get("device") or {}, out or {}
        changes = [f"{k} {old.get(k)} → {new.get(k)}" for k in ("name", "ip", "infra", "folder", "vendor") if old.get(k) != new.get(k)]
        text = f"Edited device {old.get('name')}: " + ("; ".join(changes) if changes else "no field changed")
        ttype, tid = "device", va.get("device_id")
    elif ep == "delete_device":
        d = before.get("device") or {}
        text = f"Removed device {d.get('name')} ({d.get('ip')}) from {d.get('infra')} / {d.get('folder')}"
        ttype, tid = "device", va.get("device_id")
    elif ep == "set_device_severities":
        d = before.get("device") or {}
        was, now = before.get("severities") or [], (out or {}).get("severities") or []
        text = f"Changed severity for {d.get('name')}: {', '.join(was) or 'none'} → {', '.join(now) or 'none'}"
        ttype, tid = "device", va.get("device_id")
    elif ep in ("add_keyword", "add_ignore"):
        d = before.get("device") or {}
        kind = "always-alert keyword" if ep == "add_keyword" else "ignore keyword"
        text = f"Added {kind} {q(body.get('keyword'))} to {d.get('name')}"
        ttype, tid = "device", va.get("device_id")
    elif ep in ("delete_keyword", "delete_ignore"):
        kind = "always-alert keyword" if ep == "delete_keyword" else "ignore keyword"
        text = f"Removed {kind} {q(before.get('keyword'))} from {before.get('device_name')}"
        ttype, tid = "keyword", va.get("keyword_id") or va.get("ignore_id")
    elif ep == "add_keyword_rule":
        kind = "always-alert" if body.get("kind") == "alert" else "ignore"
        extra = f", {out.get('auto_acked')} open alert(s) cleared" if out.get("auto_acked") else ""
        text = f"Applied {kind} keyword {q(out.get('keyword'))} to {out.get('scope')} ({out.get('devices')} devices, {out.get('added')} new{extra})"
        ttype = "keyword"
    elif ep == "remove_keyword_rule":
        kind = "always-alert" if body.get("kind") == "alert" else "ignore"
        text = f"Removed {kind} keyword {q(body.get('keyword'))} from every device ({out.get('removed_from')} entries)"
        ttype = "keyword"
    elif ep in ("add_keyword_device", "remove_keyword_device"):
        kind = "always-alert" if body.get("kind") == "alert" else "ignore"
        if ep == "add_keyword_device":
            extra = f", {out.get('auto_acked')} open alert(s) cleared" if out.get("auto_acked") else ""
            text = (f"Added {kind} keyword {q(out.get('keyword'))} to {out.get('device')}{extra}" if out.get("added")
                    else f"{out.get('device')} already had {kind} keyword {q(out.get('keyword'))}")
        else:
            text = f"Removed {kind} keyword {q(out.get('keyword'))} from {out.get('device')}"
        ttype = "keyword"
    elif ep == "create_folder":
        text = f"Added folder {q(out.get('name'))} to {out.get('infra')}"
        ttype, tid = "folder", out.get("id")
    elif ep == "rename_folder":
        f = before.get("folder") or {}
        text = f"Renamed folder {f.get('infra')} / {q(f.get('name'))} → {q(out.get('name'))}"
        ttype, tid = "folder", va.get("folder_id")
    elif ep == "delete_folder":
        f = before.get("folder") or {}
        text = f"Deleted folder {f.get('infra')} / {q(f.get('name'))} ({out.get('moved')} device(s) moved to Other)"
        ttype, tid = "folder", va.get("folder_id")
    elif ep == "add_auto_ack":
        text = f"Started auto-ack for {out.get('devices')} device(s) from {body.get('start')} to {body.get('end')} ({out.get('auto_acked')} open alert(s) acknowledged now)"
        ttype = "auto-ack"
    elif ep == "delete_pause_rule":
        r = before.get("rule") or {}
        text = f"Stopped muting an error on {r.get('device')}: {r.get('sample')}" + (f" ({out.get('unpaused')} alert(s) brought back)" if out.get("unpaused") else "")
        ttype, tid = "pause-rule", va.get("rule_id")
    elif ep == "delete_auto_ack":
        w = before.get("window") or {}
        text = f"Removed auto-ack for {w.get('device')} ({w.get('start')} to {w.get('end')})"
        ttype, tid = "auto-ack", va.get("window_id")
    elif ep in ("ack_alerts", "pause_alerts", "unpause_alerts", "escalate_alerts", "unescalate_alerts"):
        selected = (before.get("alerts") or {}).get("count", 0)
        key = {"ack_alerts": "acked", "pause_alerts": "paused", "unpause_alerts": "unpaused",
               "escalate_alerts": "escalated", "unescalate_alerts": "unescalated"}[ep]
        n = out.get(key, selected)                    # what the server really changed, not what was selected
        names = _alert_names(before)
        verb = {"ack_alerts": "Acknowledged", "pause_alerts": "Paused", "unpause_alerts": "Unpaused",
                "escalate_alerts": "Escalated to NET", "unescalate_alerts": "Undid escalation of"}[ep]
        until = f" until {body.get('until')}" if ep == "pause_alerts" else ""
        text = f"{verb} {n} alert{'s' if n != 1 else ''}{until}" + (f" from {names}" if names else "")
        if n == 0:
            text = f"No change: none of the {selected} selected alert(s) needed this ({verb.lower()})"
        elif n < selected:
            text += f" ({selected - n} of the {selected} selected were already in that state)"
        if ep == "pause_alerts" and out.get("muted_rules"):
            text += f" and muted the same error ({out['muted_rules']} rule{'s' if out['muted_rules'] != 1 else ''})"
        if ep == "unpause_alerts" and out.get("rules_removed"):
            text += f" and stopped muting it ({out['rules_removed']} rule{'s' if out['rules_removed'] != 1 else ''})"
        ttype = "alert"
        details["alerts"] = before.get("alerts")
    else:
        text = f"{request.method} {request.path}"
    return code, text, ttype, tid, details


@api.before_request
def _require_name_and_snapshot():
    if request.method not in MUTATING:
        return None
    who = audit_mod.actor_from_request()
    if not who:
        return jsonify({"error": "Enter your name before making changes.", "code": "name_required"}), 400
    g.actor = who
    g.before = {}
    try:
        g.before = _snapshot_before()
    except Exception:
        db.session.rollback()
    return None


@api.after_request
def _write_audit(resp):
    if request.method in MUTATING and resp.status_code < 400 and getattr(g, "actor", None):
        try:
            audit_mod.record(*_describe(resp))
        except Exception:
            db.session.rollback()
    return resp


def _safe_json(text):
    try:
        return json.loads(text) if text else None
    except ValueError:
        return {"unreadable": True}


@api.route("/audit")
def list_audit():
    audit_mod.ensure_table()
    q = audit_log.query
    who, action = (request.args.get("who") or "").strip(), (request.args.get("action") or "").strip()
    text = (request.args.get("q") or "").strip()
    if who:
        q = q.filter(audit_log.actor == who)
    if action:
        q = q.filter(audit_log.action.startswith(action.rstrip("*"), autoescape=True)) if action.endswith("*") else q.filter(audit_log.action == action)
    if text:
        q = q.filter(audit_log.summary.contains(text, autoescape=True))
    limit = min(max(request.args.get("limit", 100, type=int), 1), 500)
    offset = max(request.args.get("offset", 0, type=int), 0)
    total = q.count()
    rows = q.order_by(audit_log.id.desc()).offset(offset).limit(limit).all()
    actors = [a for (a,) in db.session.query(audit_log.actor).distinct().order_by(audit_log.actor).all()]
    return jsonify({
        "total": total, "actors": actors, "actions": [{"code": c, "label": l} for c, l in ACTION_LABELS.items()],
        "items": [{"id": r.id, "ts": _iso(r.ts), "actor": r.actor, "action": r.action,
                   "label": ACTION_LABELS.get(r.action, r.action), "summary": r.summary, "target_type": r.target_type,
                   "target_id": r.target_id, "ip": r.ip, "details": _safe_json(r.details)} for r in rows],
    })
