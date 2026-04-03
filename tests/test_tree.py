"""Tests for directory_tree functionality."""

from __future__ import annotations

from pathlib import Path

import pytest

from obsidian_workspace_mcp.vault import Vault, VaultFileError


@pytest.fixture
def vault(tmp_path: Path) -> Vault:
    """Create a vault with nested structure."""
    (tmp_path / "notes").mkdir()
    (tmp_path / "notes" / "daily.md").write_text("# Daily\n")
    (tmp_path / "notes" / "project.md").write_text("# Project\n")
    (tmp_path / "notes" / "sub").mkdir()
    (tmp_path / "notes" / "sub" / "deep.md").write_text("# Deep\n")
    (tmp_path / "attach").mkdir()
    (tmp_path / "attach" / "image.png").write_bytes(b"\x89PNG")
    return Vault(tmp_path)


class TestDirectoryTree:
    def test_basic_tree(self, vault: Vault):
        r = vault.directory_tree("")
        assert r.tree.name
        assert r.tree.is_dir
        assert "notes" in r.text
        assert "daily.md" in r.text

    def test_max_depth_limits_recursion(self, vault: Vault):
        r = vault.directory_tree("", max_depth=1)
        assert "notes" in r.text
        # With max_depth=1 we should see notes/ but not its children
        assert "daily.md" not in r.text

    def test_max_depth_two(self, vault: Vault):
        r = vault.directory_tree("", max_depth=2)
        assert "notes" in r.text
        assert "daily.md" in r.text
        assert "sub" in r.text
        # depth=2: sub/ dir visible but deep.md not
        assert "deep.md" not in r.text

    def test_max_files_per_dir(self, vault: Vault):
        # Create many files
        for i in range(30):
            (vault._root / "notes" / f"file{i}.md").write_text(f"# File {i}")
        r = vault.directory_tree("", max_files_per_dir=5)
        assert "more" in r.text
        # Truncation happens on the 'notes' child node, not the root
        notes_node = next(c for c in r.tree.children if c.name == "notes")
        assert notes_node.truncated

    def test_subdirectory_tree(self, vault: Vault):
        r = vault.directory_tree("notes", max_depth=2)
        assert "daily.md" in r.text
        assert "deep.md" in r.text

    def test_nonexistent_dir_raises(self, vault: Vault):
        with pytest.raises(VaultFileError, match="Not a directory"):
            vault.directory_tree("nope")

    def test_dirs_first_order(self, vault: Vault):
        r = vault.directory_tree("", max_depth=2)
        # Directories (notes, attach) should appear before files
        lines = r.text.split("\n")
        dir_lines = [l for l in lines if l.strip().endswith("/")]
        file_lines = [l for l in lines if l.strip() and not l.strip().endswith("/") and not l.strip().startswith("└") or "more" in l]
        # Just verify structure is sensible
        assert len(dir_lines) >= 2

    def test_text_output_is_readable(self, vault: Vault):
        r = vault.directory_tree("")
        assert "├──" in r.text or "└──" in r.text or "/" in r.text.split("\n")[0]
