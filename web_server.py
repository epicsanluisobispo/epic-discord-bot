"""
Flask web server run alongside the bot: a simple uptime-check endpoint,
used by hosting/monitoring to confirm the bot process is alive.

(The old "/media-links" page has been replaced by a live-updating Discord
embed — see link_board.py.)
"""

from threading import Thread

from flask import Flask

app = Flask(__name__)


@app.route("/")
def home():
    return "✅ Bot is running!"


def run_flask_app():
    app.run(host="0.0.0.0", port=8080)


def start_flask_in_background_thread():
    Thread(target=run_flask_app).start()