"""Modules for running the web server."""
import logging

from flask import Flask, render_template
from flask_socketio import SocketIO  # type: ignore

LOG = logging.getLogger("jddesk")

app = Flask(__name__)
socketio = SocketIO(app)


@app.route("/")  # type: ignore
def index():
    """Main page that displays the current height of the desk."""
    return render_template("index.html")


@socketio.on("connect")  # type: ignore
def connect():
    """Function to call when a client connects."""
    LOG.info("client connected")


@socketio.on("disconnect")  # type: ignore
def disconnect():
    """Function to call when a client disconnects."""
    LOG.info("client disconnected")


@socketio.on("height_update")  # type: ignore
def update_height(height):
    """Sends the updated desk height to the client."""
    socketio.emit("height_display", {"height": str(height)})
