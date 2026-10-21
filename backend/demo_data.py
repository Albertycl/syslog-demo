"""Fake data for the public demo: devices, keyword rules, sample alerts and a fake log source for the collector."""
import json
import random
from datetime import datetime, timedelta
from pathlib import Path

DATA = Path(__file__).parent / "data"
TAG = "demo"

# vendor -> (syslog severity name, code, message template)
TEMPLATES = {
    "cisco": [
        ("Errors", 3, "%LINK-3-UPDOWN: Interface Ethernet1/{n}, changed state to down"),
        ("Errors", 3, "%ETH_PORT_CHANNEL-5-PORT_DOWN: port-channel{n}: Ethernet1/{n} is down"),
        ("Critical", 2, "%BGP-5-ADJCHANGE: neighbor 192.0.2.{n} Down BGP Notification sent"),
        ("Errors", 3, "%SPANTREE-2-ROOTGUARD_BLOCK: Root guard blocking port Ethernet1/{n} on VLAN00{n}"),
        ("Warnings", 4, "%SYS-4-CPUHOG: Task is running for (2004)msecs, more than (2000)msecs"),
        ("Notifications", 5, "%SYS-5-CONFIG_I: Configured from console by demo-user on vty0"),
        ("Notifications", 5, "%LINEPROTO-5-UPDOWN: Line protocol on Interface Ethernet1/{n}, changed state to up"),
        ("Informational", 6, "%SEC_LOGIN-6-LOGIN_SUCCESS: Login Success [user: demo_ro] [Source: 192.0.2.250]"),
    ],
    "LTM": [
        ("Critical", 2, "01070727:2: Pool /Common/web_pool member /Common/192.0.2.{n}:443 monitor status down."),
        ("Error", 3, "01010028:3: No members available for pool /Common/web_pool"),
        ("Error", 3, "01140029:3: HA proc_running tmm fails, action is go offline and down links."),
        ("Warning", 4, "01070638:4: Pool /Common/web_pool member /Common/192.0.2.{n}:443 monitor status forced down."),
        ("Notice", 5, "01140030:5: Standby: traffic-group-1 failover to peer completed."),
        ("Informational", 6, "01070417:6: AUDIT - user demo-admin - RAW: config change on /Common/vs_https"),
        ("Informational", 6, "014f0005:6: Idle enforcer exiting after 5 minutes"),
    ],
}
PAN_SEVERITIES = ["Critical", "High", "Medium", "Low", "Informational"]
PAN_TEXT = ["vpn-tunnel-{n} down: IKE phase-1 negotiation failed", "link-down on ethernet1/{n}",
            "ha1-link-change: HA1 link down", "General system message {n}", "User demo-user logged in"]


def load_devices():
    return json.loads((DATA / "devices.json").read_text())["devices"]


def load_keywords():
    return json.loads((DATA / "keywords.json").read_text())["apply"]


def _pan_line(ts, rnd):
    sev = rnd.choice(PAN_SEVERITIES[:2] * 3 + PAN_SEVERITIES[2:])
    f = ["1", f"{ts:%Y/%m/%d %H:%M:%S}", "0123456789", "SYSTEM", "general", "0", f"{ts:%Y/%m/%d %H:%M:%S}", "", "", "", "",
         "0", "0", sev, rnd.choice(PAN_TEXT).format(n=rnd.randint(1, 24))]
    return sev, ",".join(f)


def make_log(device, ts, rnd):
    """(severity name, severity code, message) for one fake syslog line from `device`."""
    if device["vendor"] == "paloalto":
        sev, csv = _pan_line(ts, rnd)
        return sev, 3, f"<14>{ts:%b %d %H:%M:%S} {device['name']} {csv}"
    name, code, text = rnd.choice(TEMPLATES[device["vendor"]])
    return name, code, f"<189>{ts:%b %d %H:%M:%S} {device['name']} " + text.format(n=rnd.randint(1, 48))


def fake_docs(minutes, rnd=random):
    """Elasticsearch-shaped documents (UTC timestamps), as the collector expects them."""
    devices = load_devices()
    now = datetime.utcnow()
    docs = []
    for _ in range(min(2 + int(minutes) // 10, 12)):
        d = rnd.choice(devices)
        ts = now - timedelta(seconds=rnd.randint(0, max(1, min(int(minutes), 60)) * 60 - 1))
        local = ts + timedelta(hours=8)
        name, code, msg = make_log(d, local, rnd)
        docs.append({"@timestamp": ts.strftime("%Y-%m-%dT%H:%M:%S.000Z"), "host": {"hostname": d["name"], "ip": d["ip"]},
                     "event": {"original": msg}, "log": {"syslog": {"severity": {"name": name, "code": code}}}})
    return docs


def seed_alerts(db, all_the_logs, count=46):
    """Replace the sample alerts with fresh ones (timestamps relative to now)."""
    rnd = random.Random(14)
    all_the_logs.query.filter(all_the_logs.insert_by_which_condition == TAG).delete()
    now = datetime.utcnow() + timedelta(hours=8)
    devices = load_devices()
    for _ in range(count):
        d = rnd.choice(devices)
        ts = now - timedelta(minutes=rnd.randint(1, 60 * 30))
        name, _code, msg = make_log(d, ts, rnd)
        acked = rnd.random() < 0.22
        db.session.add(all_the_logs(
            timestamp=ts, host_address=d["ip"], host_name=d["name"], log_level=name, message=msg,
            service_type=d["vendor"], alert_acked_or_not="Acked" if acked else "alert_not_acked",
            who_acked_the_alert="demo-user" if acked else None, boolean_for_pausing_alert_checkbox=False,
            insert_by_which_condition=TAG))
    db.session.commit()
