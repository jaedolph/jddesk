"""Modules for controlling the desk."""

import logging
from time import sleep
from typing import Callable

from gattlib import BTBaseException, GATTRequester  # pylint: disable=no-name-in-module
from requests import RequestException

from jddesk.twitch import TwitchAPI

# Commands specific to the OmniDesk bluetooth controller.
# These commands were reverse engineered using packet captures of the bluetooth traffic.
DESK_UP_GATT_CMD = b"\xF1\xF1\x06\x00\x06\x7E"  # command will move desk to height preset 2
DESK_DOWN_GATT_CMD = b"\xF1\xF1\x05\x00\x05\x7E"  # command will move desk to height preset 1
DESK_STOP_GATT_CMD = b"\xF1\xF1\x2b\x00\x2b\x7E"  # command will stop the desk from moving

DESK_HEIGHT_READ_HANDLE = 0x0028  # GATT handle for receiving height notifications
DESK_HEIGHT_WRITE_HANDLE = 0x0025  # GATT handle for sending commands to the desk

# states for comparison
STATE_GOING_UP = "GOING UP"
STATE_GOING_DOWN = "GOING DOWN"
STATE_STANDING = "STANDING"
STATE_SITTING = "SITTING"
STATE_STOPPED = "STOPPED"

# these are hardcoded heights for my setup (in cm)
DESK_HEIGHT_STANDING = 123
DESK_HEIGHT_SITTING = 75

LOG = logging.getLogger("jddesk")


