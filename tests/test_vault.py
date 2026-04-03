"""Unit tests for the Vault class."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from obsidian_workspace_mcp.models import (
    EditFileRequest,
    SearchRequest,
    SortBy,
    SortOrder,
)
from obsidian_workspace_mcp.vault import Vault, VaultFileError, VaultSecurityError


@pytest.fixture
def vault(tmp_path: Path) -> Vault:
    """Create a vault with some test content."""
    # Pre-populate
    (tmp_path / "notes").mkdir()
    (tmp_path / "notes" / "daily.md").write_text("# Daily\n\nHello world.\n")
    (tmp_path / "notes" / "project.md").write_text("# Project\n\nStatus: active\n")
    (tmp_path / "attach").mkdir()
    (tmp_path / "attach" / "image.png").write_bytes(b"\x89PNG\r\n" + b"\x00" * 20)
    return Vault(tmp_path)


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


class TestVaultInit:
    def test_valid_directory(self, tmp_path: Path):
        v = Vault(tmp_path)
        assert v._root == tmp_path.resolve()

    def test_nonexistent_directory_raises(self, tmp_path: Path):
        with pytest.raises(ValueError, match="not a directory"):
            Vault(tmp_path / "nope")


# ---------------------------------------------------------------------------
# Security — path traversal
# ---------------------------------------------------------------------------


class TestPathTraversal:
    def test_read_traversal_blocked(self, vault: Vault):
        with pytest.raises(VaultSecurityError, match=r"(?i)path traversal"):
            vault.read_file("../../etc/passwd")

    def test_create_traversal_blocked(self, vault: Vault):
        with pytest.raises(VaultSecurityError, match=r"(?i)path traversal"):
            vault.create_file("../../tmp/evil.md", "pwned")

    def test_edit_traversal_blocked(self, vault: Vault):
        with pytest.raises(VaultSecurityError, match=r"(?i)path traversal"):
            vault.edit_file(EditFileRequest(path="../../tmp/evil.md", old_text="x", new_text="y"))

    def test_delete_traversal_blocked(self, vault: Vault):
        with pytest.raises(VaultSecurityError, match=r"(?i)path traversal"):
            vault.delete_file("../../etc/passwd")

    def test_list_traversal_blocked(self, vault: Vault):
        with pytest.raises(VaultSecurityError, match=r"(?i)path traversal"):
            vault.list_directory("../../etc")


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


class TestStats:
    def test_counts_files(self, vault: Vault):
        s = vault.stats()
        # 3 files: daily.md, project.md, image.png
        assert s.total_files == 3
        assert s.total_size_bytes > 0
        assert s.last_modified is not None


# ---------------------------------------------------------------------------
# List directory
# ---------------------------------------------------------------------------


class TestListDirectory:
    def test_root_listing(self, vault: Vault):
        r = vault.list_directory("")
        names = [e.name for e in r.entries]
        assert "notes" in names
        assert "attach" in names

    def test_subdirectory_listing(self, vault: Vault):
        r = vault.list_directory("notes")
        names = [e.name for e in r.entries]
        assert "daily.md" in names
        assert "project.md" in names

    def test_nonexistent_directory_raises(self, vault: Vault):
        with pytest.raises(VaultFileError, match="Not a directory"):
            vault.list_directory("nope")

    def test_sort_by_name_descending(self, vault: Vault):
        r = vault.list_directory("notes", sort_by=SortBy.NAME, sort_order=SortOrder.DESCENDING)
        names = [e.name for e in r.entries]
        assert names == sorted(names, reverse=True)

    def test_directories_first_when_sorted_by_name(self, vault: Vault):
        r = vault.list_directory("")
        # Dirs come before files because key is (not is_dir, name)
        seen_file = False
        for e in r.entries:
            if not e.is_dir:
                seen_file = True
            if seen_file and e.is_dir:
                pytest.fail("Directory found after a file in name-sorted listing")


# ---------------------------------------------------------------------------
# Read file
# ---------------------------------------------------------------------------


class TestReadFile:
    def test_read_markdown(self, vault: Vault):
        r = vault.read_file("notes/daily.md")
        assert r.content.startswith("# Daily")
        assert r.size_bytes > 0

    def test_read_nonexistent_raises(self, vault: Vault):
        with pytest.raises(VaultFileError, match="File not found"):
            vault.read_file("nope.md")

    def test_read_binary_file_raises(self, vault: Vault):
        with pytest.raises(VaultFileError, match="not valid UTF-8"):
            vault.read_file("attach/image.png")


# ---------------------------------------------------------------------------
# Create file
# ---------------------------------------------------------------------------


class TestCreateFile:
    def test_create_new_file(self, vault: Vault):
        r = vault.create_file("new/test.md", "# New\n")
        assert r.change_type.value == "created"
        assert r.size_bytes > 0
        # Verify it exists
        content = vault.read_file("new/test.md").content
        assert content == "# New\n"

    def test_overwrite_existing(self, vault: Vault):
        vault.create_file("notes/daily.md", "# Overwritten\n")
        assert vault.read_file("notes/daily.md").content == "# Overwritten\n"

    def test_empty_content(self, vault: Vault):
        r = vault.create_file("empty.md", "")
        assert r.size_bytes == 0


# ---------------------------------------------------------------------------
# Edit file
# ---------------------------------------------------------------------------


class TestEditFile:
    def test_single_replacement(self, vault: Vault):
        r = vault.edit_file(EditFileRequest(
            path="notes/project.md",
            old_text="active",
            new_text="completed",
        ))
        assert r.replacements_made == 1
        assert "completed" in vault.read_file("notes/project.md").content

    def test_replace_all_occurrences(self, vault: Vault):
        vault.create_file("multi.md", "aaa bbb aaa bbb aaa")
        r = vault.edit_file(EditFileRequest(
            path="multi.md",
            old_text="aaa",
            new_text="XXX",
            count=0,
        ))
        assert r.replacements_made == 3
        assert vault.read_file("multi.md").content == "XXX bbb XXX bbb XXX"

    def test_old_text_not_found_raises(self, vault: Vault):
        with pytest.raises(VaultFileError, match="Text to replace not found"):
            vault.edit_file(EditFileRequest(
                path="notes/daily.md",
                old_text="nonexistent",
                new_text="whatever",
            ))

    def test_edit_nonexistent_file_raises(self, vault: Vault):
        with pytest.raises(VaultFileError, match="File not found"):
            vault.edit_file(EditFileRequest(
                path="nope.md",
                old_text="x",
                new_text="y",
            ))

    def test_multiline_replacement(self, vault: Vault):
        vault.create_file("block.md", textwrap.dedent("""\
            # Title
            old block
            more old
            # End
        """))
        vault.edit_file(EditFileRequest(
            path="block.md",
            old_text="old block\nmore old",
            new_text="new content",
        ))
        content = vault.read_file("block.md").content
        assert "new content" in content
        assert "old block" not in content


# ---------------------------------------------------------------------------
# Delete file
# ---------------------------------------------------------------------------


class TestDeleteFile:
    def test_delete_existing(self, vault: Vault):
        vault.delete_file("notes/daily.md")
        with pytest.raises(VaultFileError):
            vault.read_file("notes/daily.md")

    def test_delete_nonexistent_raises(self, vault: Vault):
        with pytest.raises(VaultFileError, match="File not found"):
            vault.delete_file("nope.md")

    def test_delete_directory_raises(self, vault: Vault):
        with pytest.raises(VaultFileError, match="Not a regular file"):
            vault.delete_file("notes")


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


class TestSearch:
    def test_simple_search(self, vault: Vault):
        r = vault.search(SearchRequest(query="Status"))
        assert r.total_matches == 1
        assert r.files_searched >= 2  # at least the 2 .md files
        assert r.matches[0].path == "notes/project.md"
        assert r.matches[0].line_number == 3

    def test_case_insensitive_by_default(self, vault: Vault):
        r = vault.search(SearchRequest(query="status"))
        assert r.total_matches == 1

    def test_case_sensitive(self, vault: Vault):
        r = vault.search(SearchRequest(query="status", case_sensitive=True))
        assert r.total_matches == 0

    def test_extension_filter(self, vault: Vault):
        r = vault.search(SearchRequest(query="Status", file_extension=".md"))
        assert r.total_matches == 1

    def test_search_in_subdirectory(self, vault: Vault):
        r = vault.search(SearchRequest(query="Status", path="notes"))
        assert r.total_matches == 1

    def test_search_no_results(self, vault: Vault):
        r = vault.search(SearchRequest(query="ZZZZZZZ"))
        assert r.total_matches == 0

    def test_multiple_matches_across_files(self, vault: Vault):
        vault.create_file("notes/other.md", "Status: pending\n")
        r = vault.search(SearchRequest(query="Status"))
        assert r.total_matches == 2
