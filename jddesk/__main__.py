"""Main entrypoints for the program."""
import configparser
import logging
import pathlib
import sys
import asyncio

from bleak.exc import BleakError

from requests import RequestException

from jddesk import desk, twitch

CONFIG_FILE_NAME = ".jddesk.ini"
POLL_INTERVAL = 1

DESK_UP_REWARD_NAME = "Change to Standing Desk"
DESK_DOWN_REWARD_NAME = "Change to Sitting Desk"

LOG = logging.getLogger("jddesk")
logging.basicConfig(
    format="%(asctime)s %(levelname)s %(message)s", level=logging.INFO, datefmt="%Y-%m-%d %H:%M:%S"
)


async def run() -> None:
    """Initialises and runs the desk controller."""

    # read config
    config_file_path = str(pathlib.Path.home() / CONFIG_FILE_NAME)
    config = configparser.ConfigParser()
    config.read(config_file_path)

    try:
        LOG.info("parsing config file...")
        auth_token = config["TWITCH"]["AUTH_TOKEN"]
        client_id = config["TWITCH"]["CLIENT_ID"]
        broadcaster_id = config["TWITCH"]["BROADCASTER_ID"]
        controller_mac = config["BLUETOOTH"]["CONTROLLER_MAC"]
        display_server_url = config["DISPLAY_SERVER"]["URL"]
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
            display_server_url=display_server_url,
        )
    except BleakError as exp:
        LOG.error("Could not initialise bluetooth connection: %s", exp)
        sys.exit(1)
    # start the desk controller
    try:
        await desk_controller.run()
    except desk.FatalException:
        sys.exit(1)


def main() -> None:
    """Main entrypoint to the program."""
    asyncio.run(run())


if __name__ == "__main__":
    main()
