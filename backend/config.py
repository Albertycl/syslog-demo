import os


class Config:
    SECRET_KEY = os.urandom(16)
    SQLALCHEMY_DATABASE_URI = os.environ['DATABASE_URL']
    SQLALCHEMY_TRACK_MODIFICATIONS = False


class ProdConfig(Config):
    DEBUG = False


class DevConfig(Config):
    DEBUG = True


# The demo collector reads fake logs from demo_data.py every COLLECT_INTERVAL_SECONDS (0 turns it off).
COLLECT_INTERVAL_SECONDS = int(os.environ.get('COLLECT_INTERVAL_SECONDS', '20'))
COLLECT_WINDOW_MINUTES = int(os.environ.get('COLLECT_WINDOW_MINUTES', '5'))

# Browser origins allowed to call the API (comma separated).
CORS_ORIGINS = [o.strip() for o in os.environ.get(
    'CORS_ORIGINS', 'http://localhost:8090,http://127.0.0.1:8090').split(',') if o.strip()]
