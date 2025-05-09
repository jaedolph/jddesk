"""Modules for running the web server."""

import logging
import sys

from flask import Flask, render_template
from flask_socketio import SocketIO  # type: ignore

LOG = logging.getLogger("jddesk")

app = Flask(__name__)
socketio = SocketIO(app)
werkzeug_log = logging.getLogger("werkzeug")
werkzeug_log.disabled = True
cli = sys.modules["flask.cli"]
cli.show_server_banner = lambda *x: None  # type: ignore


@app.route("/")
def index():  # type: ignore
    """Main page that displays the current height of the desk."""
    return render_template("index.html")


@socketio.on("connect")
def connect():  # type: ignore
    """Function to call when a client connects."""
    LOG.info("client connected to display server")


@socketio.on("disconnect")
def disconnect():  # type: ignore
    """Function to call when a client disconnects."""
    LOG.info("client disconnected from display server")


@socketio.on("height_update")
def update_height(height):  # type: ignore
    """Sends the updated desk height to the client."""
    socketio.emit("height_display", {"height": str(height)})
