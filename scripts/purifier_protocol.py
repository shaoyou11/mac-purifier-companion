"""Model-scoped miIO / MIoT adapter; never infer support from a name prefix."""

from enum import Enum
from miio import AirPurifier as LegacyPurifier, AirPurifierMiot
from miio.integrations.airpurifier.zhimi.airpurifier import (
    OperationMode as LegacyMode, SUPPORTED_MODELS as LEGACY_MODELS,
)
from miio.integrations.airpurifier.zhimi.airpurifier_miot import OperationMode as MiotMode


OperationMode = Enum("OperationMode", {
    **{mode.name: mode.value for mode in LegacyMode}, "Fan": "fan",
})
MIOT_MODELS = frozenset({"zhimi.airpurifier.ma4"})
SUPPORTED_MODELS = frozenset(LEGACY_MODELS) | MIOT_MODELS


def max_level(model: str) -> int:
    return 14 if model in MIOT_MODELS else 17


def validate_level(level: int, model: str) -> None:
    if isinstance(level, bool) or not isinstance(level, int) or not 0 <= level <= max_level(model):
        raise ValueError(f"最爱档位必须是 0–{max_level(model)} 的整数")


class NormalizedStatus:
    def __init__(self, status):
        self._status = status
        # MIoT uses numeric mode values; the worker and persisted snapshots use strings.
        self.mode = OperationMode[status.mode.name]

    def __getattr__(self, name):
        return getattr(self._status, name)


class AirPurifier:
    def __init__(self, ip, token, *, timeout=3, model):
        if model not in SUPPORTED_MODELS:
            raise ValueError("不支持此型号")
        self.model = model
        self._miot = model in MIOT_MODELS
        factory = AirPurifierMiot if self._miot else LegacyPurifier
        self._device = factory(ip, token, timeout=timeout, model=model)

    def info(self):
        return self._device.info()

    def status(self):
        return NormalizedStatus(self._device.status())

    def set_mode(self, mode):
        native_mode = MiotMode if self._miot else LegacyMode
        # Unknown modes fail closed instead of silently falling back to auto.
        return self._device.set_mode(native_mode[mode.name])

    def set_favorite_level(self, level):
        validate_level(level, self.model)
        return self._device.set_favorite_level(level)
