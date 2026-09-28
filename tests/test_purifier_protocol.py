from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import purifier_protocol as protocol
import pair_device
import test_worker

MODEL = "zhimi.airpurifier.ma4"


class MiotDevice:
    def __init__(self, *args, **kwargs):
        self.mode = protocol.MiotMode.Fan
        self.level = 4
        self.writes = []

    def info(self):
        return SimpleNamespace(model=MODEL, firmware_version="test")

    def status(self):
        return SimpleNamespace(is_on=True, mode=self.mode, favorite_level=self.level, motor_speed=900)

    def set_mode(self, mode):
        if not isinstance(mode, protocol.MiotMode):
            raise TypeError("MIoT requires its own mode enum")
        self.writes.append(("mode", mode.value))
        self.mode = mode

    def set_favorite_level(self, level):
        self.writes.append(("level", level))
        self.level = level


class ProtocolTests(unittest.TestCase):
    def test_ma4_discovery_and_read_only_verification(self):
        record = pair_device._device_record({"model": MODEL})
        self.assertTrue(record["supported"])
        with patch.object(protocol, "AirPurifierMiot", MiotDevice):
            result = pair_device.verify_candidate({"model": MODEL, "ip": "192.0.2.1"}, "a" * 32)
        self.assertEqual(result["status"].mode.value, "fan")
        self.assertEqual(result["purifier"]._device.writes, [])

    def test_mode_roundtrip_and_level_boundaries(self):
        with patch.object(protocol, "AirPurifierMiot", MiotDevice):
            device = protocol.AirPurifier("192.0.2.1", "a" * 32, model=MODEL)
        for mode in ("auto", "silent", "favorite", "fan"):
            device.set_mode(protocol.OperationMode(mode))
            self.assertEqual(device.status().mode.value, mode)
        for level in (0, 14):
            device.set_favorite_level(level)
            self.assertEqual(device.status().favorite_level, level)
        count = len(device._device.writes)
        for level in (-1, 15, 17, True, 3.5):
            with self.assertRaises(ValueError):
                device.set_favorite_level(level)
        self.assertEqual(len(device._device.writes), count)

    def test_legacy_selection_and_full_range_preserved(self):
        with patch.object(protocol, "LegacyPurifier") as legacy, patch.object(protocol, "AirPurifierMiot") as miot:
            device = protocol.AirPurifier("192.0.2.1", "a" * 32, model="zhimi.airpurifier.m1")
            device.set_favorite_level(17)
            device.set_mode(protocol.OperationMode.Favorite)
            legacy.return_value.set_favorite_level.assert_called_once_with(17)
            legacy.return_value.set_mode.assert_called_once_with(protocol.LegacyMode.Favorite)
            miot.assert_not_called()

    def test_unknown_model_rejected(self):
        with self.assertRaises(ValueError):
            protocol.AirPurifier("192.0.2.1", "a" * 32, model="zhimi.airpurifier.unknown")


class MiotWorkerTests(unittest.TestCase):
    def setUp(self):
        # Reuse the existing isolated worker fixture, without inheriting its tests.
        self.fixture = test_worker.WorkerSafetyTests()
        self.fixture.setUp()
        self.worker = self.fixture.instance
        with patch.object(protocol, "AirPurifierMiot", MiotDevice):
            self.worker.device = protocol.AirPurifier("192.0.2.1", "a" * 32, model=MODEL)
        self.worker.device_view["model"] = MODEL
        self.worker.account["paired"] = True
        self.worker.poll_device()

    def tearDown(self):
        self.fixture.tearDown()

    def test_takeover_and_restore_manual_fan_mode(self):
        self.worker.set_manual_purifier(7)
        self.assertEqual(self.worker.device_view["mode"], "favorite")
        self.assertEqual(self.worker.device_view["level"], 7)
        self.worker.release_manual_purifier()
        self.assertEqual(self.worker.device_view["mode"], "fan")
        self.assertEqual(self.worker.device_view["level"], 4)

    def test_external_ha_change_relinquishes_control(self):
        self.worker.set_manual_purifier(7)
        self.worker.device._device.mode = protocol.MiotMode.Auto
        self.worker.poll_device()
        self.assertFalse(self.worker.owner)
        self.assertEqual(self.worker.mode, "paused")
        self.assertIsNone(self.worker.snapshot)

    def test_out_of_range_rejected_before_mode_change(self):
        for action in (lambda: self.worker.set_manual_purifier(15),
                       lambda: self.worker.start_test_strategy([3, 17]),
                       lambda: self.worker.configure({"mediumLevel": 3, "highLevel": 15}),
                       lambda: self.worker._write_level(17)):
            with self.assertRaises(ValueError):
                action()
        self.assertEqual(self.worker.device._device.writes, [])
