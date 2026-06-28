import os
import tempfile
import unittest

from solomon_harness import bootstrap


class FakeDB:
    """In-memory stand-in for DatabaseClient that records its calls."""

    def __init__(self):
        self.store = {}
        self.saves = []
        self.deletes = []

    def get_memory(self, key):
        return self.store.get(key)

    def save_memory(self, key, value, category=None):
        self.store[key] = value
        self.saves.append(key)

    def delete_memory(self, key):
        self.store.pop(key, None)
        self.deletes.append(key)


class TestIncrementalIndex(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def _write(self, rel, content):
        path = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(path) or self.root, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return path

    def test_index_is_incremental(self):
        self._write("a.py", "print('a')")
        self._write(os.path.join("pkg", "b.py"), "print('b')")
        b_rel = os.path.join("pkg", "b.py")

        db = FakeDB()
        bootstrap.index_codebase(self.root, db)
        # First pass indexes both files and writes a manifest.
        self.assertIn("a.py", db.store)
        self.assertIn(b_rel, db.store)
        self.assertIn("__code_index_manifest__", db.store)

        # Re-index with nothing changed: no file is re-read/re-saved.
        db.saves.clear()
        bootstrap.index_codebase(self.root, db)
        self.assertNotIn("a.py", db.saves)
        self.assertNotIn(b_rel, db.saves)

        # Change one file (different size -> new signature): only it re-indexes.
        self._write("a.py", "print('a has changed now')")
        db.saves.clear()
        bootstrap.index_codebase(self.root, db)
        self.assertIn("a.py", db.saves)
        self.assertNotIn(b_rel, db.saves)
        self.assertEqual(db.store["a.py"], "print('a has changed now')")

        # Remove a file: it is deleted from the store on the next index.
        os.remove(os.path.join(self.root, b_rel))
        db.deletes.clear()
        bootstrap.index_codebase(self.root, db)
        self.assertIn(b_rel, db.deletes)
        self.assertNotIn(b_rel, db.store)

    def test_excludes_generated_dirs(self):
        self._write("keep.py", "x = 1")
        self._write(os.path.join(".git", "config"), "[core]")
        self._write(os.path.join("docs", "guide.md"), "# guide")
        self._write(os.path.join("node_modules", "dep.js"), "module.exports = {}")

        db = FakeDB()
        bootstrap.index_codebase(self.root, db)
        self.assertIn("keep.py", db.store)
        self.assertNotIn(os.path.join(".git", "config"), db.store)
        self.assertNotIn(os.path.join("docs", "guide.md"), db.store)
        self.assertNotIn(os.path.join("node_modules", "dep.js"), db.store)


class TestCodeOverview(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def _write(self, rel, content):
        path = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(path) or self.root, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

    def test_overview_reflects_indexed_files(self):
        self._write("a.py", "print('a')")
        self._write(os.path.join("src", "b.py"), "print('b')")
        db = FakeDB()
        bootstrap.index_codebase(self.root, db)

        overview = bootstrap.generate_code_overview(self.root, db)
        self.assertIn("Code Overview", overview)
        self.assertIn("Files indexed: 2", overview)
        self.assertIn("File types", overview)

    def test_write_code_overview_creates_wiki_file(self):
        self._write("a.py", "print('a')")
        db = FakeDB()
        bootstrap.index_codebase(self.root, db)

        path = bootstrap.write_code_overview(self.root, db)
        self.assertTrue(os.path.isfile(path))
        self.assertEqual(
            path, os.path.join(self.root, "docs", "wiki", "Code-Overview.md")
        )
        with open(path, "r", encoding="utf-8") as f:
            self.assertIn("Code Overview", f.read())


if __name__ == "__main__":
    unittest.main()
