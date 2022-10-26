from .const import *
from .utils import _LOGGER


class InverterData:
    """
    Holding all current inverter measurements
    """
    def __init__(self, addresses):
        self._data = {}
        # Add inverter addresses we expect to get data from
        # This helps noticing if metrics from inverters are missing (needed for accumulated metrics method)
        for addr in addresses:
            self.add_inverter(str(addr))

    def add_inverter(self, addr):
        if addr not in self._data.keys():
            self._data[str(addr)] = {}

    def set_metric(self, metrics_conf_name, addr, value):
        # TODO: Make clear that value should be numeric (int/float) because of get_accumulated_metrics.
        if metrics_conf_name not in INVERTER_METRICS:
            _LOGGER.warning(f"Inverter '{addr}'. Unknown metric: '{metrics_conf_name}'. Not adding it.")
            return
        self._data[str(addr)][metrics_conf_name] = value

    def get_metric(self, addr, metrics_conf_name):
        try:
            return self._data[str(addr)][metrics_conf_name]
        except KeyError as e:
            _LOGGER.debug(f"Inverter '{addr}'. Metrics '{metrics_conf_name}' not found in inverter data.")
        return None

    def get_accumulated_metrics(self, metrics_conf_name, allow_partial=False):
        """
        Allow partial also means that we return 0 if no inverter has that metric set.
        """
        value = 0
        for addr in self._data.keys():
            v = self.get_metric(addr, metrics_conf_name)
            if v is None:
                if not allow_partial:
                    # Don't return partially aggregated metrics.
                    # A drop because of a reading error of inverter(s) could confuse HA and end users, too.
                    _LOGGER.debug("Got partially aggregated metric. Dropping it.")
                    return None
                else:
                    v = 0
            value += v
        return value
