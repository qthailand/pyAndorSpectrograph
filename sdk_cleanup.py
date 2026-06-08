import logging

logger = logging.getLogger(__name__)


def _shutdown_sdk(sdk, *, live_running: bool = False, connected: bool = False) -> None:
    """Safely abort acquisition, switch cooling off if needed, then shut down the SDK."""
    if sdk is None:
        return

    try:
        if live_running:
            sdk.AbortAcquisition()
    except Exception as exc:
        logger.warning("AbortAcquisition during shutdown failed: %s", exc)

    try:
        if connected:
            sdk.CoolerOFF()
    except Exception as exc:
        logger.warning("CoolerOFF during shutdown failed: %s", exc)

    try:
        sdk.ShutDown()
    except Exception as exc:
        logger.warning("ShutDown during shutdown failed: %s", exc)
