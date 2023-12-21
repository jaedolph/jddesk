import asyncio
import configparser
import pathlib

from pwinput import pwinput
from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic
from twitchAPI.twitch import Twitch
from twitchAPI.pubsub import PubSub
from twitchAPI.oauth import UserAuthenticator
from twitchAPI.type import AuthScope
from twitchAPI.helper import first

from jddesk import common



class DeskHeightTester():

    def __init__(self, mac_address):
        self.desk_max_height = 0
        self.desk_min_height = 200
        self.desk_height = 0
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

    async def calibrate_height(self):
        await self.client.start_notify(common.DESK_HEIGHT_READ_UUID, self.on_notification)
        await asyncio.sleep(0)
        print("Moving desk to standing position...")
        await self.client.write_gatt_char(common.DESK_HEIGHT_WRITE_UUID, common.DESK_STOP_GATT_CMD)
        await asyncio.sleep(1)
        await self.client.write_gatt_char(common.DESK_HEIGHT_WRITE_UUID, common.DESK_UP_GATT_CMD)
        await asyncio.sleep(15)
        print("Moving desk to sitting position...")
        await self.client.write_gatt_char(common.DESK_HEIGHT_WRITE_UUID, common.DESK_STOP_GATT_CMD)
        await asyncio.sleep(1)
        await self.client.write_gatt_char(common.DESK_HEIGHT_WRITE_UUID, common.DESK_DOWN_GATT_CMD)
        await asyncio.sleep(15)

        return self.desk_max_height, self.desk_min_height


