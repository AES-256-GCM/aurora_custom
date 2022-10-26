"""Custom Aurora inverter integration."""
from typing import Callable, Generic, TypeVar
T = TypeVar("T")

from datetime import timedelta
from homeassistant import core
from homeassistant.helpers.discovery import async_load_platform
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .inverter_fetcher import InverterFetcher, InverterFetcherFactory
from .const import *
from .utils import _LOGGER


async def async_setup(hass: core.HomeAssistant, config: dict) -> bool:
    """Set up the platform.

    @NOTE: `config` is the full dict from `configuration.yaml`.

    :returns: A boolean to indicate that initialization was successful.
    """
    # TODO: Validate config (required fields)
    conf = config[DOMAIN]

    update_interval = 60
    if conf[CONF_UPDATE_INTERVAL]:
        update_interval = conf[CONF_UPDATE_INTERVAL]

    fetcher_factory = InverterFetcherFactory()
    coordinator = MyCoordinator(
        hass,
        _LOGGER,
        # Name of the data. For logging purposes.
        name=DOMAIN,
        update_method=fetcher_factory.get_fetcher(conf).fetch_inverter_data,
        update_interval=timedelta(seconds=update_interval),
    )

    # Fetch initial data so we have data when entities subscribe
    await coordinator.async_refresh()

    hass.data[DOMAIN] = {
        "conf": conf,
        "coordinator": coordinator,
    }
    hass.async_create_task(async_load_platform(hass, "sensor", DOMAIN, {}, conf))
    return True


class MyCoordinator(DataUpdateCoordinator):
    async def _async_update_data(self) -> T:
        """Fetch the latest data from the source."""
        if self.update_method is None:
            raise NotImplementedError("Update method not implemented")
        return await self.update_method(self.hass)
