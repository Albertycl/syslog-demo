"""Create the tables, load the fake devices and keywords once, and refresh the sample alerts. Safe to run on every start."""
from main_yt_syslog import app
import blueprint.api as api_module
from blueprint.api import apply_keyword_rule, ensure_folders, ensure_severity_row, folder_for_new_device
from demo_data import load_devices, load_keywords, seed_alerts
from model import db, device_list, all_the_logs


def main():
    with app.app_context():
        db.create_all()
        api_module._folders_ready = False
        ensure_folders()
        if device_list.query.count() == 0:
            for d in load_devices():
                db.session.add(device_list(host_name=d["name"], host_address=d["ip"], which_vendor=d["vendor"],
                                           deivce_belongs_to_which_folders=d["infra"], index=d.get("floor"),
                                           device_folder=d.get("folder") or folder_for_new_device(d["name"], d["infra"])))
            db.session.flush()
            for dev in device_list.query.all():
                ensure_severity_row(dev)
            db.session.commit()
            for r in load_keywords():
                apply_keyword_rule(r["kind"], r["keyword"], vendor=r["vendor"])
        seed_alerts(db, all_the_logs)
        print("demo data loaded", flush=True)


if __name__ == "__main__":
    main()
