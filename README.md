# jddesk

Code powering [Jaedolph](twitch.tv/jaedolph)'s desk related channel points rewards.

The code may be useful for reference by streamers attempting to do a similar thing.

The code is very specific to my setup so would probably require a lot of hacking to get working with another type of desk. I have an [OMNIDESK PRO 2020](https://theomnidesk.com.au/collections/omnidesk-pro-2020) with the optional [bluetooth controller](https://theomnidesk.com.au/products/bluetooth-controller).

# Installation

This package requires several C/C++ libraries in order for the `gattlib` dependency to install properly.

I have only tested running this code on Fedora with Python 3.10.

Installing deps on Fedora:
```bash
sudo dnf install gcc-c++ python3-devel boost-python3-devel glib2-devel bluez-libs-devel
```

Install the packages:
```bash
python3 -m pip install . --user
```

# Config

Create a config file at `~/.jddesk.ini`

Example config file:
```ini
[BLUETOOTH]
CONTROLLER_MAC = 01:02:03:04:05:06

[TWITCH]
AUTH_TOKEN = 1234567890abcdefghijklmnopqrst
CLIENT_ID = abcdefghijklmnopqrst1234567890
BROADCASTER_ID = 12345678
```

`CONTROLLER_MAC` is the MAC address of the desk's bluetooth controller.

(TODO: Automate this process more)
You can get your `BROADCASTER_ID` from a site like this: https://www.streamweasels.com/tools/convert-twitch-username-to-user-id/


The `CLIENT_ID` you can get by creating an "application" here: https://dev.twitch.tv/console/apps/create

Once you have the `CLIENT_ID`, you can get the `AUTH_TOKEN` from here (it will be included in the URL you get redirected to): https://id.twitch.tv/oauth2/authorize?client_id=abcdefghijklmnopqrst1234567890&redirect_uri=http://localhost&response_type=token&scope=channel:read:redemptions%20channel:manage:redemptions%20openid

# Running the program

Ensure bluetooth is enabled.

Run the program:
```
jddesk
 * Serving Flask app 'jddesk.web'
 * Debug mode: off
```

The web server will run on port 5000, you can set up a browser source in OBS to display the desk
height in real time using http://yourhostname:5000.
