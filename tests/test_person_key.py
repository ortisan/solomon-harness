"""Unit tests for the canonical person key (ADR-0012, issue #118).

``normalize_person_key`` maps an email and a login (two scalars, the ADR's
normative seam) to the cross-tenant person key; ``person_key_or_unassigned`` maps
a stored null key to the reserved query token. Both are pure, total, and
deterministic, so these tests need no backend.
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
            normalize_person_key("  Alice@Example.com  ", None),
            "alice@example.com",
        )

    def test_two_email_spellings_normalize_to_one_key(self):
        """One human's two spellings of the same email collapse to one key."""
        self.assertEqual(
            normalize_person_key("Alice@Example.com", None),
            normalize_person_key("alice@example.com", None),
        )

    def test_distinct_emails_never_collapse(self):
        """Two distinct emails stay two distinct keys (no false merge)."""
        self.assertNotEqual(
            normalize_person_key("alice@example.com", None),
            normalize_person_key("alice@contoso.com", None),
        )

    def test_handle_only_yields_namespaced_key(self):
        """A handle-only assignee yields gh:<lowercased-login>."""
        self.assertEqual(normalize_person_key(None, "Bob"), "gh:bob")

    def test_handle_key_never_collides_with_email(self):
        """The gh: namespace is disjoint from every email-form key, so a handle
        can never collide with an email even if the login looked email-like."""
        email_key = normalize_person_key("alice@example.com", None)
        for login in ("bob", "alice", "alice@example.com"):
            handle_key = normalize_person_key(None, login)
            self.assertIsNotNone(handle_key)
            assert handle_key is not None  # narrow for the type checker
            self.assertTrue(handle_key.startswith("gh:"))
            self.assertNotEqual(handle_key, email_key)

    def test_email_wins_when_both_known(self):
        """When both an email and a login are present, the email wins."""
        self.assertEqual(
            normalize_person_key("Alice@Example.com", "bob"),
            "alice@example.com",
        )

    def test_empty_email_falls_through_to_the_login(self):
        """An empty or whitespace-only email is not a usable key, so a present
        login still yields the namespaced handle key (the email seam is scalar)."""
        self.assertEqual(normalize_person_key("  ", "Bob"), "gh:bob")

    def test_email_without_at_is_not_a_key(self):
        """A non-empty email lacking '@' is not a usable email; with no login it
        yields None rather than a bogus email key."""
        self.assertIsNone(normalize_person_key("not-an-email", None))

    def test_empty_inputs_return_none(self):
        """Null, empty, or whitespace-only scalar inputs return None and never
        raise (total)."""
        for email, login in (
            (None, None),
            ("", ""),
            ("  ", "  "),
            (None, ""),
            ("", None),
        ):
            with self.subTest(email=email, login=login):
                self.assertIsNone(normalize_person_key(email, login))


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
