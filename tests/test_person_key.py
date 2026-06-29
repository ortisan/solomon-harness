"""Unit tests for the canonical person key (ADR-0012, issue #118).

``normalize_person_key`` maps a GitHub assignee object to the cross-tenant person
key; ``person_key_or_unassigned`` maps a stored null key to the reserved query
token. Both are pure, total, and deterministic, so these tests need no backend.
"""

import os
import sys
import unittest

repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from solomon_harness.tools.database_client import (  # noqa: E402
    UNASSIGNED_PERSON_KEY,
    normalize_person_key,
    person_key_or_unassigned,
)


class TestNormalizePersonKey(unittest.TestCase):
    def test_email_is_lowercased_and_trimmed(self):
        """A known email becomes lowercase(trim(email))."""
        self.assertEqual(
            normalize_person_key({"email": "  Alice@Example.com  "}),
            "alice@example.com",
        )

    def test_two_email_spellings_normalize_to_one_key(self):
        """One human's two spellings of the same email collapse to one key."""
        self.assertEqual(
            normalize_person_key({"email": "Alice@Example.com"}),
            normalize_person_key({"email": "alice@example.com"}),
        )

    def test_distinct_emails_never_collapse(self):
        """Two distinct emails stay two distinct keys (no false merge)."""
        self.assertNotEqual(
            normalize_person_key({"email": "alice@example.com"}),
            normalize_person_key({"email": "alice@contoso.com"}),
        )

    def test_handle_only_yields_namespaced_key(self):
        """A handle-only assignee yields gh:<lowercased-login>."""
        self.assertEqual(normalize_person_key({"login": "Bob"}), "gh:bob")

    def test_handle_key_never_collides_with_email(self):
        """The gh: namespace is disjoint from every email-form key, so a handle
        can never collide with an email even if the login looked email-like."""
        email_key = normalize_person_key({"email": "alice@example.com"})
        for login in ("bob", "alice", "alice@example.com"):
            handle_key = normalize_person_key({"login": login})
            self.assertIsNotNone(handle_key)
            assert handle_key is not None  # narrow for the type checker
            self.assertTrue(handle_key.startswith("gh:"))
            self.assertNotEqual(handle_key, email_key)

    def test_email_wins_when_both_known(self):
        """When both an email and a login are present, the email wins."""
        self.assertEqual(
            normalize_person_key({"email": "Alice@Example.com", "login": "bob"}),
            "alice@example.com",
        )

    def test_none_and_empty_assignee_return_none(self):
        """Null, non-mapping, empty, or whitespace-only assignees return None and
        never raise (total)."""
        for assignee in (
            None,
            {},
            {"email": "", "login": ""},
            {"email": "  ", "login": "  "},
            "not-a-mapping",
        ):
            self.assertIsNone(normalize_person_key(assignee))


class TestPersonKeyOrUnassigned(unittest.TestCase):
    def test_person_key_or_unassigned_maps_none(self):
        """A stored null key reads back as the reserved unassigned pseudo-key."""
        self.assertEqual(person_key_or_unassigned(None), UNASSIGNED_PERSON_KEY)
        self.assertEqual(person_key_or_unassigned(None), "unassigned")

    def test_person_key_or_unassigned_passes_through_a_real_key(self):
        """A concrete key is returned unchanged; unassigned is reserved, so no real
        key can equal it (every concrete key is an email or a gh: handle)."""
        self.assertEqual(person_key_or_unassigned("alice@example.com"), "alice@example.com")
        self.assertEqual(person_key_or_unassigned("gh:bob"), "gh:bob")
        self.assertNotEqual(UNASSIGNED_PERSON_KEY, "gh:bob")


if __name__ == "__main__":
    unittest.main()