class DeskController(GATTRequester):  # type: ignore
    """Polls the Twitch API for desk related channel points rewards.

    If a reward is queued it will send commands to the desk's bluetooth control unit to move the
    desk to a standing or sitting position.

    The controller will also deal with marking rewards as redeemed or refunding points if the reward
    cannot be fulfilled e.g. if a user redeems "Change to Standing Desk" and the desk is already in
    the standing position.

    :param twitch_api: TwitchAPI object for making request to the Twitch API
    :param controller_mac: MAC address of the desk's bluetooth controller
    :param desk_up_reward_id: UUID of the channel points reward for moving the desk up
    :param desk_down_reward_id: UUID of the channel points reward for moving the desk down
    :param callback: callback function to run when a desk height update notification is received
    """

    def __init__(
        self,
        twitch_api: TwitchAPI,
        controller_mac: str,
        desk_up_reward_id: str,
        desk_down_reward_id: str,
        callback: Callable[[float], None],
    ) -> None:

        self.twitch_api = twitch_api
        self.controller_mac = controller_mac
        self.desk_up_reward_id = desk_up_reward_id
        self.desk_down_reward_id = desk_down_reward_id
        self.callback = callback
        self.height = 0.0
        self.state = STATE_STOPPED

        # initialise the GATTRequester without connecting
        super().__init__(self.controller_mac, False)

    @staticmethod
    def get_height_in_cm(data: bytes) -> float:
        """Takes binary data from the height update notification and converts it to a height in cm.

        :param data: data from the height update notification
        :returns: the height in centimeters
        """

        height = int.from_bytes(data[-5:-3], "big") / 10.0

        return height

    def on_notification(self, handle: int, data: bytes) -> None:
        """Keep track of the desk height in realtime by listening for GATT notifications.

        If a notification is received for a height update (seems to happen constantly when the desk
        is moving), we use the callback function to update the web app display.

        :param handle: GATT handle id for the notification
        :param data: data in the notification
        """
        if handle == DESK_HEIGHT_READ_HANDLE:

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
            # Run the callback function to notify the web app of the height change
            self.callback(self.height)

    def move_desk_up(self) -> None:
        """Sends commands to the desk to move it to the standing position."""

        self.write_cmd(DESK_HEIGHT_WRITE_HANDLE, DESK_STOP_GATT_CMD)
        sleep(1)
        self.write_cmd(DESK_HEIGHT_WRITE_HANDLE, DESK_UP_GATT_CMD)
        self.state = STATE_GOING_UP

    def move_desk_down(self) -> None:
        """Sends commands to the desk to move it to the sitting position."""

        self.write_cmd(DESK_HEIGHT_WRITE_HANDLE, DESK_STOP_GATT_CMD)
        sleep(1)
        self.write_cmd(DESK_HEIGHT_WRITE_HANDLE, DESK_DOWN_GATT_CMD)
        self.state = STATE_GOING_DOWN

    def reconnect(self) -> None:
        """Attempts to reconnect to desk via bluetooth."""

        LOG.info("attempting to reconnect to desk...")
        try:
            self.disconnect()
            sleep(2)
            self.connect()
        except BTBaseException as exp:
            LOG.exception("could not reconnect: %s", exp)

        LOG.info("reconnected successfully")

    def handle_desk_up_reward(self, redemption_id: str, user: str) -> None:
        """Handle a singular "Change to Standing Desk" channel points redemption.

        :param redemption_id: UUID of the channel points redemption
        :param user: name of the user claiming the redemption
        :raises BTBaseException: when there is an issue communicating with the desk
        """

        if self.state in (STATE_GOING_UP, STATE_STANDING):
            LOG.info("refunding %s (desk moving up or standing already)", user)
            self.twitch_api.mark_reward_done(
                self.desk_up_reward_id, redemption_id, self.twitch_api.CANCELED
            )
            return
        LOG.info("%s is moving desk up", user)
        try:
            self.move_desk_up()
        except BTBaseException as exp:
            LOG.error("refunding %s (failed to move desk)", user)
            self.twitch_api.mark_reward_done(
                self.desk_up_reward_id, redemption_id, self.twitch_api.CANCELED
            )
            raise BTBaseException from exp

        self.twitch_api.mark_reward_done(
            self.desk_up_reward_id, redemption_id, self.twitch_api.FULFILLED
        )

    def handle_desk_down_reward(self, redemption_id: str, user: str) -> None:
        """Handle a singular "Change to Sitting Desk" channel points redemption.

        :param redemption_id: UUID of the channel points redemption
        :param user: name of the user claiming the redemption
        :raises BTBaseException: when there is an issue communicating with the desk
        """

        if self.state in (STATE_GOING_DOWN, STATE_SITTING):
            LOG.info("refunding %s (desk moving down or sitting already)", user)
            self.twitch_api.mark_reward_done(
                self.desk_down_reward_id, redemption_id, self.twitch_api.CANCELED
            )
            return
        LOG.info("%s is moving desk down", user)
        try:
            self.move_desk_down()
        except BTBaseException as exp:
            LOG.error("refunding %s (failed to move desk)", user)
            self.twitch_api.mark_reward_done(
                self.desk_down_reward_id, redemption_id, self.twitch_api.CANCELED
            )
            raise BTBaseException from exp

        self.twitch_api.mark_reward_done(
            self.desk_down_reward_id, redemption_id, self.twitch_api.FULFILLED
        )

    def poll(self) -> None:
        """Poll the Twitch API for desk related channel points channel points redemptions."""

        try:
            # handle "Change to Standing Desk" channel points redemptions in the queue
            unfulfilled_up = self.twitch_api.get_redemptions(self.desk_up_reward_id)
            for redemption in unfulfilled_up:
                redemption_id = redemption["id"]
                user = redemption["user_name"]
                self.handle_desk_up_reward(redemption_id, user)

            # handle "Change to Sitting Desk" channel points redemptions in the queue
            unfulfilled_down = self.twitch_api.get_redemptions(self.desk_down_reward_id)
            for redemption in unfulfilled_down:
                redemption_id = redemption["id"]
                user = redemption["user_name"]
                self.handle_desk_down_reward(redemption_id, user)

        except RequestException as exp:
            LOG.exception("Error making request to twitch: %s", exp)
        except KeyError as exp:
            LOG.exception("Error with data returned: %s", exp)
        except BTBaseException as exp:
            LOG.exception("Bluetooth error: %s", exp)
            # attempt to reconnect
            self.reconnect()
        except Exception as exp:  # pylint: disable=broad-except
            LOG.exception("Unknown error: %s", exp)
