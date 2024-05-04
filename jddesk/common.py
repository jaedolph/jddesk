"""Common functions/variables used in multiple submodules."""

import sys
import os
import pathlib
from twitchAPI.twitch import Twitch
from twitchAPI.type import AuthScope

# Commands specific to the JCP35N-BLT bluetooth module.
# These should work for any desk using this controller including OmniDesk and UPLIFT desks.
# These commands were reverse engineered using packet captures of the bluetooth traffic.
DESK_UP_GATT_CMD = b"\xF1\xF1\x06\x00\x06\x7E"  # command will move desk to height preset 2
DESK_DOWN_GATT_CMD = b"\xF1\xF1\x05\x00\x05\x7E"  # command will move desk to height preset 1
DESK_STOP_GATT_CMD = b"\xF1\xF1\x2b\x00\x2b\x7E"  # command will stop the desk from moving

# states for comparison
STATE_GOING_UP = "GOING UP"
STATE_GOING_DOWN = "GOING DOWN"
STATE_STANDING = "STANDING"
STATE_SITTING = "SITTING"
STATE_STOPPED = "STOPPED"

DESK_UP_BITS_COMMAND = "!deskstand"
DESK_DOWN_BITS_COMMAND = "!desksit"
DESK_GENERIC_BITS_COMMAND = "!desk"

DEFAULT_CONFIG_FILE_NAME = "jddesk.ini"
DEFAULT_CONFIG_FILE_PATH = str(pathlib.Path.home() / DEFAULT_CONFIG_FILE_NAME)

DESK_DOWN_CHANNEL_POINTS_COST = 1000
DESK_UP_CHANNEL_POINTS_COST = 1000


def custom_exit(return_code: int) -> None:
    """Custom exit routine that ensures the console window doesn't close immediately on Windows.

    :param return_code: the return code to set on exit
    """
    if os.name == "nt":
        input("Press `ENTER` to exit")
    sys.exit(return_code)


def get_height_in_cm(data: bytes) -> float:
    """Takes binary data from the height update notification and converts it to a height in cm.

    :param data: data from the height update notification
    :returns: the height in centimeters
    """

    height = int.from_bytes(data[-5:-3], "big") / 10.0

    return height


async def set_up_channel_points(
    twitch: Twitch, broadcaster_id: str, desk_up_reward_name: str, desk_down_reward_name: str
) -> tuple[str, str]:
    """Configure channel points rewards for sitting and standing.

    :param twitch: Twitch object to interact with the Twitch API
    :param broadcaster_id: id of the broadcaster to configure channel points for
    :param desk_up_reward_name: Name of channel points reward to move the desk to stand position
    :param desk_down_reward_name: Name of channel points reward to move the desk to sit position
    :return: numeric ids of the desk_up and desk_down rewards
    """
    # set up channel points rewards
    rewards = await twitch.get_custom_reward(broadcaster_id, only_manageable_rewards=True)
    desk_up_reward_id = None
    desk_down_reward_id = None
    for reward in rewards:
        title = reward.title
        if title == desk_up_reward_name:
            desk_up_reward_id = reward.id
            continue
        if title == desk_down_reward_name:
            desk_down_reward_id = reward.id
            continue

    if not desk_up_reward_id:
        print(f'Creating reward "{desk_up_reward_name}"')
        reward = await twitch.create_custom_reward(
            broadcaster_id,
            title=desk_up_reward_name,
            cost=DESK_UP_CHANNEL_POINTS_COST,
        )
        desk_up_reward_id = reward.id

    if not desk_down_reward_id:
        print(f'Creating reward "{desk_down_reward_name}"')
        reward = await twitch.create_custom_reward(
            broadcaster_id,
            title=desk_down_reward_name,
            cost=DESK_DOWN_CHANNEL_POINTS_COST,
        )
        desk_down_reward_id = reward.id

    return desk_up_reward_id, desk_down_reward_id


def get_target_scope(channel_points_enabled: bool, bits_enabled: bool) -> list[AuthScope]:
    """Gets a list of required twitch auth scopes for managing channel points and/or bits.

    :param channel_points_enabled: true if channel points will be used to move the desk
    :param bits_enabled: true if bits will be used to move the desk
    :return: List of AuthScopes required
    """

    if not (channel_points_enabled or bits_enabled):
        raise ValueError("must enable at least one scope (channel points or bits)")

    target_scope = []
    if channel_points_enabled:
        target_scope.append(AuthScope.CHANNEL_READ_REDEMPTIONS)
        target_scope.append(AuthScope.CHANNEL_MANAGE_REDEMPTIONS)
    if bits_enabled:
        target_scope.append(AuthScope.BITS_READ)

    return target_scope
