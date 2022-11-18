"""Modules for running the web server."""
import logging

from flask import Flask, render_template
from flask_socketio import SocketIO  # type: ignore

app = Flask(__name__)
socketio = SocketIO(app)

LOG = logging.getLogger("jddesk")


@app.route("/")  # type: ignore
def index():
    """Main page that displays the current height of the desk."""
    return render_template("index.html")


@socketio.on("connect", namespace="/jddesk")  # type: ignore
def connect():
    """Function to call when a client connects (initialises the display)"""
    LOG.info("client connected")
    socketio.emit("newheight", {"height": str(0.0)}, namespace="/jddesk")


@socketio.on("disconnect", namespace="/jddesk")  # type: ignore
def disconnect():
    """Function to call when a client disconnects."""
    LOG.info("client disconnected")
