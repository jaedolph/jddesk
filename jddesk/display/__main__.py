"""Sets up a webserver to display the desk height."""
import logging
from jddesk.display import web


LOG = logging.getLogger("jddesk")
logging.basicConfig(
    format="%(asctime)s %(levelname)s %(message)s", level=logging.INFO, datefmt="%Y-%m-%d %H:%M:%S"
)


def main() -> None:
    """Start the display server."""
    LOG.info("starting display server")
    web.socketio.run(web.app, host="0.0.0.0")


if __name__ == "__main__":
    main()
