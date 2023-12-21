"""Main entrypoints for the program."""
import configparser
import logging
import pathlib
import asyncio

from bleak.exc import BleakError

from requests import RequestException
from twitchAPI.twitch import Twitch
from twitchAPI.pubsub import PubSub
from twitchAPI.oauth import UserAuthenticator
from twitchAPI.type import AuthScope
from twitchAPI.helper import first

from jddesk import desk, common

POLL_INTERVAL = 1

LOG = logging.getLogger("jddesk")
logging.basicConfig(
    format="%(asctime)s %(levelname)s %(message)s", level=logging.DEBUG, datefmt="%Y-%m-%d %H:%M:%S"
)

async def run() -> None:
    """Initialises and runs the desk controller."""

    # read config
    config_file_path = str(pathlib.Path.home() / common.CONFIG_FILE_NAME)
    config = configparser.ConfigParser()
    config.read(config_file_path)

    try:
        LOG.info("parsing config file...")
        auth_token = config["TWITCH"]["AUTH_TOKEN"]
        refresh_token = config["TWITCH"]["REFRESH_TOKEN"]
        client_id = config["TWITCH"]["CLIENT_ID"]
        client_secret = config["TWITCH"]["CLIENT_SECRET"]
        broadcaster_name = config["TWITCH"]["BROADCASTER_NAME"]
        controller_mac = config["DESK"]["CONTROLLER_MAC"]
        desk_height_sitting = float(config["DESK"]["SITTING_HEIGHT"])
        desk_height_standing = float(config["DESK"]["STANDING_HEIGHT"])
        display_server_enabled = (config["DISPLAY_SERVER"]["ENABLED"] == "yes")
        display_server_url = None
        if display_server_enabled:
            display_server_url = config["DISPLAY_SERVER"]["URL"]
        min_bits = None
        use_bits = (config["TWITCH"]["ENABLE_BITS"] == "yes")
        if use_bits:
            min_bits = int(config["TWITCH"]["MIN_BITS"])
        use_channel_points = (config["TWITCH"]["ENABLE_CHANNEL_POINTS"] == "yes")

        desk_up_reward_name = None
        desk_down_reward_name = None
        if use_channel_points:
            desk_up_reward_name = config["TWITCH"]["DESK_UP_REWARD_NAME"]
            desk_down_reward_name = config["TWITCH"]["DESK_DOWN_REWARD_NAME"]
    except KeyError as exp:
        LOG.error("Missing config item: %s", exp)
        common.exit(1)

    # create TwitchAPI object from config
    try:
        LOG.info("configuring twitch authentication...")
        twitch = await Twitch(client_id, client_secret)
        await twitch.authenticate_app([])
        target_scope = []
        if use_channel_points:
            target_scope.append(AuthScope.CHANNEL_READ_REDEMPTIONS)
            target_scope.append(AuthScope.CHANNEL_MANAGE_REDEMPTIONS)
        if use_bits:
            target_scope.append(AuthScope.BITS_READ)

        await twitch.set_user_authentication(auth_token, target_scope, refresh_token)
        broadcaster = await first(twitch.get_users(logins=[broadcaster_name]))
        broadcaster_id = broadcaster.id
    except Exception as exp:
        LOG.error("Could not initialise twitch connection: %s", exp)
        common.exit(1)

    if use_channel_points:
        # configure channel points reward
        LOG.info("checking channel points rewards...")
        desk_up_reward_id, desk_down_reward_id = await common.set_up_channel_points(
            twitch,
            broadcaster_id,
            desk_up_reward_name,
            desk_down_reward_name,
        )

    # create DeskController object from config
    try:
        desk_controller = desk.DeskController(
            twitch=twitch,
            broadcaster_id=broadcaster_id,
            controller_mac=controller_mac,
            desk_up_reward_id=desk_up_reward_id,
            desk_down_reward_id=desk_down_reward_id,
            desk_height_standing=desk_height_standing,
            desk_height_sitting=desk_height_sitting,
            min_bits=min_bits,
            display_server_url=display_server_url,
        )
    except BleakError as exp:
        LOG.error("Could not initialise bluetooth connection: %s", exp)
        common.exit(1)

    # start the desk controller
    try:
        await desk_controller.run()
    except desk.FatalException:
        common.exit(1)


def main() -> None:
    """Main entrypoint to the program."""
    asyncio.run(run(), debug=False)
    common.exit(0)

if __name__ == "__main__":
    main()
