"""Main entrypoints for the program."""
import configparser
import logging
import pathlib
import sys
from threading import Event

from gattlib import BTBaseException  # pylint: disable=no-name-in-module
from requests import RequestException

from jddesk import desk, twitch, web

CONFIG_FILE_NAME = ".jddesk.ini"
POLL_INTERVAL = 1

DESK_UP_REWARD_NAME = "Change to Standing Desk"
DESK_DOWN_REWARD_NAME = "Change to Sitting Desk"

LOG = logging.getLogger("jddesk")
logging.basicConfig(
    format="%(asctime)s %(levelname)s %(message)s", level=logging.INFO, datefmt="%Y-%m-%d %H:%M:%S"
)

# disable spammy logs from the web server
logging.getLogger("werkzeug").setLevel(logging.CRITICAL)


def update_height_display(height: float) -> None:
    """Updates the desk height display in the web app with the current height.

    :param height: current height of the desk in cm
    """
    web.socketio.emit("newheight", {"height": str(height)}, namespace="/jddesk")


def run_loop(desk_controller: desk.DeskController, thread_stop_event: Event) -> None:
    """Run the desk controller thread.

    :param desk_controller: initialised DeskController object
    :param thread_stop_event: event to use to stop the desk controller thread
    """
    # connect to the desk via bluetooth
    desk_controller.connect()

    # run the polling loop
    while not thread_stop_event.is_set():
        desk_controller.poll()
        web.socketio.sleep(POLL_INTERVAL)


def main() -> None:
    """Main entrypoint to the program."""

    # read config
    config_file_path = str(pathlib.Path.home() / CONFIG_FILE_NAME)
    config = configparser.ConfigParser()
    config.read(config_file_path)

    try:
        auth_token = config["TWITCH"]["AUTH_TOKEN"]
        client_id = config["TWITCH"]["CLIENT_ID"]
        broadcaster_id = config["TWITCH"]["BROADCASTER_ID"]
        controller_mac = config["BLUETOOTH"]["CONTROLLER_MAC"]
    except KeyError as exp:
        LOG.error("Missing config item: %s", exp)
        sys.exit(1)

    # create TwitchAPI object from config
    try:
        twitch_api = twitch.TwitchAPI(
            auth_token=auth_token,
            client_id=client_id,
            broadcaster_id=broadcaster_id,
        )
        rewards = twitch_api.get_rewards()
    except RequestException as exp:
        LOG.error("Could not initialise twitch connection: %s", exp)
        sys.exit(1)

    # convert reward names to ids
    try:
        desk_up_reward_id = None
        desk_down_reward_id = None
        for reward in rewards:
            title = reward["title"]
            if title == DESK_UP_REWARD_NAME:
                desk_up_reward_id = reward["id"]
                continue
            if title == DESK_DOWN_REWARD_NAME:
                desk_down_reward_id = reward["id"]
                continue

        if not desk_up_reward_id:
            raise KeyError(f"no reward id matching '{DESK_UP_REWARD_NAME}'")
        if not desk_down_reward_id:
            raise KeyError(f"no reward id matching '{DESK_DOWN_REWARD_NAME}'")

    except KeyError as exp:
        LOG.error("Could not get reward ids: %s", exp)
        sys.exit(1)

    # create DeskController object from config
    try:
        desk_controller = desk.DeskController(
            twitch_api=twitch_api,
            controller_mac=controller_mac,
            desk_up_reward_id=desk_up_reward_id,
            desk_down_reward_id=desk_down_reward_id,
            callback=update_height_display,
        )
    except BTBaseException as exp:
        LOG.error("Could not initialise bluetooth connection: %s", exp)
        sys.exit(1)

    # start desk controller in background thread
    thread_stop_event = Event()
    web.socketio.start_background_task(run_loop, desk_controller, thread_stop_event)

    # start webserver
    web.socketio.run(web.app, host="0.0.0.0")


if __name__ == "__main__":
    main()
