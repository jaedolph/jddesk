"""Main entrypoints for the program."""
import logging
import asyncio
import argparse
import threading
import traceback

from jddesk import desk, common, setup_config
from jddesk.display import web
from jddesk.config import DeskConfig, DeskConfigError

POLL_INTERVAL = 1

LOG = logging.getLogger("jddesk")


def load_config(config_file_path: str) -> DeskConfig:
    """Loads config file.

    :param config_file_path: path to the config file to read
    :return: DeskConfig object containing the configuration from the config file
    """

    try:
        LOG.info("parsing config file...")
        config = DeskConfig(config_file_path)
        config.load_config()
    except DeskConfigError as exp:
        LOG.error("invalid config: %s", exp)
        common.custom_exit(1)

    return config


async def run_controller(config: DeskConfig) -> None:
    """Initializes and runs the desk controller.

    :param config: DeskConfig object containing the configuration"""

    desk_controller = desk.DeskController(config)

    # start the desk controller
    try:
        await desk_controller.run()
    except desk.FatalException:
        common.custom_exit(1)


def run_display_server(config: DeskConfig) -> None:
    """Start the display server.

    :param config: DeskConfig object containing the configuration"""

    LOG.info("starting display server")
    host, port = config.display_server_address.split(":")

    web.socketio.run(web.app, host=host, port=port, allow_unsafe_werkzeug=True)


def run_setup_config(config_file_path: str) -> None:
    """Run the configuration helper.

    :param config_file_path: path to the config file to write/edit
    """

    LOG.info("starting configuration helper")
    try:
        asyncio.run(setup_config.configure(config_file_path))
    except Exception as exp:  # pylint: disable=broad-exception-caught
        traceback.print_tb(exp.__traceback__)
        print(f"Fatal exception occurred: {exp}")
        common.custom_exit(1)
    common.custom_exit(0)


def main() -> None:
    """Main entrypoint to the program."""

    parser = argparse.ArgumentParser(
        prog="jddesk", description="Controls your desk from twitch.tv events"
    )
    parser.add_argument("--configure", action="store_true", help="run the configuration utility")
    parser.add_argument(
        "--config-file", default=common.DEFAULT_CONFIG_FILE_PATH, help="path to config file"
    )
    parser.add_argument("--debug", action="store_true", help="turn on debug logging")
    parser.add_argument("--log-file", help="path to log file")

    args = parser.parse_args()

    # configure logging
    log_level = logging.INFO
    log_handlers: list[logging.Handler] = [logging.StreamHandler()]
    if args.debug:
        LOG.info("setting log level to DEBUG")
        log_level = logging.DEBUG
        LOG.debug("test")

    if args.log_file:
        log_handlers.append(logging.FileHandler(args.log_file))

    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(message)s",
        level=log_level,
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=log_handlers,
    )

    # run config helper utility if required
    if args.configure:
        run_setup_config(args.config_file)
        return

    # load config file
    config = load_config(args.config_file)

    # run display server in the background if required
    display_server = None
    if config.display_server_enabled:
        display_server = threading.Thread(target=run_display_server, args=[config])
        display_server.daemon = True
        display_server.start()

    # run the desk controller
    asyncio.run(run_controller(config), debug=False)

    common.custom_exit(0)


if __name__ == "__main__":
    main()
