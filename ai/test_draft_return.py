"""Checks for the inactive entry point; no synthetic inquiries or policies."""
import unittest
from unittest.mock import Mock

from draft_return import generate_return_draft


class PendingDraftTests(unittest.TestCase):
    def test_unconfigured_entry_point_is_explicitly_unavailable(self):
        with self.assertRaisesRegex(NotImplementedError, "GitHub"):
            generate_return_draft()

    def test_client_is_not_called(self):
        client = Mock()
        with self.assertRaises(NotImplementedError):
            generate_return_draft(client=client)
        self.assertEqual(client.mock_calls, [])


if __name__ == "__main__":
    unittest.main()
