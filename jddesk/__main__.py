"""Main entrypoints for the program."""
import logging
import pathlib
import asyncio

from bleak.exc import BleakError

from jddesk import desk, common
from jddesk.config import DeskConfig, DeskConfigError

POLL_INTERVAL = 1

LOG = logging.getLogger("jddesk")
logging.basicConfig(
    format="%(asctime)s %(levelname)s %(message)s", level=logging.INFO, datefmt="%Y-%m-%d %H:%M:%S"
)


async def run() -> None:
    """Initializes and runs the desk controller."""

    # read config
    try:
        LOG.info("parsing config file...")
        config_file_path = str(pathlib.Path.home() / common.CONFIG_FILE_NAME)
        config = DeskConfig(config_file_path)
        config.load_config()
    except DeskConfigError as exp:
        LOG.error("invalid config: %s", exp)
        common.custom_exit(1)

    try:
        desk_controller = desk.DeskController(config)
    except BleakError as exp:
        LOG.error("Could not initialize bluetooth connection: %s", exp)
        common.custom_exit(1)

    # start the desk controller
    try:
        await desk_controller.run()
    except desk.FatalException:
        common.custom_exit(1)


def main() -> None:
    """Main entrypoint to the program."""
    asyncio.run(run(), debug=False)
    common.custom_exit(0)


if __name__ == "__main__":
    main()
