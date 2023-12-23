"""Helper program to write config file."""

import asyncio

from pwinput import pwinput
from bleak import BleakClient
from bleak.exc import BleakError
from bleak.backends.characteristic import BleakGATTCharacteristic
from twitchAPI.twitch import Twitch
from twitchAPI.oauth import UserAuthenticator
from twitchAPI.helper import first
from twitchAPI.type import TwitchAPIException

from jddesk import common
from jddesk.config import DeskConfig, DeskConfigError


class DeskHeightTester:
    """Used to test that the desk controller is functioning properly.

    :param mac_address: MAC address of the desk's bluetooth controller
    """

    def __init__(self, mac_address: str) -> None:
        self.desk_max_height = 0.0
        self.desk_min_height = 200.0
        self.desk_height = 0.0
        self.client = BleakClient(mac_address)

    def on_notification(self, sender: BleakGATTCharacteristic, data: bytes) -> None:
        """Keep track of the desk height in realtime by listening for GATT notifications.

        We can use this to find the desk maximum and minimum heights.

        :param sender: GATT characteristic of the notification
        :param data: data in the notification
        """
        del sender
        self.desk_height = common.get_height_in_cm(data)
        if self.desk_height > self.desk_max_height:
            self.desk_max_height = self.desk_height
        if self.desk_height < self.desk_min_height:
            self.desk_min_height = self.desk_height

    async def calibrate_height(self) -> tuple[float, float]:
        """Determines the sitting and standing heights of the desk by moving it up and down.

        :return: maximum and minimum heights the desk moved to during the test
        """
        await self.client.start_notify(common.DESK_HEIGHT_READ_UUID, self.on_notification)
        await asyncio.sleep(0)
        print("Moving desk to standing position...")
        await self.client.write_gatt_char(common.DESK_HEIGHT_WRITE_UUID, common.DESK_STOP_GATT_CMD)
        await asyncio.sleep(1)
        await self.client.write_gatt_char(common.DESK_HEIGHT_WRITE_UUID, common.DESK_UP_GATT_CMD)
        await asyncio.sleep(14)
        print("Moving desk to sitting position...")
        await self.client.write_gatt_char(common.DESK_HEIGHT_WRITE_UUID, common.DESK_STOP_GATT_CMD)
        await asyncio.sleep(1)
        await self.client.write_gatt_char(common.DESK_HEIGHT_WRITE_UUID, common.DESK_DOWN_GATT_CMD)
        await asyncio.sleep(14)

        return self.desk_max_height, self.desk_min_height


def input_bool(prompt: str) -> bool:
    """Wrapper around the input function that can be used for boolean values. Repeats the prompt
    until a valid yes/no answer is added.

    :param prompt: input prompt to show the user
    :return: true if the user enters yes, false if they enter no
    """
    return_val = None
    while return_val is None:
        input_string = input(prompt)
        if input_string.lower().startswith("y"):
            return_val = True
        elif input_string.lower().startswith("n"):
            return_val = False
        else:
            print("Please enter 'yes' or 'no'")
            return_val = None

    return return_val


async def configure_desk_controller(config: DeskConfig) -> DeskConfig:
    """Performs a survey to configure desk controller parameters."""
    connection_ok = False
    while not connection_ok:
        config.controller_mac = input(
            "Enter the MAC address below the QR code (e.g. F8:30:02:33:53:09): "
        )
        print("Testing connection to the desk...")
        try:
            tester = DeskHeightTester(config.controller_mac)
            await tester.client.connect()
            connection_ok = tester.client.is_connected
        except BleakError as exception:
            print(f"\nERROR: {exception}\n")

    print("Connection OK")
    print("\n" * 5)

    print("Set your desk heights using the manual controller")
    print(
        "1. Ensure you have set your '1' preset to the sitting height, and the your '2' "
        "preset set to standing height\n"
        "2. Press preset '1' to move the desk to the sitting position to prepare for calibration"
    )
    input("\nPress `ENTER` when complete.")
    print("\n" * 5)
    print(
        "⚠⚠⚠⚠⚠ WARNING: Desk will move up and down to calibrate. Do not adjust the desk "
        "while calibration is in progress. ⚠⚠⚠⚠⚠"
    )
    input("Press `ENTER` to start calibration.")
    print("\n" * 5)
    config.desk_height_standing, config.desk_height_sitting = await tester.calibrate_height()

    print("\n" * 5)
    print(
        f"Desk standing height detected as {config.desk_height_standing}cm, "
        f"sitting height detected as {config.desk_height_sitting }cm"
    )
    input("\nCalibration complete. Press `ENTER` to continue.")

    return config