async def main():

    print("\n⚠⚠⚠⚠⚠ WARNING: DO NOT SHOW THE FOLLOWING ON STREAM. ⚠⚠⚠⚠⚠" * 10)
    input("\nPress `ENTER` if this is not showing on stream.")


    print("\n" * 5)
    print("DESK SETUP")
    print("\n--------------------------")

    print("\n" * 5)
    print("Find one of the QR code stickers that came with the desk bluetooth controller")
    connection_ok = False

    while not connection_ok:
        mac_address = input("Enter the MAC address below the QR code (e.g. F8:30:02:33:53:09): ")
        print("Testing connection to the desk...")
        try:
            tester = DeskHeightTester(mac_address)
            await tester.client.connect()
            connection_ok = tester.client.is_connected
        except Exception as exp:
            print(exp)

    print("Connection OK")
    print("\n" * 5)

    print("Set your desk heights using the manual controller")
    print("Ensure you have set your '1' preset to the sitting height, and the your '2' preset set to standing height")
    input("\nPress `ENTER` when complete.")
    print("\n" * 5)
    print("Press preset '1' to move the desk to the sitting position to prepare for calibration")
    input("\nPress `ENTER` when complete.")
    print("\n" * 5)
    print("⚠⚠⚠⚠⚠ WARNING: Desk will move up and down to calibrate. Do not adjust the desk while calibration is in progress. ⚠⚠⚠⚠⚠")
    input("Press `ENTER` to start calibration.")
    print("\n" * 5)
    max_height, min_height = await tester.calibrate_height()
    print("\n" * 5)
    print(f"Desk standing height detected as {max_height}cm, sitting height detected as {min_height}cm")
    input("\nCalibration complete. Press `ENTER` to continue.")

    print("\n" * 5)
    print("TWITCH INTEGRATION SETUP")
    print("\n--------------------------")
    print("1. Create a new application at: https://dev.twitch.tv/console/apps/create")
    print("2. Set 'Name' to whatever you want e.g. 'jddesk'")
    print("3. Add an 'OAuth Redirect URL' to http://localhost:17563")
    print("4. Set 'Category' to 'Application Integration'")
    print("5. Set 'Client' to 'Confidential'")
    print("6. Click the 'I'm not a robot' verification and click 'Create'")
    input("\nPress `ENTER` when complete.")
    print("\n" * 5)

    print("Click 'manage' on the application you have created")
    client_id = input("Copy and paste the 'Client ID' here: ")
    client_secret = pwinput("Click 'New Secret' and paste the secret here: ")
    print("\n" * 5)
    broadcaster_name = input("\nWhat is the name of your twitch channel? e.g. 'jaedolph': ")
    print("\n" * 5)

    use_channel_points = None
    use_bits = None

    while not (use_channel_points or use_bits):
        while use_channel_points is None:
            use_channel_points_resp = input("\nWould you like viewers to control the desk with channel points? (yes/no): ")
            if use_channel_points_resp.lower().startswith("y"):
                use_channel_points = True
            elif use_channel_points_resp.lower().startswith("n"):
                use_channel_points = False
            else:
                print("Please enter 'yes' or 'no'")

        while use_bits is None:
            use_bits_resp = input("\nWould you like viewers to control the desk with bits? (yes/no): ")
            if use_bits_resp.lower().startswith("y"):
                use_bits = True
            elif use_bits_resp.lower().startswith("n"):
                use_bits = False
            else:
                print("Please enter 'yes' or 'no'")

        if not (use_channel_points or use_bits):
            print("\nERROR: You must enable at least one option (channel points or bits)")
            use_channel_points = None
            use_bits = None

    print("\nYou must authorize the application to manage your channel points rewards and/or listen for bits redemptions.")
    input("\nPress `ENTER` to open a new window to authorize the application.")
    target_scope = []
    if use_channel_points:
        target_scope.append(AuthScope.CHANNEL_READ_REDEMPTIONS)
        target_scope.append(AuthScope.CHANNEL_MANAGE_REDEMPTIONS)
    if use_bits:
        target_scope.append(AuthScope.BITS_READ)
    # create TwitchAPI object
    twitch = await Twitch(client_id, client_secret)
    await twitch.authenticate_app([])
    auth = UserAuthenticator(twitch, target_scope, force_verify=False)
    auth_token, refresh_token = await auth.authenticate()

    await twitch.set_user_authentication(auth_token, target_scope, refresh_token)
    broadcaster = await first(twitch.get_users(logins=[broadcaster_name]))
    broadcaster_id = broadcaster.id


    if use_channel_points:
        desk_up_reward_name = input("\nWhat would you like to call your channel points reward to raise your desk? (defaults to 'Change to standing desk'): ")
        if not desk_up_reward_name:
            desk_up_reward_name = "Change to standing desk"
        desk_down_reward_name = input("\nWhat would you like to call your channel points reward to lower your desk? (defaults to 'Change to sitting desk'): ")
        if not desk_down_reward_name:
            desk_down_reward_name = "Change to sitting desk"
        input("\nPress `ENTER` to create channel point rewards. Cost will default to 1000 points, you can change this manually in your creator dashboard")
        # configure channel points reward
        await common.set_up_channel_points(
            twitch,
            broadcaster_id,
            desk_up_reward_name,
            desk_down_reward_name,
        )
    if use_bits:
        min_bits = input("\nWhat do you want the minimum bits to move your desk to be? (e.g. 300): ")


    print("\n" * 5)
    print("DISPLAY SERVER SETUP")
    print("\n--------------------------")

    display_server_enable = None
    while display_server_enable is None:
        display_server_enable_resp = input("\nWould you like to enable the display server that can be used as an OBS browser source? (yes/no): ")
        if display_server_enable_resp.lower().startswith("y"):
            display_server_enable = True
        elif display_server_enable_resp.lower().startswith("n"):
            display_server_enable = False
        else:
            print("Please enter 'yes' or 'no'")

    config = configparser.ConfigParser()
    config.add_section("TWITCH")
    config["TWITCH"]["AUTH_TOKEN"] = auth_token
    config["TWITCH"]["REFRESH_TOKEN"] = refresh_token

    config["TWITCH"]["CLIENT_ID"] = client_id
    config["TWITCH"]["CLIENT_SECRET"] = client_secret
    config["TWITCH"]["BROADCASTER_NAME"] = broadcaster_name


    config["TWITCH"]["ENABLE_CHANNEL_POINTS"] = "yes" if use_channel_points else "no"
    if use_channel_points:
        config["TWITCH"]["DESK_UP_REWARD_NAME"] = desk_up_reward_name
        config["TWITCH"]["DESK_DOWN_REWARD_NAME"] = desk_down_reward_name

    config["TWITCH"]["ENABLE_BITS"] = "yes" if use_bits else "no"
    if use_bits:
        config["TWITCH"]["MIN_BITS"] = str(min_bits)

    config.add_section("DESK")
    config["DESK"]["CONTROLLER_MAC"] = mac_address
    config["DESK"]["SITTING_HEIGHT"] = str(min_height)
    config["DESK"]["STANDING_HEIGHT"] = str(max_height)

    config.add_section("DISPLAY_SERVER")
    config["DISPLAY_SERVER"]["ENABLED"] = "yes" if display_server_enable else "no"
    config["DISPLAY_SERVER"]["URL"] = "http://localhost:5000"

    config_file_path = str(pathlib.Path.home() / common.CONFIG_FILE_NAME)

    with open(config_file_path, "w") as config_file:
        config.write(config_file)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exp:
        print(f"Fatal exception occured: {exp}")
        common.exit(1)
    common.exit(0)