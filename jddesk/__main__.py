"""Main entrypoints for the program."""
import configparser
import logging
import pathlib
import sys
import asyncio

from bleak.exc import BleakError

from requests import RequestException
from twitchAPI.twitch import Twitch
from twitchAPI.pubsub import PubSub
from twitchAPI.oauth import UserAuthenticator
from twitchAPI.type import AuthScope
from twitchAPI.helper import first

from jddesk import desk

CONFIG_FILE_NAME = ".jddesk.ini"
POLL_INTERVAL = 1

DESK_UP_REWARD_NAME = "Change to Standing Desk (test)"
DESK_DOWN_REWARD_NAME = "Change to Sitting Desk (test)"

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
        client_secret = config["TWITCH"]["CLIENT_SECRET"]
        broadcaster_name = config["TWITCH"]["BROADCASTER_NAME"]
        controller_mac = config["BLUETOOTH"]["CONTROLLER_MAC"]
        display_server_url = config["DISPLAY_SERVER"]["URL"]
    except KeyError as exp:
        LOG.error("Missing config item: %s", exp)
        sys.exit(1)

    # create TwitchAPI object from config
    try:
        twitch = await Twitch(client_id, client_secret)
        await twitch.authenticate_app([])
        target_scope: list = [
            AuthScope.CHANNEL_READ_REDEMPTIONS,
            AuthScope.CHANNEL_MANAGE_REDEMPTIONS,
        ]
        auth = UserAuthenticator(twitch, target_scope, force_verify=False)
        token, refresh_token = await auth.authenticate()
        await twitch.set_user_authentication(token, target_scope, refresh_token)
        broadcaster = await first(twitch.get_users(logins=[broadcaster_name]))
        broadcaster_id = broadcaster.id
    except Exception as exp:
        LOG.error("Could not initialise twitch connection: %s", exp)
        sys.exit(1)

    # set up channel points rewards
    try:
        rewards = await twitch.get_custom_reward(broadcaster_id, only_manageable_rewards=True)
        desk_up_reward_id = None
        desk_down_reward_id = None
        for reward in rewards:
            title = reward.title
            if title == DESK_UP_REWARD_NAME:
                desk_up_reward_id = reward.id
                continue
            if title == DESK_DOWN_REWARD_NAME:
                desk_down_reward_id = reward.id
                continue

        if not desk_up_reward_id:
            LOG.info('Could not find desk up reward called "%s"', DESK_UP_REWARD_NAME)
            LOG.info('Creating reward "%s"', DESK_UP_REWARD_NAME)
            reward = await twitch.create_custom_reward(
                broadcaster_id,
                title=DESK_UP_REWARD_NAME,
                cost=999,
            )
            desk_up_reward_id = reward.id

        if not desk_down_reward_id:
            LOG.info('Could not find desk down reward called "%s"', DESK_DOWN_REWARD_NAME)
            LOG.info('Creating reward "%s"', DESK_DOWN_REWARD_NAME)
            reward = await twitch.create_custom_reward(
                broadcaster_id,
                title=DESK_DOWN_REWARD_NAME,
                cost=999,
            )
            desk_down_reward_id = reward.id

    except KeyError as exp:
        LOG.error("Could not get reward ids: %s", exp)
        sys.exit(1)

    # create DeskController object from config
    try:
        desk_controller = desk.DeskController(
            twitch=twitch,
            broadcaster_id=broadcaster_id,
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
    asyncio.run(run(), debug=False)


if __name__ == "__main__":
    main()
