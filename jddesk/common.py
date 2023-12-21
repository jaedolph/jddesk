# Commands specific to the OmniDesk bluetooth controller.
# These commands were reverse engineered using packet captures of the bluetooth traffic.
DESK_UP_GATT_CMD = b"\xF1\xF1\x06\x00\x06\x7E"  # command will move desk to height preset 2
DESK_DOWN_GATT_CMD = b"\xF1\xF1\x05\x00\x05\x7E"  # command will move desk to height preset 1
DESK_STOP_GATT_CMD = b"\xF1\xF1\x2b\x00\x2b\x7E"  # command will stop the desk from moving

DESK_HEIGHT_READ_UUID = (
    "0000ff02-0000-1000-8000-00805f9b34fb"  # GATT UUID for receiving height notifications
)
DESK_HEIGHT_WRITE_UUID = (
    "0000ff01-0000-1000-8000-00805f9b34fb"  # GATT UUID for sending commands to the desk
)

# states for comparison
STATE_GOING_UP = "GOING UP"
STATE_GOING_DOWN = "GOING DOWN"
STATE_STANDING = "STANDING"
STATE_SITTING = "SITTING"
STATE_STOPPED = "STOPPED"

DESK_UP_BITS_COMMAND = "!deskstand"
DESK_DOWN_BITS_COMMAND = "!desksit"
DESK_GENERIC_BITS_COMMAND = "!desk"

CONFIG_FILE_NAME = "jddesk.ini"

def get_height_in_cm(data: bytes) -> float:
    """Takes binary data from the height update notification and converts it to a height in cm.

    :param data: data from the height update notification
    :returns: the height in centimeters
    """

    height = int.from_bytes(data[-5:-3], "big") / 10.0

    return height

async def set_up_channel_points(twitch, broadcaster_id, desk_up_reward_name, desk_down_reward_name):
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
            cost=1000,
        )
        desk_up_reward_id = reward.id

    if not desk_down_reward_id:
        print(f'Creating reward "{desk_down_reward_name}"')
        reward = await twitch.create_custom_reward(
            broadcaster_id,
            title=desk_down_reward_name,
            cost=1000,
        )
        desk_down_reward_id = reward.id

    return desk_up_reward_id, desk_down_reward_id
