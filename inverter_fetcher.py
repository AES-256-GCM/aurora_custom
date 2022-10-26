""" Fetch data from inverter(s) """
import logging
import requests
from typing import List

from .const import *
from .utils import _LOGGER
from .inverter import InverterData

from aurorapy.client import AuroraError, AuroraSerialClient
from prometheus_client.parser import text_string_to_metric_families


class InverterFetcherFactory:
    def get_fetcher(self, conf):
        if CONF_SERIAL_DEVICE in conf:
            return InverterFetcherSerial(conf)
        else:
            return InverterFetcherExporter(conf)


class InverterFetcher:
    def __init__(self, conf):
        self._inverter_addresses: list = conf[CONF_INVERTER_ADDRESSES]

    async def fetch_inverter_data(self, hass):
        # Run synchronous update methods
        data = await hass.async_add_executor_job(self.update)
        return data

    def update(self):
        raise NotImplementedError


class InverterFetcherExporter(InverterFetcher):
    def __init__(self, conf):
        super().__init__(conf)
        self._exporter_address = conf[CONF_EXPORTER]

    def update(self):
        data = InverterData(self._inverter_addresses)

        # Convert into list of str
        addresses_str = map(str, self._inverter_addresses)
        try:
            r = requests.get(self._exporter_address, params={'inverter_addresses': ','.join(addresses_str)},
                             timeout=10)
            if r.status_code != 200:
                _LOGGER.warning(f"Unexpected response from inverter exporter: Got HTTP code '{r.status_code}', expected 200.")
                # Always return InverterData!
                # Therefore the sensors will get a None value.
                return data

            for family in text_string_to_metric_families(r.text):
                for sample in family.samples:
                    # Grid Power
                    if sample.name == 'grid_power_reading':
                        # Making sure we have the unit we expect for our calculations
                        assert sample.labels["unit"] == 'W'
                        power = round(sample.value)
                        data.set_metric(DATA_POWER, sample.labels["inverter_addr"], power)
                    # Cumulated total energy
                    if sample.name == 'energy_total':
                        assert sample.labels["unit"] == 'kWh'
                        energy = round(sample.value * 1000)
                        data.set_metric(DATA_ENERGY_TOTAL, sample.labels["inverter_addr"], energy)
                    # Inverter reachable
                    if sample.name == 'inverter_reachable':
                        reachable = int(sample.value)
                        data.set_metric(DATA_INVERTER_REACHABLE, sample.labels["inverter_addr"], reachable)
        except requests.ConnectionError as e:
            _LOGGER.warning(f"Couldn't fetch exporter endpoint: {e}")
        except ValueError as e:
            _LOGGER.warning(f"ValueError parsing response: {e}. "
                            f"Is '{self._exporter_address}# a Prometheus metrics endpoint?")
        return data


class InverterFetcherSerial(InverterFetcher):
    def __init__(self, conf):
        super().__init__(conf)
        self._serial_address = conf[CONF_SERIAL_DEVICE]

    def update(self):
        data = InverterData(self._inverter_addresses)

        for addr in self._inverter_addresses:
            # TODO: Make timeout configurable via config?
            client = AuroraSerialClient(addr, self._serial_address, parity="N", timeout=3)
            try:
                client.connect()
                # Grid Power
                # https://gitlab.com/energievalsabbia/aurorapy/-/blob/master/docs/docs.md
                power = round(client.measure(index=3))
                data.set_metric(DATA_POWER, addr, power)
                # Cumulated total energy
                energy = round(client.cumulated_energy(period=5))
                data.set_metric(DATA_ENERGY_TOTAL, addr, energy)
                # Inverter reachable
                data.set_metric(DATA_INVERTER_REACHABLE, addr, 1)
            except AuroraError as e:
                data.set_metric(DATA_INVERTER_REACHABLE, addr, 0)
                # Also the (normal) situation of no response during darkness
                # raises an exception.
                if "No response after" in str(e):
                    _LOGGER.debug("No response from inverter (could be dark)")
            finally:
                if client.serline.isOpen():
                    client.close()
        return data
