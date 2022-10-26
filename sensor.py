"""Platform for sensor integration."""
from __future__ import annotations

import datetime
import logging
import random
import copy

from homeassistant.components.sensor import SensorEntity, STATE_CLASS_TOTAL_INCREASING, STATE_CLASS_MEASUREMENT
from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.const import POWER_WATT, ENERGY_WATT_HOUR, DEVICE_CLASS_POWER, DEVICE_CLASS_ENERGY
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .const import *
from .types import InverterQueryResults

_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(hass: HomeAssistant, config, async_add_entities, discovery_info=None):
    """Setup the sensor platform."""
    coordinator = hass.data[DOMAIN]["coordinator"]
    inverter_addresses = hass.data[DOMAIN]["conf"][CONF_INVERTER_ADDRESSES]

    sensors = []

    """
    Sensors representing accumulated data of all inverters
    """
    power_spec_all_inverters = AuroraSensorSpec(address=None,
                                                metric_data_name=DATA_POWER,
                                                device_class=DEVICE_CLASS_POWER,
                                                state_class=STATE_CLASS_MEASUREMENT,
                                                native_unit_of_measurement=POWER_WATT,
                                                user_friendly_name="Aurora inverter power production total",
                                                unique_id="aurora_inverter_power_production_total",
                                                # Force updates only for power spec since it's needed for
                                                # subsequent statistics sensor calculations
                                                force_update=True)
    sensors.append(AuroraSensor(coordinator, sensor_spec=power_spec_all_inverters))
    energy_spec_all_inverters = AuroraSensorSpec(address=None,
                                                 metric_data_name=DATA_ENERGY_TOTAL,
                                                 device_class=DEVICE_CLASS_ENERGY,
                                                 state_class=STATE_CLASS_TOTAL_INCREASING,
                                                 native_unit_of_measurement=ENERGY_WATT_HOUR,
                                                 user_friendly_name="Aurora inverter energy total production total",
                                                 unique_id="aurora_inverter_energy_total_production_total")
    sensors.append(AuroraNoneIsLastNonNoneValueNonAllowPartialSensor(coordinator, sensor_spec=energy_spec_all_inverters))
    for inverter_address in inverter_addresses:
        """
        Sensors representing data of individual inverters
        """
        sensors.append(AuroraInverterPowerStateSensor(coordinator, addr=inverter_address))

        power_spec_inverter = copy.copy(power_spec_all_inverters)
        power_spec_inverter.address = inverter_address
        power_spec_inverter.user_friendly_name = f"Aurora inverter {inverter_address} power production"
        power_spec_inverter.unique_id = f"aurora_inverter_{inverter_address}_power_production"
        sensors.append(AuroraSensor(coordinator, sensor_spec=power_spec_inverter))

        energy_spec_inverter = copy.copy(energy_spec_all_inverters)
        energy_spec_inverter.address = inverter_address
        energy_spec_inverter.user_friendly_name = f"Aurora inverter {inverter_address} energy total production"
        energy_spec_inverter.unique_id = f"aurora_inverter_{inverter_address}_energy_total_production"
        sensors.append(AuroraNoneIsLastNonNoneValueNonAllowPartialSensor(coordinator, sensor_spec=energy_spec_inverter))

    async_add_entities(sensors, True)


class AuroraInverterPowerStateSensor(CoordinatorEntity, BinarySensorEntity):
    """
    Represent inverter power state: on/off
    """
    def __init__(self, coordinator: DataUpdateCoordinator[InverterQueryResults], addr):
        super().__init__(coordinator)
        self._addr = addr

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return f"Aurora inverter {self._addr} power state"

    @property
    def unique_id(self) -> str | None:
        return f"aurora_inverter_{self._addr}_power_state"

    @property
    def is_on(self) -> bool | None:
        v = self.coordinator.data.get_metric(self._addr, DATA_INVERTER_REACHABLE)
        if v is None:
            return False
        return v == 1

    @property
    def available(self):
        v = self.coordinator.data.get_metric(self._addr, DATA_INVERTER_REACHABLE)
        if v is None:
            return False
        return True

    @property
    def icon(self) -> str | None:
        return "hass:power"


class AuroraSensorSpec:
    def __init__(self, address: str | None, metric_data_name: str, device_class: str, state_class: str, native_unit_of_measurement: str,
                 user_friendly_name: str, unique_id: str, force_update: bool = False):
        # None means get accumulated metrics for all inverters; str means get only metric for specific inverter address
        self.address = address
        self.metric_data_name = metric_data_name
        self.device_class = device_class
        self.state_class = state_class
        self.native_unit_of_measurement = native_unit_of_measurement
        self.user_friendly_name = user_friendly_name
        self.unique_id = unique_id
        # Update sensor even if value didn't change (needed for e.g. calculation of mean in statistics sensor)
        self.force_update = force_update


class AuroraSensor(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator: DataUpdateCoordinator[InverterQueryResults], sensor_spec: AuroraSensorSpec):
        super().__init__(coordinator)
        self._last_non_none_value = None
        self._sensor_spec = sensor_spec

    @property
    def force_update(self):
        """Force update."""
        return self._sensor_spec.force_update

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return self._sensor_spec.user_friendly_name

    @property
    def unique_id(self) -> str | None:
        return self._sensor_spec.unique_id

    @property
    def device_class(self) -> str | None:
        return self._sensor_spec.device_class

    @property
    def state_class(self) -> str | None:
        return self._sensor_spec.state_class

    @property
    def native_value(self):
        """
        Returning 0 looks better than None resulting in "unknown"
        Partial results are allowed.
        """
        if self._sensor_spec.address is None:
            v = self.coordinator.data.get_accumulated_metrics(self._sensor_spec.metric_data_name, allow_partial=True)
        else:
            v = self.coordinator.data.get_metric(self._sensor_spec.address, self._sensor_spec.metric_data_name)
        if v is None:
            return 0
        return v

    @property
    def native_unit_of_measurement(self) -> str | None:
        return self._sensor_spec.native_unit_of_measurement

    @property
    def available(self):
        """
        The sensor is available when inverter_reachable is present for all inverters/for the current inverter.
        """
        if self._sensor_spec.address is None:
            # This sensor is responsible for accumulated metric
            v = self.coordinator.data.get_accumulated_metrics(DATA_INVERTER_REACHABLE, allow_partial=False)
        else:
            # This sensor is responsible for one specific inverter metric
            v = self.coordinator.data.get_metric(self._sensor_spec.address, DATA_INVERTER_REACHABLE)
        if v is None:
            return False
        return True


class AuroraNoneIsLastNonNoneValueNonAllowPartialSensor(AuroraSensor):
    @property
    def native_value(self):
        """
        Return last non-none value if measurement is none.
        Partial results not allowed (e.g., for total increasing)
        """
        # TODO: How to keep last state more persistent (across HA restarts?)
        if self._sensor_spec.address is None:
            v = self.coordinator.data.get_accumulated_metrics(self._sensor_spec.metric_data_name, allow_partial=False)
        else:
            v = self.coordinator.data.get_metric(self._sensor_spec.address, self._sensor_spec.metric_data_name)
        if v is None:
            return self._last_non_none_value
        else:
            self._last_non_none_value = v
        return v
