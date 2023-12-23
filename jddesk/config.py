"""DeskConfig class used for storing/validating configuration."""

import configparser
import re
import os


class DeskConfigError(Exception):
    """Custom exception thrown when the configuration is invalid."""


# pylint: disable=too-many-public-methods
class DeskConfig:
    """Stores and manages config for the desk controller.

    :param config_file_path: path to the config file to read/write
    """

    def __init__(self, config_file_path: str) -> None:
        """Initialize the DeskConfig."""
        self.config_file_path = config_file_path
        self.config = configparser.ConfigParser()

    def new_config(self) -> None:
        """Creates sections so new config can be created."""
        self.config.add_section("DESK")
        self.config.add_section("TWITCH")
        self.config.add_section("DISPLAY_SERVER")

    def load_config(self) -> None:
        """Creates sections so new config can be created."""
        if not os.path.isfile(self.config_file_path):
            raise DeskConfigError(f'could not open config file "{self.config_file_path}"')

        self.config.read(self.config_file_path)
        self.validate_config()

    def validate_desk_section(self) -> None:
        """Validates the [DESK] section of the config."""
        try:
            assert self.config.has_section("DESK")
            assert self.is_mac_address(self.controller_mac)
            assert isinstance(self.desk_height_sitting, float)
            assert isinstance(self.desk_height_standing, float)
        except (configparser.Error, AssertionError, ValueError, KeyError) as exp:
            raise DeskConfigError(exp) from exp

    def validate_twitch_section(self) -> None:
        """Validates the [TWITCH] section of the config."""

        try:
            assert self.config.has_section("TWITCH")
            assert isinstance(self.client_id, str)
            assert isinstance(self.client_secret, str)
            assert isinstance(self.broadcaster_name, str)
            assert isinstance(self.auth_token, str)
            assert isinstance(self.refresh_token, str)
            assert isinstance(self.bits_enabled, bool)
            if self.bits_enabled:
                assert isinstance(self.min_bits, int)
            assert isinstance(self.channel_points_enabled, bool)
            if self.channel_points_enabled:
                assert isinstance(self.desk_up_reward_name, str)
                assert isinstance(self.desk_down_reward_name, str)
        except (configparser.Error, AssertionError, ValueError, KeyError) as exp:
            raise DeskConfigError(exp) from exp

    def validate_display_server_section(self) -> None:
        """Validates the [DISPLAY_SERVER] section of the config."""
        try:
            assert isinstance(self.display_server_enabled, bool)
            if self.display_server_enabled:
                assert isinstance(self.display_server_address, str)
        except (configparser.Error, AssertionError, ValueError, KeyError) as exp:
            raise DeskConfigError(exp) from exp

    def validate_config(self) -> None:
        """Validates that the current config."""
        self.validate_desk_section()
        self.validate_twitch_section()
        self.validate_display_server_section()

    def write_config(self) -> None:
        """Writes current config to file."""
        self.validate_config()
        with open(self.config_file_path, "w", encoding="utf-8") as config_file:
            self.config.write(config_file)

    @staticmethod
    def is_mac_address(value: str) -> bool:
        """Checks if value is a valid MAC address.

        :param value: value to check
        :return: true if the value is a MAC address, false if it is invalid
        """
        is_valid_mac = re.match(
            r"([0-9A-F]{2}[:]){5}[0-9A-F]{2}",
            string=value,
            flags=re.IGNORECASE,
        )

        if is_valid_mac is None:
            return False

        return bool(is_valid_mac.group())

    # pylint: disable=missing-function-docstring
    @property
    def controller_mac(self) -> str:
        return self.config["DESK"]["CONTROLLER_MAC"]

    @controller_mac.setter
    def controller_mac(self, value: str) -> None:
        self.config["DESK"]["CONTROLLER_MAC"] = value

    @property
    def desk_height_standing(self) -> float:
        return self.config.getfloat("DESK", "STANDING_HEIGHT")

    @desk_height_standing.setter
    def desk_height_standing(self, value: float) -> None:
        assert isinstance(value, float)
        self.config["DESK"]["STANDING_HEIGHT"] = str(value)

    @property
    def desk_height_sitting(self) -> float:
        return self.config.getfloat("DESK", "SITTING_HEIGHT")

    @desk_height_sitting.setter
    def desk_height_sitting(self, value: float) -> None:
        assert isinstance(value, float)
        self.config["DESK"]["SITTING_HEIGHT"] = str(value)

    @property
    def auth_token(self) -> str:
        return self.config["TWITCH"]["AUTH_TOKEN"]

    @auth_token.setter
    def auth_token(self, value: str) -> None:
        self.config["TWITCH"]["AUTH_TOKEN"] = value

    @property
    def refresh_token(self) -> str:
        return self.config["TWITCH"]["REFRESH_TOKEN"]

    @refresh_token.setter
    def refresh_token(self, value: str) -> None:
        self.config["TWITCH"]["REFRESH_TOKEN"] = value

    @property
    def client_id(self) -> str:
        return self.config["TWITCH"]["CLIENT_ID"]

    @client_id.setter
    def client_id(self, value: str) -> None:
        self.config["TWITCH"]["CLIENT_ID"] = value

    @property
    def client_secret(self) -> str:
        return self.config["TWITCH"]["CLIENT_SECRET"]

    @client_secret.setter
    def client_secret(self, value: str) -> None:
        self.config["TWITCH"]["CLIENT_SECRET"] = value

    @property
    def broadcaster_name(self) -> str:
        return self.config["TWITCH"]["BROADCASTER_NAME"]

    @broadcaster_name.setter
    def broadcaster_name(self, value: str) -> None:
        self.config["TWITCH"]["BROADCASTER_NAME"] = value

    @property
    def channel_points_enabled(self) -> bool:
        return self.config.getboolean("TWITCH", "ENABLE_CHANNEL_POINTS")

    @channel_points_enabled.setter
    def channel_points_enabled(self, value: bool) -> None:
        self.config["TWITCH"]["ENABLE_CHANNEL_POINTS"] = "yes" if value else "no"

    @property
    def desk_up_reward_name(self) -> str:
        return self.config["TWITCH"]["DESK_UP_REWARD_NAME"]

    @desk_up_reward_name.setter
    def desk_up_reward_name(self, value: str) -> None:
        self.config["TWITCH"]["DESK_UP_REWARD_NAME"] = value

    @property
    def desk_down_reward_name(self) -> str:
        return self.config["TWITCH"]["DESK_DOWN_REWARD_NAME"]

    @desk_down_reward_name.setter
    def desk_down_reward_name(self, value: str) -> None:
        self.config["TWITCH"]["DESK_DOWN_REWARD_NAME"] = value

    @property
    def bits_enabled(self) -> bool:
        return self.config.getboolean("TWITCH", "ENABLE_BITS")

    @bits_enabled.setter
    def bits_enabled(self, value: str) -> None:
        self.config["TWITCH"]["ENABLE_BITS"] = "yes" if value else "no"

    @property
    def min_bits(self) -> int:
        return self.config.getint("TWITCH", "MIN_BITS")

    @min_bits.setter
    def min_bits(self, value: int) -> None:
        self.config["TWITCH"]["MIN_BITS"] = str(value)

    @property
    def display_server_enabled(self) -> bool:
        return self.config.getboolean("DISPLAY_SERVER", "ENABLED")

    @display_server_enabled.setter
    def display_server_enabled(self, value: bool) -> None:
        self.config["DISPLAY_SERVER"]["ENABLED"] = "yes" if value else "no"

    @property
    def display_server_address(self) -> str:
        return self.config["DISPLAY_SERVER"]["ADDRESS"]

    @display_server_address.setter
    def display_server_address(self, value: str) -> None:
        self.config["DISPLAY_SERVER"]["ADDRESS"] = value

    # pylint: disable=
