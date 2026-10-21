import logging
import os

from flask import Flask
from flask_cors import CORS

from blueprint.api import api
from blueprint.collector import collector, should_autostart, start_scheduler
from config import CORS_ORIGINS, DevConfig, ProdConfig
from model import db

app = Flask(__name__)
app.register_blueprint(api)
app.register_blueprint(collector)

# Debug mode (and the Werkzeug debugger) only when FLASK_DEBUG is set.
app.config.from_object(DevConfig if os.environ.get("FLASK_DEBUG", "").strip().lower() in ("1", "true", "yes") else ProdConfig)
db.init_app(app)
CORS(app, origins=CORS_ORIGINS)
logging.getLogger("werkzeug").setLevel(logging.ERROR)


@app.route("/healthz")
def healthz():
    return "ok"


# The collector schedule starts only in a real server process (gunicorn); scripts that import this module do not start it.
_start, _why = should_autostart(app)
if _start:
    start_scheduler(app)
print(f"collector schedule: {'started' if _start else 'not started'} ({_why})", flush=True)
