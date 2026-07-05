"""Category-gated embeddings for the memory vector index (ADR-0016, F6).

The code index (categories codebase_index and index) and the board history
are operational blobs, not semantic notes: embedding them pollutes the HNSW
index and semantic_search returns file contents instead of meaning. The gate
is a DENYLIST of those known non-semantic categories, so every unknown
category keeps its embedding and stays searchable (behavior preserved), and
semantic_search excludes the denylist by default while still honoring an
explicit category argument.
"""

import os
import sys
import tempfile
import unittest

repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from solomon_harness.tools.database_client import (  # noqa: E402
    NON_SEMANTIC_MEMORY_CATEGORIES,
    DatabaseClient,
    is_semantic_category,
)

try:  # importable both as `tests.test_...` and bare under unittest discover
    from tests.test_database_client_resilience import FakeSurreal
except ImportError:  # pragma: no cover - depends on the discovery entry point
    from test_database_client_resilience import FakeSurreal  # type: ignore[no-redef]


class TestCategoryGate(unittest.TestCase):
    def test_denylist_names_the_known_non_semantic_categories(self):
        self.assertEqual(
            NON_SEMANTIC_MEMORY_CATEGORIES, ("codebase_index", "index", "board_history")
        )

    def test_is_semantic_category(self):
        for category in NON_SEMANTIC_MEMORY_CATEGORIES:
            self.assertFalse(is_semantic_category(category), category)
        self.assertFalse(is_semantic_category("Board_History"))
        self.assertTrue(is_semantic_category("insight"))
        self.assertTrue(is_semantic_category("decision_context"))
        # An unknown or absent category keeps its embedding (denylist semantics).
        self.assertTrue(is_semantic_category(None))
        self.assertTrue(is_semantic_category(""))


class SurrealFakeBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def _client(self, fake):
        client = DatabaseClient(db_path=os.path.join(self.tmp.name, "harness.db"))
        client.backend = "surrealdb"
        client.db = fake
        return client


class TestSaveMemoryEmbeddingGate(SurrealFakeBase):
    def _upsert_params(self, fake):
        upserts = [(q, p) for q, p in fake.calls if "UPSERT" in q]
        self.assertEqual(len(upserts), 1)
        return upserts[0]

    def test_non_semantic_category_is_not_embedded(self):
        fake = FakeSurreal(result=[])
        client = self._client(fake)

        client.save_memory("src/foo.py", "def foo(): ...", "codebase_index")

        query, params = self._upsert_params(fake)
        self.assertNotIn("embedding", query)
        self.assertNotIn("embedding", params)

    def test_semantic_category_keeps_its_embedding(self):
        fake = FakeSurreal(result=[])
        client = self._client(fake)

        client.save_memory("k", "the review found a race", "insight")

        query, params = self._upsert_params(fake)
        self.assertIn("embedding", query)
        self.assertTrue(any(v != 0.0 for v in params["embedding"]))


class TestSemanticSearchExclusion(SurrealFakeBase):
    def test_default_search_excludes_the_denylist(self):
        fake = FakeSurreal(result=[])
        client = self._client(fake)

        client.semantic_search("race condition")

        query, params = fake.calls[0]
        self.assertIn("category NOT IN $excluded", query)
        self.assertEqual(params["excluded"], list(NON_SEMANTIC_MEMORY_CATEGORIES))

    def test_explicit_category_is_honored_verbatim(self):
        fake = FakeSurreal(result=[])
        client = self._client(fake)

        client.semantic_search("race condition", category="board_history")

        query, params = fake.calls[0]
        self.assertIn("category = $category", query)
        self.assertNotIn("$excluded", query)
        self.assertEqual(params["category"], "board_history")


if __name__ == "__main__":
    unittest.main()
