import logging
from flask import Flask, render_template
from api.routes import api
from config import PORT, DEBUG

logging.basicConfig(
    level=logging.DEBUG if DEBUG else logging.INFO,
    format="%(asctime)s %(levelname)-5s [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
)


def create_app():
    app = Flask(__name__)
    app.register_blueprint(api)

    @app.route("/")
    def index():
        return render_template("index.html")

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(host="127.0.0.1", port=PORT, debug=DEBUG)