def configure_twitch(config: DeskConfig) -> DeskConfig:
    """Configure twitch application settings.

    :param config: DeskConfig object to update
    :return: updated DeskConfig object
    """

    print(
        "1. Create a new application at: https://dev.twitch.tv/console/apps/create\n"
        '2. Set "Name" to whatever you want e.g. "jddesk"\n'
        '3. Add an "OAuth Redirect URL" to http://localhost:17563\n'
        '4. Set "Category" to "Application Integration"\n'
        '5. Set "Client" to "Confidential"\n'
        '6. Click the "I\'m not a robot" verification and click "Create"\n'
        '7. Click "manage" on the application you have created'
    )
    input("\nPress `ENTER` when complete.")
    print("\n" * 5)
    config.client_id = input("Copy and paste the 'Client ID' here: ")
    config.client_secret = pwinput("Click 'New Secret' and paste the secret here: ")
    print("\n" * 5)
    config.broadcaster_name = input("\nWhat is the name of your twitch channel? e.g. 'jaedolph': ")
    print("\n" * 5)

    channel_points_enabled = None
    bits_enabled = None

    while not (channel_points_enabled or bits_enabled):
        channel_points_enabled = input_bool(
            "\nWould you like viewers to control the desk with channel points? (yes/no): "
        )

        bits_enabled = input_bool(
            "\nWould you like viewers to control the desk with bits? (yes/no): "
        )

        if not (channel_points_enabled or bits_enabled):
            print("\nERROR: You must enable at least one option (channel points or bits)")
            channel_points_enabled = None
            bits_enabled = None

    config.channel_points_enabled = channel_points_enabled
    config.bits_enabled = bits_enabled

    return config


async def authorize_twitch(config: DeskConfig) -> tuple[Twitch, DeskConfig]:
    """Configure twitch API authorization.

    :param config: DeskConfig object to update
    :return: initialized Twitch object and updated DeskConfig object
    """

    print(
        "\nYou must authorize the application to manage your channel points rewards and/or listen "
        "for bits redemptions."
    )
    input("\nPress `ENTER` to open a new window to authorize the application.")

    # create TwitchAPI object
    target_scope = common.get_target_scope(config.channel_points_enabled, config.bits_enabled)
    twitch = await Twitch(config.client_id, config.client_secret)
    await twitch.authenticate_app([])
    auth = UserAuthenticator(twitch, target_scope, force_verify=True)
    auth.document = """<!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <title>jddesk authorization</title>
        </head>
        <body>
            <h1>Successfully authorized application</h1>
        Please close this page and return to the setup utility.
        </body>
    </html>"""
    config.auth_token, config.refresh_token = await auth.authenticate()

    await twitch.set_user_authentication(config.auth_token, target_scope, config.refresh_token)

    return twitch, config


async def configure_channel_points(twitch: Twitch, config: DeskConfig) -> DeskConfig:
    """Configure channel point rewards used for moving the desk.

    :param twitch: twitch object
    :param config: DeskConfig object to update
    :return: updated DeskConfig object
    """

    broadcaster = await first(twitch.get_users(logins=[config.broadcaster_name]))
    assert broadcaster is not None
    broadcaster_id = broadcaster.id

    if config.channel_points_enabled:
        desk_up_reward_name = input(
            "\nWhat would you like to call your channel points reward to raise your desk? "
            "(leave blank to use 'Change to standing desk'): "
        )
        if not desk_up_reward_name:
            desk_up_reward_name = "Change to standing desk"
        desk_down_reward_name = input(
            "\nWhat would you like to call your channel points reward to lower your desk? "
            "(leave blank to use 'Change to sitting desk'): "
        )
        if not desk_down_reward_name:
            desk_down_reward_name = "Change to sitting desk"
        input(
            "\nPress `ENTER` to create channel point rewards. Cost will default to "
            f"{common.DESK_DOWN_CHANNEL_POINTS_COST} points, you can change this manually in your "
            "creator dashboard"
        )

        config.desk_up_reward_name = desk_up_reward_name
        config.desk_down_reward_name = desk_down_reward_name
        # configure channel points reward
        await common.set_up_channel_points(
            twitch,
            broadcaster_id,
            desk_up_reward_name,
            desk_down_reward_name,
        )

    return config


