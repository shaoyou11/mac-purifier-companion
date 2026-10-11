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

    def test_disconnect_preserves_automatic_intent_before_takeover(self):
        subject = self.subject
        subject.mode = "enabled"
        subject.intent_enabled = True
        subject.device = test_worker.FakePurifier()
        with patch.object(subject.device, "status", side_effect=OSError()):
            self.assertFalse(subject.poll_device())
        self.assertEqual(subject.mode, "paused")
        self.assertFalse(subject.manual_paused)
        self.assertTrue(subject.reconnect_pending)
        self.assertFalse(subject.owner)

    def test_failed_startup_keeps_automatic_resume_pending(self):
        subject = self.subject
        subject.mode = "enabled"
        subject.intent_enabled = True
        with patch.object(worker, "read_token", return_value="a" * 32), \
             patch.object(worker, "AirPurifier", side_effect=OSError()):
            subject.connect_device()
        self.assertEqual(subject.mode, "paused")
        self.assertFalse(subject.manual_paused)
        self.assertTrue(subject.reconnect_pending)

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

    def ready_for_resume(self):
        from dataclasses import replace
        subject = self.subject
        subject.config = replace(subject.config, mediumLevel=6, highLevel=10)
        subject.verified = {6, 10}
        subject.device = test_worker.FakePurifier()
        subject.mode = "enabled"
        subject.intent_enabled = True
        subject.sensor_received_mono = worker.time.monotonic()
        subject.sensor_source_wall = worker.time.time()
        return subject

    def test_reconnect_resumes_auto_without_immediate_write(self):
        subject = self.ready_for_resume()
        with patch.object(subject.device, "status", side_effect=OSError()):
            subject.poll_device()
        subject.poll_device()
        self.assertEqual(subject.mode, "enabled")
        self.assertFalse(subject.reconnect_pending)
        self.assertFalse(subject.manual_paused)
        self.assertEqual(subject.device.writes, [])

    def test_resume_waits_for_temperature_then_sensor_resumes(self):
        subject = self.ready_for_resume()
        subject._pause_disconnected_control()
        subject.sensor_received_mono = None
        subject.poll_device()
        self.assertEqual(subject.mode, "paused")
        self.assertTrue(subject.reconnect_pending)
        subject.handle_sensor({"timestamp": worker.time.time(), "temp": {"cpu_temp_avg": 56}})
        self.assertEqual(subject.mode, "enabled")
        self.assertEqual(subject.device.writes, [])

    def test_manual_pause_during_outage_is_persisted_and_never_resumes(self):
        subject = self.ready_for_resume()
        subject._pause_disconnected_control()
        subject.handle_command({"op": "pause"})
        subject.poll_device()
        self.assertEqual(subject.mode, "paused")
        restored = worker.Worker()
        self.assertTrue(restored.manual_paused)
        self.assertFalse(restored.reconnect_pending)

    def test_restart_during_outage_retains_pending_intent(self):
        subject = self.ready_for_resume()
        subject._pause_disconnected_control()
        restored = worker.Worker()
        self.assertTrue(restored.reconnect_pending)
        self.assertFalse(restored.manual_paused)
        self.assertTrue(restored.intent_enabled)

    def test_owned_state_rechecked_and_restored_without_replaying_commands(self):
        subject = self.ready_for_resume()
        subject.snapshot = {"power": True, "mode": "favorite", "level": 6}
        subject.expected = {"power": True, "mode": "favorite", "level": 9}
        subject.owner = True
        subject._pause_disconnected_control()
        subject.poll_device()
        self.assertTrue(subject.owner)
        self.assertEqual(subject.mode, "enabled")
        self.assertEqual(subject.device.writes, [])

    def test_external_change_during_outage_is_not_overwritten(self):
        subject = self.ready_for_resume()
        subject.snapshot = {"power": True, "mode": "favorite", "level": 6}
        subject.expected = {"power": True, "mode": "favorite", "level": 10}
        subject.owner = True
        subject._pause_disconnected_control()
        subject.poll_device()
        self.assertEqual(subject.mode, "paused")
        self.assertTrue(subject.manual_paused)
        self.assertFalse(subject.reconnect_pending)
        self.assertEqual(subject.device.writes, [])

    def test_uncertain_write_and_unverified_levels_do_not_resume(self):
        subject = self.ready_for_resume()
        subject._pause_disconnected_control()
        subject.command_state = "unknown"
        subject.poll_device()
        self.assertEqual(subject.mode, "paused")
        subject.command_state = "none"
        subject.verified = set()
        subject.poll_device()
        self.assertEqual(subject.mode, "paused")
        self.assertEqual(subject.device.writes, [])

    def test_startup_reconnect_resumes_after_fresh_sensor_sample(self):
        subject = self.ready_for_resume()
        subject.persist()
        restored = worker.Worker()
        device = test_worker.FakePurifier()
        with patch.object(worker, "read_token", return_value="a" * 32), \
             patch.object(worker, "AirPurifier", side_effect=[OSError(), device]):
            restored.connect_device()
            restored.maintain_device_connection()
        self.assertEqual(restored.mode, "paused")
        restored.handle_sensor({"timestamp": worker.time.time(), "temp": {"cpu_temp_avg": 80}})
        self.assertEqual(restored.mode, "enabled")
        self.assertEqual(device.writes, [])
        self.assertTrue(all(row["elapsed"] == 0 for row in restored.rule.dwell()))

    def test_powered_off_device_waits_without_turning_it_on(self):
        subject = self.ready_for_resume()
        subject._pause_disconnected_control()
        subject.device.power = False
        subject.poll_device()
        self.assertEqual(subject.mode, "paused")
        self.assertTrue(subject.reconnect_pending)
        self.assertEqual(subject.device.writes, [])
        subject.device.power = True
        subject.poll_device()
        self.assertEqual(subject.mode, "enabled")

    def test_stop_during_outage_cancels_automatic_resume(self):
        subject = self.ready_for_resume()
        subject._pause_disconnected_control()
        subject.handle_command({"op": "stop"})
        subject.poll_device()
        self.assertEqual(subject.mode, "stopped")
        self.assertFalse(subject.intent_enabled)
        self.assertFalse(worker.Worker().reconnect_pending)

    def test_shutdown_while_owned_device_offline_keeps_resume_intent(self):
        subject = self.ready_for_resume()
        subject.snapshot = {"power": True, "mode": "favorite", "level": 6}
        subject.expected = {"power": True, "mode": "favorite", "level": 9}
        subject.owner = True
        with patch.object(subject.device, "status", side_effect=OSError()):
            subject.poll_device()
            subject.shutdown(preserve_intent=True)
        restored = worker.Worker()
        self.assertTrue(restored.reconnect_pending)
        self.assertFalse(restored.manual_paused)
        self.assertEqual(restored.snapshot["level"], 6)
        self.assertEqual(subject.device.writes, [])
