"""EcoFlow Alternator Charger 600W / 1000W (product id 9987).

A different model from the 800W charger (ALTERNATOR), on the same heartbeat layout.
What differs, read from the EcoFlow app's own MQTT traffic:

- The device reports from address 96 with protocol version 3, and the app sends every
  config write there. Writes addressed to 20 (the 800W's address) are ignored.
- The app no longer writes the start voltage through AlternatorSet.start_voltage (137).
  It writes car_batt_start_voltage (24) and car_batt_stop_voltage (22) together, as
  floats in volts, and the heartbeat reports them back in fields 551 and 550.
  start_voltage (138) only mirrors the start threshold truncated to whole volts.
"""

from typing import Any, override

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.components.number.const import NumberDeviceClass
from homeassistant.const import UnitOfElectricPotential

from custom_components.ecoflow_cloud.api import EcoflowApiClient
from custom_components.ecoflow_cloud.devices import const
from custom_components.ecoflow_cloud.devices.internal.alternator import (
    _HB_KEY,
    Alternator,
    AlternatorCommandMessage,
)
from custom_components.ecoflow_cloud.devices.internal.proto import ef_alternator_pb2 as alternator_pb2
from custom_components.ecoflow_cloud.entities import BaseNumberEntity

_START_VOLTAGE_KEY = f"{_HB_KEY}.carBattStartVoltage"
_STOP_VOLTAGE_KEY = f"{_HB_KEY}.carBattStopVoltage"


class _VoltageThresholdEntity(BaseNumberEntity):
    """Car battery start or stop threshold, reported and written as float volts."""

    _attr_native_unit_of_measurement = UnitOfElectricPotential.VOLT
    _attr_device_class = NumberDeviceClass.VOLTAGE
    _attr_native_step = 0.1
    _attr_mode = NumberMode.BOX

    def _update_value(self, val: Any) -> bool:
        # float32 on the wire, so 14.9 can arrive as 14.899999618530273
        return super()._update_value(round(float(val), 1))

    async def async_set_native_value(self, value: float) -> None:
        if self._command:
            volts = round(value, 1)
            self.send_set_message(volts, self.command_dict(volts))  # type: ignore[arg-type]


class AlternatorV2(Alternator):
    """EcoFlow Alternator Charger 600W / 1000W."""

    _DEVICE_ADDRESS = 96
    _PROTOCOL_VERSION = 3

    @override
    def _voltage_numbers(self, client: EcoflowApiClient) -> list[NumberEntity]:
        return [
            _VoltageThresholdEntity(
                client,
                self,
                _START_VOLTAGE_KEY,
                const.ALTERNATOR_START_VOLTAGE,
                11,
                30,
                lambda value, params: self._thresholds_write(start=value, stop=params.get(_STOP_VOLTAGE_KEY)),
            ),
            _VoltageThresholdEntity(
                client,
                self,
                _STOP_VOLTAGE_KEY,
                const.ALTERNATOR_STOP_VOLTAGE,
                10,
                30,
                lambda value, params: self._thresholds_write(start=params.get(_START_VOLTAGE_KEY), stop=value),
            ),
        ]

    def _thresholds_write(self, start: float | None, stop: float | None) -> AlternatorCommandMessage:
        # The app always sends both thresholds in one write, so send the one the
        # user did not change as the device last reported it.
        payload = alternator_pb2.AlternatorSet()
        if start is not None:
            payload.car_batt_start_voltage = float(start)
        if stop is not None:
            payload.car_batt_stop_voltage = float(stop)
        return self._config_write(payload)