def configure_bits(config: DeskConfig) -> DeskConfig:
    """Configure bits used for moving the desk.

    :param config: DeskConfig object to update
    :return: updated DeskConfig object
    """
    min_bits = None
    while min_bits is None:
        min_bits = input(
            "\nWhat do you want the minimum bits to move your desk to be? (e.g. 300): "
        )
        try:
            config.min_bits = int(min_bits)
        except ValueError:
            print("ERROR: please enter a valid number")
            min_bits = None

    return config


def configure_display_server(config: DeskConfig) -> DeskConfig:
    """Configure display server that can be used as a browser source.

    :param config: DeskConfig object to update
    :return: updated DeskConfig object
    """

    config.display_server_enabled = input_bool(
        "\nWould you like to enable the display server that can be used as an OBS "
        "browser source? (yes/no): "
    )
    if config.display_server_enabled:
        config.display_server_address = "localhost:5000"

    return config


# pylint: disable=too-many-statements,too-many-branches
async def configure(config_file_path: str) -> None:
    """Utility that prompts user for settings to configure the desk controller."""

    desk_config = DeskConfig(config_file_path)
    desk_config.new_config()

    print("\n⚠⚠⚠⚠⚠ WARNING: DO NOT SHOW THE FOLLOWING ON STREAM. ⚠⚠⚠⚠⚠" * 10)
    input("\nPress `ENTER` if this is not showing on stream.")

    print("checking current config...")
    config_valid = False
    try:
        desk_config.load_config()
        config_valid = True
    except DeskConfigError:
        print("config is currently not valid")
        config_valid = False

    print("\n" * 5)
    print("DESK SETUP")
    print("\n--------------------------")
    desk_config_valid = False
    if config_valid:
        desk_config_valid = not input_bool(
            "Desk configuration is valid, would you like to update it? (yes/no): "
        )
    while not desk_config_valid:
        desk_config = await configure_desk_controller(desk_config)
        try:
            desk_config.validate_desk_section()
            desk_config_valid = True
        except DeskConfigError as exception:
            print(f"\nERROR: invalid config {exception}\n")
            desk_config_valid = False

    print("\n" * 5)
    print("TWITCH INTEGRATION SETUP")
    print("\n--------------------------")

    twitch_config_valid = False
    if config_valid:
        twitch_config_valid = not input_bool(
            "Twitch configuration is valid, would you like to update it? (yes/no): "
        )
    while not twitch_config_valid:
        desk_config = configure_twitch(desk_config)
        try:
            twitch, desk_config = await authorize_twitch(desk_config)
        except TwitchAPIException as exception:
            print(f"\nERROR: could not configure Twitch API authorization: {exception}\n")
            continue

        if desk_config.channel_points_enabled:
            print("\n" * 5)
            print("CHANNEL POINTS SETUP")
            print("\n--------------------------")
            try:
                desk_config = await configure_channel_points(twitch, desk_config)
            except TwitchAPIException as exception:
                print(f"\nERROR: could not configure channel points: {exception}\n")
                continue

        if desk_config.bits_enabled:
            print("\n" * 5)
            print("BITS SETUP")
            print("\n--------------------------")
            desk_config = configure_bits(desk_config)
        try:
            desk_config.validate_twitch_section()
            twitch_config_valid = True
        except DeskConfigError as exception:
            print(f"\nERROR: invalid config {exception}\n")
            twitch_config_valid = False

    print("\n" * 5)
    print("DISPLAY SERVER SETUP")
    print("\n--------------------------")
    display_server_config_valid = False
    if config_valid:
        display_server_config_valid = not input_bool(
            "Display server configuration is valid, would you like to update it? (yes/no): "
        )
    while not display_server_config_valid:
        desk_config = configure_display_server(desk_config)
        try:
            desk_config.validate_display_server_section()
            display_server_config_valid = True
        except DeskConfigError as exception:
            print(f"\nERROR: invalid config {exception}\n")
            display_server_config_valid = False

    print("\n" * 5)
    print(f"Writing config file to {desk_config.config_file_path}...")
    desk_config.write_config()
    print("CONFIGURATION COMPLETE")


# pylint: disable=
