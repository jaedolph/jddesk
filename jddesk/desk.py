"""Modules for controlling the desk."""

import logging
import signal
import sys
from types import FrameType
from typing import Optional
import asyncio

import socketio
from bleak import BleakClient
from bleak.exc import BleakError
from bleak.backends.characteristic import BleakGATTCharacteristic
from requests import RequestException
from twitchAPI.twitch import Twitch
from twitchAPI.pubsub import PubSub
from twitchAPI.type import CustomRewardRedemptionStatus

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

# these are hardcoded heights for my setup (in cm)
DESK_HEIGHT_STANDING = 123.0
DESK_HEIGHT_SITTING = 74.5

# time in seconds to wait between each poll of the twitch api
POLL_INTERVAL = 1

LOG = logging.getLogger("jddesk")


class FatalException(Exception):
    """Custom exception when the controller fails and can't recover."""


class DeskController:
    """Polls the Twitch API for desk related channel points rewards.

    If a reward is queued it will send commands to the desk's bluetooth control unit to move the
    desk to a standing or sitting position.

    The controller will also deal with marking rewards as redeemed or refunding points if the reward
    cannot be fulfilled e.g. if a user redeems "Change to Standing Desk" and the desk is already in
    the standing position.

    :param twitch: TwitchAPI.Twitch object for interacting with the Twitch API
    :param controller_mac: MAC address of the desk's bluetooth controller
    :param desk_up_reward_id: UUID of the channel points reward for moving the desk up
    :param desk_down_reward_id: UUID of the channel points reward for moving the desk down
    :param display_server_url: url of the display server to send height updates to
    """

    def __init__(
        self,
        twitch: Twitch,
        broadcaster_id: str,
        controller_mac: str,
        desk_up_reward_id: str,
        desk_down_reward_id: str,
        display_server_url: str,
    ) -> None:
        self.twitch = twitch
        self.controller_mac = controller_mac
        self.desk_up_reward_id = desk_up_reward_id
        self.desk_down_reward_id = desk_down_reward_id
        self.display_server_url = display_server_url
        self.sio_client = socketio.Client(reconnection=False)
        self.height = DESK_HEIGHT_SITTING
        self.state = STATE_SITTING

        self.client = BleakClient(controller_mac)

        self.pubsub = PubSub(twitch, callback_loop=asyncio.get_running_loop())
        self.broadcaster_id = broadcaster_id

        self.pending_events = set()

        # ensure graceful shutdown is handled on SIGINT and SIGTERM signals (only works for linux)
        try:
            signal.signal(signal.SIGINT, self.exit_gracefully)
            signal.signal(signal.SIGTERM, self.exit_gracefully)
        except NotImplementedError as exp:
            LOG.warning("Could not set up signal handlers: %s", exp)

    def exit_gracefully(self, signum: int, frame: Optional[FrameType]) -> None:
        """Gracefully shut down the controller."""
        del frame
        LOG.info("received signal %s", signum)
        LOG.info("stopping pubsub...")
        self.pubsub.stop()
        LOG.info("disconnecting from display server...")
        self.sio_client.disconnect()
        LOG.info("controller shutting down")
        sys.exit(0)

    @staticmethod
    def get_height_in_cm(data: bytes) -> float:
        """Takes binary data from the height update notification and converts it to a height in cm.

        :param data: data from the height update notification
        :returns: the height in centimeters
        """

        height = int.from_bytes(data[-5:-3], "big") / 10.0

        return height

    def on_notification(self, sender: BleakGATTCharacteristic, data: bytes) -> None:
        """Keep track of the desk height in realtime by listening for GATT notifications.

        If a notification is received for a height update (seems to happen constantly when the desk
        is moving), we use the callback function to update the web app display.

        :param sender: GATT characteristic of the notification
        :param data: data in the notification
        """
        del sender

        height_new = self.get_height_in_cm(data)

        LOG.debug("height=%s height_new=%s", self.height, height_new)
        if height_new > self.height:
            # If height is increasing the desk is moving up.
            self.state = STATE_GOING_UP
        elif height_new < self.height:
            # If height is decreasing the desk is moving down.
            self.state = STATE_GOING_DOWN
        elif height_new > DESK_HEIGHT_STANDING - 2:
            # If the desk is not changing height and close to standing position, assume we are
            # standing.
            self.state = STATE_STANDING
        elif height_new < DESK_HEIGHT_SITTING + 2:
            # If the desk is not changing height and close to sitting position, assume we are
            # sitting.
            self.state = STATE_SITTING
        else:
            # If the desk isn't moving and is somewhere between the sitting and standing
            # position, it probably got stuck or manually stopped so mark it as stopped.
            self.state = STATE_STOPPED

        self.height = height_new
        LOG.debug("state=%s", self.state)

        self.display_height()

    async def callback_channel_points(self, uuid, data: dict) -> None:
        del uuid
        reward_id = data["data"]["redemption"]["reward"]["id"]
        redemption_id = data["data"]["redemption"]["id"]
        user = data["data"]["redemption"]["user"]["display_name"]

        if reward_id == self.desk_up_reward_id:
            await self.handle_desk_up_reward(redemption_id, user)
        if reward_id == self.desk_down_reward_id:
            await self.handle_desk_down_reward(redemption_id, user)

    async def move_desk_up(self) -> None:
        """Sends commands to the desk to move it to the standing position."""
        await self.client.write_gatt_char(DESK_HEIGHT_WRITE_UUID, DESK_STOP_GATT_CMD)
        await asyncio.sleep(1)
        await self.client.write_gatt_char(DESK_HEIGHT_WRITE_UUID, DESK_UP_GATT_CMD)
        self.state = STATE_GOING_UP

    async def move_desk_down(self) -> None:
        """Sends commands to the desk to move it to the sitting position."""

        await self.client.write_gatt_char(DESK_HEIGHT_WRITE_UUID, DESK_STOP_GATT_CMD)
        await asyncio.sleep(1)
        await self.client.write_gatt_char(DESK_HEIGHT_WRITE_UUID, DESK_DOWN_GATT_CMD)
        self.state = STATE_GOING_DOWN

    async def reconnect(self) -> None:
        """Attempts to reconnect to desk via bluetooth."""

        LOG.info("attempting to reconnect to desk via bluetooth...")
        try:
            await self.client.disconnect()
            await asyncio.sleep(1)
            await self.client.connect()
            await asyncio.sleep(1)
        except BleakError as exp:
            LOG.error("failed to reconnect: %s", exp)
            return

        LOG.info("reconnected successfully")

    def display_height(self) -> None:
        """Sends a height update to the display server."""
        try:
            self.sio_client.emit("height_update", str(self.height))
        except socketio.client.exceptions.SocketIOError:
            LOG.error("failed to connect to display server, attempting to reconnect...")
            try:
                self.sio_client.connect(self.display_server_url)
                LOG.info("reconnected to display server")
            except socketio.client.exceptions.SocketIOError as exp:
                LOG.error("failed to reconnect: %s", exp)

    async def handle_desk_up_reward(self, redemption_id: str, user: str) -> None:
        """Handle a singular "Change to Standing Desk" channel points redemption.

        :param redemption_id: UUID of the channel points redemption
        :param user: name of the user claiming the redemption
        :raises BTBaseException: when there is an issue communicating with the desk
        """

        if self.state in (STATE_GOING_UP, STATE_STANDING):
            LOG.info("refunding %s (desk moving up or standing already)", user)
            await self.twitch.update_redemption_status(
                self.broadcaster_id,
                self.desk_up_reward_id,
                redemption_id,
                CustomRewardRedemptionStatus.CANCELED,
            )
            return
        LOG.info("%s is moving desk up", user)
        await self.move_desk_up()

        await self.twitch.update_redemption_status(
            self.broadcaster_id,
            self.desk_up_reward_id,
            redemption_id,
            CustomRewardRedemptionStatus.FULFILLED,
        )

    async def handle_desk_down_reward(self, redemption_id: str, user: str) -> None:
        """Handle a singular "Change to Sitting Desk" channel points redemption.

        :param redemption_id: UUID of the channel points redemption
        :param user: name of the user claiming the redemption
        :raises BTBaseException: when there is an issue communicating with the desk
        """

        if self.state in (STATE_GOING_DOWN, STATE_SITTING):
            LOG.info("refunding %s (desk moving down or sitting already)", user)
            await self.twitch.update_redemption_status(
                self.broadcaster_id,
                self.desk_down_reward_id,
                redemption_id,
                CustomRewardRedemptionStatus.CANCELED,
            )
            return
        LOG.info("%s is moving desk down", user)
        await self.move_desk_down()

        await self.twitch.update_redemption_status(
            self.broadcaster_id,
            self.desk_down_reward_id,
            redemption_id,
            CustomRewardRedemptionStatus.FULFILLED,
        )

    async def run(self) -> None:
        """Run the polling loop."""
        LOG.info("event loop %s", asyncio.get_running_loop())
        # connect to the desk via bluetooth
        LOG.info("connecting to desk bluetooth controller at %s...", self.controller_mac)
        try:
            await self.client.connect()
            # start notifier for desk heigh updates
            await self.client.start_notify(DESK_HEIGHT_READ_UUID, self.on_notification)
            # test moving the desk to sitting position
            await self.move_desk_down()
        except BleakError as exp:
            LOG.error("failed to connect to desk via bluetooth: %s", exp)
            raise FatalException from exp

        # connect to the display server
        LOG.info("connecting to display server at %s...", self.display_server_url)
        try:
            self.sio_client.connect(self.display_server_url)
        except socketio.client.exceptions.SocketIOError as exp:
            LOG.error("failed to connect to display server at %s: %s", self.display_server_url, exp)
            raise FatalException from exp

        self.pubsub.start()
        await self.pubsub.listen_channel_points(self.broadcaster_id, self.callback_channel_points)

        # run the polling loop
        LOG.info("starting twitch api poll loop...")
        while True:
            LOG.debug("polling twitch api")
            self.display_height()
            await asyncio.sleep(POLL_INTERVAL)
