"""Modules for interacting with the Twitch API."""

from typing import Any, cast

import requests

API_BASEURL = "https://api.twitch.tv/helix"
REQUEST_TIMEOUT = 5


class TwitchAPI:
    """Used to make calls to the Twitch API.

    :param auth_token: auth token of the service account
    :param client_id: client id of the service account
    :param broadcaster_id: numeric broadcaster id of the channel
    """

    # constants for marking rewards as done
    FULFILLED = "FULFILLED"
    CANCELED = "CANCELED"

    def __init__(self, auth_token: str, client_id: str, broadcaster_id: str):
        self.auth_token = auth_token
        self.client_id = client_id
        self.broadcaster_id = broadcaster_id

    def get_rewards(self) -> list[dict[str, Any]]:
        """Get a list of all channel points rewards the service account can manage.

        :raises RequestException: if the request fails
        """

        req = requests.get(
            f"{API_BASEURL}/channel_points/custom_rewards",
            headers={"Authorization": f"Bearer {self.auth_token}", "Client-ID": self.client_id},
            params={
                "broadcaster_id": self.broadcaster_id,
                "only_manageable_rewards": "True",
            },
            timeout=REQUEST_TIMEOUT,
        )
        req.raise_for_status()

        try:
            rewards = req.json()["data"]
        except KeyError as exp:
            raise requests.RequestException("could not rewards") from exp

        return cast(list[dict[str, Any]], rewards)

    def get_redemptions(self, reward_id: str) -> list[dict[str, Any]]:
        """Get a list of all unfulfilled channel points reward redemptions.

        :param reward_id: UUID of the reward to get redemptions for
        :raises RequestException: if the request fails
        """

        req = requests.get(
            f"{API_BASEURL}/channel_points/custom_rewards/redemptions",
            headers={"Authorization": f"Bearer {self.auth_token}", "Client-ID": self.client_id},
            params={
                "broadcaster_id": self.broadcaster_id,
                "reward_id": reward_id,
                "status": "UNFULFILLED",
            },
            timeout=REQUEST_TIMEOUT,
        )
        req.raise_for_status()

        try:
            redemptions = req.json()["data"]
        except KeyError as exp:
            raise requests.RequestException("could not rewards") from exp

        return cast(list[dict[str, Any]], redemptions)

    def mark_reward_done(self, reward_id: str, redemption_id: str, status: str) -> None:
        """Mark a channel points reward redemption as done.

        :param reward_id: UUID of the reward
        :param redemption_id: UUID of the reward redemption
        :param status: status to mark the reward as ("FULFILLED" or "CANCELED")

        :raises RequestException: if the request fails
        """
        reward_update = requests.patch(
            f"{API_BASEURL}/channel_points/custom_rewards/redemptions",
            headers={"Authorization": f"Bearer {self.auth_token}", "Client-ID": self.client_id},
            params={
                "broadcaster_id": self.broadcaster_id,
                "reward_id": reward_id,
                "id": redemption_id,
            },
            data={"status": status},
            timeout=REQUEST_TIMEOUT,
        )
        reward_update.raise_for_status()
