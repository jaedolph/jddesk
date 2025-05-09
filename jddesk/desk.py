"""Modules for controlling the desk."""

import logging
import signal
import sys
import asyncio

import socketio
from bleak import BleakClient
from bleak.exc import BleakError
from bleak.backends.characteristic import BleakGATTCharacteristic
from twitchAPI.twitch import Twitch
from twitchAPI.eventsub.websocket import EventSubWebsocket
from twitchAPI.object.eventsub import ChannelPointsCustomRewardRedemptionAddEvent, ChannelCheerEvent
from twitchAPI.type import CustomRewardRedemptionStatus, TwitchAPIException
from twitchAPI.helper import first

from jddesk import common
from jddesk.config import DeskConfig

# time in seconds to wait between each run loop
POLL_INTERVAL = 1

LOG = logging.getLogger("jddesk")


class FatalException(Exception):
    """Custom exception when the controller fails and can't recover."""


# pylint: disable=too-many-instance-attributes
class DeskController:
    """Controls the desk via bluetooth based on events from Twitch.

    If a reward is queued it will send commands to the desk's bluetooth control unit to move the
    desk to a standing or sitting position.

    The controller will also deal with marking rewards as redeemed or refunding points if the reward
    cannot be fulfilled e.g. if a user redeems "Change to Standing Desk" and the desk is already in
    the standing position.

    The controller can also support listening for bits events.

    :param config: DeskConfig object holding the configuration for the DeskController
    """

    def __init__(
        self,
        config: DeskConfig,
    ) -> None:
        self.config = config

        self.height = self.config.desk_height_sitting
        self.state = common.STATE_SITTING

        self.client = BleakClient(self.config.controller_mac)

        if self.config.display_server_enabled:
            self.sio_client = socketio.Client(reconnection=False)

        self.running = False
        self.twitch = None
        self.broadcaster_id = None
        self.desk_up_reward_id = None
        self.desk_down_reward_id = None
        self.eventsub = None
        self.reconnect_bluetooth_required = False
        self.reconnect_display_server_required = False

    def configure_signal_handlers(self) -> None:
        """Ensure graceful shutdown is handled on SIGINT and SIGTERM signals (only works for
        linux)."""
        LOG.debug("configuring signal handlers")
        loop = asyncio.get_event_loop()
        try:
            loop.add_signal_handler(
                signal.SIGINT, lambda: asyncio.create_task(self.exit_gracefully())
            )
            loop.add_signal_handler(
                signal.SIGTERM, lambda: asyncio.create_task(self.exit_gracefully())
            )
        except NotImplementedError as exp:
            LOG.warning("Could not set up signal handlers: %s", exp)

    async def exit_gracefully(self) -> None:
        """Gracefully shut down the controller."""
        self.running = False
        if self.eventsub:
            LOG.info("stopping eventsub...")
            await self.eventsub.stop()
        if self.twitch:
            LOG.info("disconnecting from twitch api...")
            await self.twitch.close()
        if self.config.display_server_enabled:
            LOG.info("disconnecting from display server...")
            self.sio_client.disconnect()
        LOG.info("controller shutting down")
        sys.exit(0)

    def on_notification(self, sender: BleakGATTCharacteristic, data: bytes) -> None:
        """Keep track of the desk height in realtime by listening for GATT notifications.

        If a notification is received for a height update (seems to happen constantly when the desk
        is moving), we use the callback function to update the web app display.

        :param sender: GATT characteristic of the notification
        :param data: data in the notification
        """
        del sender

        height_new = common.get_height_in_cm(data)

        LOG.debug("height=%s height_new=%s", self.height, height_new)
        if height_new > self.height:
            # If height is increasing the desk is moving up.
            self.state = common.STATE_GOING_UP
        elif height_new < self.height:
            # If height is decreasing the desk is moving down.
            self.state = common.STATE_GOING_DOWN
        elif height_new > self.config.desk_height_standing - 2:
            # If the desk is not changing height and close to standing position, assume we are
            # standing.
            self.state = common.STATE_STANDING
        elif height_new < self.config.desk_height_sitting + 2:
            # If the desk is not changing height and close to sitting position, assume we are
            # sitting.
            self.state = common.STATE_SITTING
        else:
            # If the desk isn't moving and is somewhere between the sitting and standing
            # position, it probably got stuck or manually stopped so mark it as stopped.
            self.state = common.STATE_STOPPED

        self.height = height_new
        LOG.debug("state=%s", self.state)
        if self.config.display_server_enabled:
            self.display_height()

    async def callback_bits(self, data: ChannelCheerEvent) -> None:
        """Callback for bit redemptions that moves desk according to the message.

        :param data: data of the pubsub message
        """
        bits_used = data.event.bits
        chat_message = data.event.message
        user = data.event.user_name
        if not user:
            user = "anonymous"

        if bits_used < self.config.min_bits:
            LOG.info("Not enough bits to move desk")
            return

        if common.DESK_UP_BITS_COMMAND in chat_message.split(" "):
            LOG.info("%s command found", common.DESK_UP_BITS_COMMAND)
            LOG.info("%s is moving desk up", user)
            await self.move_desk_up()
        elif common.DESK_DOWN_BITS_COMMAND in chat_message.split(" "):
            LOG.info("%s command found", common.DESK_DOWN_BITS_COMMAND)
            LOG.info("%s is moving desk down", user)
            await self.move_desk_down()
        elif common.DESK_GENERIC_BITS_COMMAND in chat_message.split(" "):
            # this will only work reliably if height detection is enabled
            LOG.info("%s command found", common.DESK_GENERIC_BITS_COMMAND)
            if self.state in (common.STATE_GOING_DOWN, common.STATE_SITTING):
                LOG.info("%s is moving desk up", user)
                await self.move_desk_up()
            elif self.state in (common.STATE_GOING_UP, common.STATE_STANDING):
                LOG.info("%s is moving desk down", user)
                await self.move_desk_down()
        else:
            LOG.info("No desk command found in bits message")

    async def callback_channel_points(
        self, data: ChannelPointsCustomRewardRedemptionAddEvent
    ) -> None:
        """Callback for channel point redemptions that moves desk according to the reward redeemed.

        :param data: data of the pubsub message
        """
        reward_id = data.event.reward.id
        redemption_id = data.event.id
        user = data.event.user_name

        if reward_id == self.desk_up_reward_id:
            await self.handle_desk_up_reward(redemption_id, user)
        if reward_id == self.desk_down_reward_id:
            await self.handle_desk_down_reward(redemption_id, user)

    async def move_desk_up(self) -> None:
        """Sends commands to the desk to move it to the standing position."""

        await self.client.write_gatt_char(self.config.data_in_uuid, common.DESK_STOP_GATT_CMD)
        await asyncio.sleep(1)
        await self.client.write_gatt_char(
            self.config.data_in_uuid,
            common.get_height_set_command(self.config.desk_height_standing),
        )
        self.state = common.STATE_GOING_UP

    async def move_desk_down(self) -> None:
        """Sends commands to the desk to move it to the sitting position."""

        await self.client.write_gatt_char(self.config.data_in_uuid, common.DESK_STOP_GATT_CMD)
        await asyncio.sleep(1)
        await self.client.write_gatt_char(
            self.config.data_in_uuid,
            common.get_height_set_command(self.config.desk_height_sitting),
        )
        self.state = common.STATE_GOING_DOWN

    async def reconnect_bluetooth(self) -> None:
        """Attempts to reconnect to desk via bluetooth."""

        LOG.info("attempting to reconnect to desk via bluetooth...")
        try:
            await self.client.disconnect()
            await asyncio.sleep(1)
            await self.client.connect()
            await asyncio.sleep(1)
            self.reconnect_bluetooth_required = False
        except (BleakError, OSError, TimeoutError) as exp:
            LOG.error("failed to reconnect: %s", exp)
            return

        LOG.info("reconnected successfully")

    async def reconnect_display_server(self) -> None:
        """Attempts to recconect to the display server."""
        try:
            self.sio_client.connect("http://" + self.config.display_server_address)
            LOG.info("reconnected to display server")
        except socketio.client.exceptions.SocketIOError as exp:
            LOG.error("failed to reconnect: %s", exp)
            self.reconnect_display_server_required = False

    def display_height(self) -> None:
        """Sends a height update to the display server."""
        try:
            self.sio_client.emit("height_update", str(self.height))
        except socketio.client.exceptions.SocketIOError:
            LOG.error("failed to connect to display server")
            self.reconnect_display_server_required = True

    async def handle_desk_up_reward(self, redemption_id: str, user: str) -> None:
        """Handle a singular "Change to Standing Desk" channel points redemption.

        :param redemption_id: UUID of the channel points redemption
        :param user: name of the user claiming the redemption
        :raises BTBaseException: when there is an issue communicating with the desk
        """
        assert self.desk_up_reward_id is not None
        # can only refund points if height detection is enabled
        if self.config.desk_height_detection_enabled:
            if self.state in (common.STATE_GOING_UP, common.STATE_STANDING):
                LOG.info("refunding %s (desk moving up or standing already)", user)
                await self.twitch.update_redemption_status(
                    self.broadcaster_id,
                    self.desk_up_reward_id,
                    redemption_id,
                    CustomRewardRedemptionStatus.CANCELED,
                )
                return

        LOG.info("%s is moving desk up", user)
        try:
            await self.move_desk_up()
        except (BleakError, OSError) as exp:
            LOG.error("failed to move desk up: %s", exp)
            self.reconnect_bluetooth_required = True
            LOG.info("refunding %s (failed to move desk)", user)
            await self.twitch.update_redemption_status(
                self.broadcaster_id,
                self.desk_up_reward_id,
                redemption_id,
                CustomRewardRedemptionStatus.CANCELED,
            )
            return

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
        assert self.desk_down_reward_id is not None
        # can only refund points if height detection is enabled
        if self.config.desk_height_detection_enabled:
            if self.state in (common.STATE_GOING_DOWN, common.STATE_SITTING):
                LOG.info("refunding %s (desk moving down or sitting already)", user)
                await self.twitch.update_redemption_status(
                    self.broadcaster_id,
                    self.desk_down_reward_id,
                    redemption_id,
                    CustomRewardRedemptionStatus.CANCELED,
                )
                return
        LOG.info("%s is moving desk down", user)
        try:
            await self.move_desk_down()
        except (BleakError, OSError) as exp:
            LOG.error("failed to move desk down: %s", exp)
            self.reconnect_bluetooth_required = True
            LOG.info("refunding %s (failed to move desk)", user)
            await self.twitch.update_redemption_status(
                self.broadcaster_id,
                self.desk_up_reward_id,
                redemption_id,
                CustomRewardRedemptionStatus.CANCELED,
            )
            return

        await self.twitch.update_redemption_status(
            self.broadcaster_id,
            self.desk_down_reward_id,
            redemption_id,
            CustomRewardRedemptionStatus.FULFILLED,
        )

    async def configure_twitch(self) -> None:
        """Configures connection to the twitch API and sets up event listeners."""

        LOG.info("configuring twitch authentication...")
        self.twitch = await Twitch(self.config.client_id, self.config.client_secret)
        assert self.twitch is not None
        await self.twitch.authenticate_app([])
        target_scope = common.get_target_scope(
            self.config.channel_points_enabled, self.config.bits_enabled
        )

        await self.twitch.set_user_authentication(
            self.config.auth_token, target_scope, self.config.refresh_token
        )
        broadcaster = await first(self.twitch.get_users(logins=[self.config.broadcaster_name]))
        assert broadcaster is not None
        self.broadcaster_id = broadcaster.id

        self.eventsub = EventSubWebsocket(self.twitch, callback_loop=asyncio.get_running_loop())
        assert self.eventsub is not None
        self.eventsub.start()

        if self.config.channel_points_enabled:
            LOG.info("checking channel points rewards...")
            assert self.config.desk_up_reward_name is not None
            assert self.config.desk_down_reward_name is not None
            assert self.broadcaster_id is not None
            self.desk_up_reward_id, self.desk_down_reward_id = await common.set_up_channel_points(
                self.twitch,
                self.broadcaster_id,
                self.config.desk_up_reward_name,
                self.config.desk_down_reward_name,
            )
            LOG.info("listening for channel points...")
            await self.eventsub.listen_channel_points_custom_reward_redemption_add(
                self.broadcaster_id, self.callback_channel_points
            )

        if self.config.bits_enabled:
            LOG.info("listening for bits...")
            await self.eventsub.listen_channel_cheer(self.broadcaster_id, self.callback_bits)

    async def run(self) -> None:
        """Run the desk controller."""

        self.configure_signal_handlers()

        self.running = True
        if self.config.display_server_enabled:
            # connect to the display server
            LOG.info(
                "connecting to display server at http://%s...", self.config.display_server_address
            )
            try:
                self.sio_client.connect("http://" + self.config.display_server_address)
            except socketio.client.exceptions.SocketIOError as exp:
                LOG.error(
                    "failed to connect to display server at %s: %s",
                    self.config.display_server_address,
                    exp,
                )
                raise FatalException from exp

        # connect to the desk via bluetooth
        LOG.info("connecting to desk bluetooth controller at %s...", self.config.controller_mac)
        try:
            await self.client.connect()
            if self.config.desk_height_detection_enabled:
                # start notifier for desk height updates
                await self.client.start_notify(self.config.data_out_uuid, self.on_notification)
            await asyncio.sleep(1)
            # ensure desk is in sitting position
            LOG.info("ensuring desk is in sitting position...")
            await self.move_desk_down()
        except (BleakError, OSError) as exp:
            LOG.error("failed to connect to desk via bluetooth: %s", exp)
            raise FatalException from exp

        try:
            # configure twitch api connectivity
            await self.configure_twitch()
        except TwitchAPIException as exp:
            LOG.error("failed to configure twitch api connectivity: %s", exp)
            raise FatalException from exp

        LOG.info("finished starting controller")
        while self.running:
            LOG.debug("controller is running")
            if self.config.display_server_enabled:
                if self.reconnect_display_server_required:
                    await self.reconnect_display_server()
                self.display_height()
            if self.reconnect_bluetooth_required:
                await self.reconnect_bluetooth()
            await asyncio.sleep(POLL_INTERVAL)
