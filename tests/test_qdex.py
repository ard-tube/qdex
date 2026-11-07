import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import qdex


class FuzzySearchTests(unittest.TestCase):
    def test_is_case_insensitive_and_matches_subsequences(self):
        self.assertIsNotNone(qdex.fuzzy_score("FBr", "Firefox Browser"))
        self.assertIsNone(qdex.fuzzy_score("xyz", "Firefox"))

    def test_contiguous_and_early_matches_rank_higher(self):
        self.assertGreater(qdex.fuzzy_score("fire", "Firefox"), qdex.fuzzy_score("fire", "File Explorer"))

    def test_empty_query_matches_everything(self):
        self.assertEqual(qdex.fuzzy_score("", "Anything"), 0)


class SettingsTests(unittest.TestCase):
    def test_setup_preferences_round_trip(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = root / ".config" / "qdex" / "config.json"
            settings = qdex.Settings("Arda", root.resolve())

            qdex.save_settings(settings, config)

            self.assertEqual(qdex.load_settings(config), settings)
            self.assertEqual(config.stat().st_mode & 0o777, 0o600)

    def test_rejects_missing_start_folder(self):
        with tempfile.TemporaryDirectory() as temporary:
            config = Path(temporary) / "config.json"
            config.write_text(
                '{"name":"Arda","start_directory":"/not/a/real/folder"}',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "unavailable"):
                qdex.load_settings(config)


class DirectoryTests(unittest.TestCase):
    def test_hides_dotfiles_and_puts_folders_first(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "z-file.txt").touch()
            (root / "a-folder").mkdir()
            (root / ".hidden").touch()
            entries = qdex.list_directory(root)
            self.assertEqual([entry.name for entry in entries], ["a-folder", "z-file.txt"])

    def test_dotfile_can_be_searched_explicitly(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / ".config").touch()
            self.assertEqual([entry.name for entry in qdex.list_directory(root, ".c")], [".config"])


class TransferTests(unittest.TestCase):
    def test_copies_a_directory_without_overwriting(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            source.mkdir()
            (source / "note.txt").write_text("hello", encoding="utf-8")
            destination = root / "destination"
            destination.mkdir()

            target = qdex.transfer_item(source, destination)
            self.assertEqual((target / "note.txt").read_text(encoding="utf-8"), "hello")
            with self.assertRaises(FileExistsError):
                qdex.transfer_item(source, destination)

    def test_moves_a_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "note.txt"
            source.write_text("hello", encoding="utf-8")
            destination = root / "destination"
            destination.mkdir()

            target = qdex.transfer_item(source, destination, move=True)
            self.assertFalse(source.exists())
            self.assertEqual(target.read_text(encoding="utf-8"), "hello")

    def test_rejects_copying_a_folder_into_itself(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "folder"
            source.mkdir()
            nested = source / "nested"
            nested.mkdir()
            with self.assertRaisesRegex(ValueError, "inside itself"):
                qdex.transfer_item(source, nested)


if __name__ == "__main__":
    unittest.main()
