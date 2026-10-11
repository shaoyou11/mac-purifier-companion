import json
import unittest
from unittest.mock import patch

import test_worker
import worker


class ReconnectionTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_worker.WorkerSafetyTests()
        self.fixture.setUp()
        self.subject = self.fixture.instance
        worker.DEVICE_PATH.write_text(json.dumps({
            "model": "zhimi.airpurifier.m1", "ip": "192.0.2.1",
            "credentialId": "test-device",
        }))

    def tearDown(self):
        self.fixture.tearDown()

    def test_startup_failure_reconnects_without_manual_refresh(self):
        device = test_worker.FakePurifier()
        with patch.object(worker, "read_token", return_value="a" * 32), \
             patch.object(worker, "AirPurifier", side_effect=[OSError(), device]):
            self.subject.connect_device()
            self.assertIsNone(self.subject.device)
            self.subject.maintain_device_connection()
        self.assertTrue(self.subject.device_view["reachable"])
        self.assertEqual(device.writes, [])

    def test_repeated_read_failures_rebuild_session_without_restoring_or_resuming(self):
        subject = self.subject
        old = test_worker.FakePurifier()
        subject.device = old
        subject.device_view.update(reachable=True, power=True, mode="favorite", level=9)
        subject.mode = "manual"
        subject.owner = True
        subject.snapshot = {"power": True, "mode": "favorite", "level": 6}
        subject.expected = {"power": True, "mode": "favorite", "level": 9}
        with patch.object(old, "status", side_effect=OSError()):
            for _ in range(3):
                subject.poll_device()
        fresh = test_worker.FakePurifier()
        with patch.object(worker, "read_token", return_value="a" * 32), \
             patch.object(worker, "AirPurifier", return_value=fresh):
            subject.maintain_device_connection()
        self.assertIs(subject.device, fresh)
        self.assertTrue(subject.device_view["reachable"])
        self.assertFalse(subject.owner)
        self.assertEqual(subject.mode, "paused")
        self.assertEqual(subject.snapshot["level"], 6)
        self.assertEqual(fresh.writes, [])
        self.assertEqual(subject.device_failures, 0)

    def test_failed_reconnect_backs_off_and_caps_delay(self):
        subject = self.subject
        with patch.object(subject, "connect_device") as connect, \
             patch.object(worker.time, "monotonic", return_value=100) as clock:
            subject.maintain_device_connection()
            connect.assert_called_once_with(reconcile_snapshot=False)
            self.assertEqual(subject.next_device_reconnect, 105)
            clock.return_value = 101
            subject.maintain_device_connection()
            self.assertEqual(connect.call_count, 1)
            clock.return_value = 105
            subject.maintain_device_connection()
            self.assertEqual(subject.next_device_reconnect, 115)
            for _ in range(8):
                clock.return_value = subject.next_device_reconnect
                subject.maintain_device_connection()
            self.assertEqual(subject.device_reconnect_delay, 60)

    def test_unpaired_or_pairing_does_not_reconnect(self):
        with patch.object(self.subject, "connect_device") as connect:
            with patch.object(worker, "DEVICE_PATH", worker.LOCAL / "absent.json"):
                self.subject.maintain_device_connection()
            self.subject.pairing = object()
            self.subject.maintain_device_connection()
            connect.assert_not_called()

    def test_successful_read_resets_backoff_and_uses_completion_time(self):
        subject = self.subject
        subject.device = test_worker.FakePurifier()
        subject.device_failures = 4
        subject.device_reconnect_delay = 60
        subject.next_device_reconnect = 200
        with patch.object(worker.time, "monotonic", side_effect=[100, 150]):
            self.assertTrue(subject.poll_device())
        self.assertEqual(subject.device_failures, 0)
        self.assertEqual(subject.device_reconnect_delay, 5)
        self.assertEqual(subject.next_device_reconnect, 0)
        self.assertEqual(subject.device_observed_mono, 150)
