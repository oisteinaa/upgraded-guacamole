"""Queued notifications must not keep a live monitor behind acquisition."""
import unittest
from unittest.mock import MagicMock, patch
from src.Capture import capture_zmq


class NotificationTests(unittest.TestCase):
    def test_latest_mode_coalesces_but_default_preserves_notifications(self):
        for latest in (False, True):
            with self.subTest(latest=latest):
                queued = [{"dest_path": "old.hdf5"}, {"dest_path": "new.hdf5"}]
                socket = MagicMock()
                def receive():
                    if not queued:
                        raise KeyboardInterrupt
                    return queued.pop(0)
                socket.recv_json.side_effect = receive
                socket.poll.side_effect = lambda *_: bool(queued)
                context = MagicMock()
                context.__enter__.return_value.socket.return_value = socket
                argv = ["capture_zmq"] + (["--latest-only"] if latest else [])
                with patch("sys.argv", argv), patch("zmq.Context", return_value=context), patch.object(
                    capture_zmq, "register_recording", side_effect=lambda path, *_: path
                ) as register, patch.object(capture_zmq, "publish_recording", return_value={"channel_count": 2}):
                    with self.assertRaises(KeyboardInterrupt):
                        capture_zmq.main()
                self.assertEqual([c.args[0] for c in register.call_args_list],
                                 ["new.hdf5"] if latest else ["old.hdf5", "new.hdf5"])
