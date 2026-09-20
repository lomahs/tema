"""Run the app: `.venv/bin/python app.py`.

The factory lives in `tcm.web.app`; this is the entry point that keeps the
documented command working from the repository root.
"""
from tcm.settings import DEBUG, PORT
from tcm.web.app import configure_logging, create_app

configure_logging()
app = create_app()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=PORT, debug=DEBUG)
