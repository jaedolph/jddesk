# jddesk

Code powering [Jaedolph](twitch.tv/jaedolph)'s desk related channel points rewards.

The code may be useful for reference by streamers attempting to do a similar thing.

The code is very specific to my setup so would probably require a lot of hacking to get working with another type of desk. I have an [OMNIDESK PRO 2020](https://theomnidesk.com.au/collections/omnidesk-pro-2020) with the optional [bluetooth controller](https://theomnidesk.com.au/products/bluetooth-controller).

## Interaction modes

There are multiple interaction modes that can be enabled.

### Channel Points

If configured, the desk can be moved up and down using channel points rewards. e.g.
- "Change to standing desk" - moves the desk to standing position
- "Change to sitting desk" - moves the desk to sitting position

Channel points will be refunded to users if the desk does not need to move or fails to move.

The controller will automatically create the channel points rewards once configured. These must not
be created manually in order for the controller to work. The costs/icons/cooldowns can be manually
modified once the rewards are created.

### Bits

If configured, the desk can be moved up and down using commands within a bits cheer. Currently the
commands are hard-coded as:
- `!desk` - moves the desk to sitting or standing based on its current position e.g. will move to
  standing position if currently sitting.
- `!desksit` - moves the desk to sitting position. Does nothing if the desk is already in sitting
  position.
- `!deskstand` - moves the desk to standing position. Does nothing if the desk is already in standing
  position.

An example cheer message that would trigger the desk to move:
```
cheer500 !desk streamer why don't you stand up for a bit KEKW
```

Bits do not get refunded if the desk does not move (I don't think this is possible with how bits work).

# Installation

## Install using pip

Installation has been tested on Fedora 38 using python 3.11 but should work on other Linux distributions.
```bash
python3 -m pip install . --user
jddesk --configure
```

## Install on Windows

Installation has been tested on Windows 11.

1. Download the latest release zip file
2. Copy the zip to a location such as "Documents"
3. Right click and select "Extract here"
4. Follow [README.txt](windows/README.txt) instructions in the extracted folder


# Browser source

The current desk height can be displayed in real time on stream using an OBS browser source.

The default url for this is:
```
http://localhost:5000
```

To configure a custom url see the **Configuration** section.

# Configuration

## Configuration helper utility
The application can be configured using a configuration helper utility by adding the `--configure`
flag to the program. Note that this does not currently work inside the docker image.
```
jddesk --configure
```

## Configuration example

```ini
[DESK]
# desk configuration
controller_mac = 01:02:03:04:05:06 # mac address of the bluetooth controller
standing_height = 122.9 # desk standing height in centimeters
sitting_height = 76.4 # desk sitting height in centimeters

[TWITCH]
# oauth configuration (it is recommended to run `jddesk --configure` to create these)
client_id = 1234567890abcdefghijklmnopqrst # client id of custom twitch application
client_secret = abcdefghijklmnopqrst1234567890 # client secret of twitch application
broadcaster_name = jaedolph # username (not display name) of your channel
auth_token = poiuytrewqlkjhgfdsamnbvcxz1234 # user auth token
refresh_token = qwertyuiopasdfghjkl1234567890asdfghjkllkjhgfdsa123 # user refresh token

# channel points configuration
enable_channel_points = yes # allow channel points to move the desk
desk_up_reward_name = Change to standing desk # channel point reward name to move desk up
desk_down_reward_name = Change to sitting desk # channel point reward name to move desk down

# bits configuration
enable_bits = yes # allow bits cheers to move the desk
min_bits = 500 # minimum bits required in a cheer to move desk

[DISPLAY_SERVER]
# display server configuration
enabled = yes # enable the display server
address = localhost:5000 # socket to listen on for the display server
```

# Architecture
The application consists of two parts:
* The desk controller
* The display server (optional)

## Display server
The display server is a [Flask](https://flask.palletsprojects.com/) based web application for
displaying the desk height. It can be used as a browser source in OBS. The server uses the socketio
protocol to receive and transmit real time updates of the desk height.

## Desk controller
The desk controller creates [PubSub](https://dev.twitch.tv/docs/pubsub/) listeners for Twitch
channel points and/or bits events. If a configured channel points reward or a bits cheer with an
inline command is received, it will send commands to the desk's bluetooth controller.

The desk controller will also listen for "notify" events from the bluetooth controller which show
the current height of the desk. These notify events are sent every time the desk moves. Each event
is relayed to the display server so the current height of the desk can be displayed in OBS in real
time.

## System diagram
```mermaid
graph LR;
    obs(OBS Browser Source)
    display(Display Server)
    controller(Desk Controller)
    desk(Desk Bluetooth Module)
    twitchapi(Twitch API)

    obs-- http -->display
    display-- socketio -->obs
    controller-- socketio -->display
    controller<-- https -->twitchapi
    controller-- Bluetooth GATT commands -->desk
    desk-- Bluetooth GATT notifications -->controller
```

# Running with Podman

Ensure selinux perms are correct on your config file
```
chcon -t container_file_t ~/jddesk.ini
```

Run the controller
```
podman run \
    -d \
    --name jddesk \
    --net=host \
    -v /var/run/dbus/:/var/run/dbus/ \
    --userns=keep-id \
    --user=$UID \
    --privileged \
    -v ~/jddesk.ini:/usr/src/app/jddesk.ini docker.io/jaedolph/jddesk:latest
```

# Running on Kubernetes
I have only tested this on k3s running on a Raspberry Pi. May not work with latest version.

Edit the [kustomize.yml](kustomize/kustomize.yml) file and add the hostname of your desired route for the display server.

Edit the [.jddesk.ini](kustomize/.jddesk.yml) config file. This can be used to generate a secret with your config file.

Apply the resources:
```
kubectl kustomize kustomize/ | kubectl apply -f -
```
