"""Unit tests for property queries and tag index features."""

from __future__ import annotations

from pathlib import Path

import pytest

from obsidian_workspace_mcp.models import (
    PropertyFilter,
    PropertySort,
    QueryPropertiesRequest,
    SortOrder,
    TagIndexRequest,
)
from obsidian_workspace_mcp.vault import Vault, VaultFileError


@pytest.fixture
def vault(tmp_path: Path) -> Vault:
    """Create a vault with frontmatter-rich test content."""
    (tmp_path / "notes").mkdir()

    (tmp_path / "notes" / "project.md").write_text(
        "---\ntitle: Project Alpha\nstatus: active\npriority: 3\ntags: [work, urgent]\n---\n# Project Alpha\n"
    )
    (tmp_path / "notes" / "idea.md").write_text(
        "---\ntitle: Random Idea\nstatus: idea\npriority: 1\ntags: [personal, creative]\n---\n# Idea\n"
    )
    (tmp_path / "notes" / "done.md").write_text(
        "---\ntitle: Old Project\nstatus: done\npriority: 5\ntags: [work, archive]\n---\n# Done\n"
    )
    (tmp_path / "notes" / "notags.md").write_text(
        "---\ntitle: No Tags Note\nstatus: draft\n---\n# No tags\n"
    )
    (tmp_path / "notes" / "nofrontmatter.md").write_text("# Just content\n")
    (tmp_path / "notes" / "sub").mkdir()
    (tmp_path / "notes" / "sub" / "nested.md").write_text(
        "---\ntitle: Nested Note\nstatus: active\npriority: 2\ntags: [work]\n---\n# Nested\n"
    )
    return Vault(tmp_path)


# ---------------------------------------------------------------------------
# Property Query — filtering
# ---------------------------------------------------------------------------


class TestPropertyFiltering:
    def test_eq_filter(self, vault: Vault):
        r = vault.query_properties(QueryPropertiesRequest(
            filters=[PropertyFilter(field="status", op="eq", value="active")],
        ))
        titles = [m.properties["title"] for m in r.matches]
        assert "Project Alpha" in titles
        assert "Nested Note" in titles
        assert "Old Project" not in titles

    def test_neq_filter(self, vault: Vault):
        r = vault.query_properties(QueryPropertiesRequest(
            filters=[PropertyFilter(field="status", op="neq", value="active")],
        ))
        statuses = [m.properties["status"] for m in r.matches]
        assert "active" not in statuses

    def test_contains_filter_on_list(self, vault: Vault):
        r = vault.query_properties(QueryPropertiesRequest(
            filters=[PropertyFilter(field="tags", op="contains", value="work")],
        ))
        assert r.total_matches == 3  # project, done, nested

    def test_contains_filter_on_string(self, vault: Vault):
        r = vault.query_properties(QueryPropertiesRequest(
            filters=[PropertyFilter(field="title", op="contains", value="Project")],
        ))
        titles = [m.properties["title"] for m in r.matches]
        assert "Project Alpha" in titles
        assert "Old Project" in titles

    def test_gt_filter(self, vault: Vault):
        r = vault.query_properties(QueryPropertiesRequest(
            filters=[PropertyFilter(field="priority", op="gt", value=2)],
        ))
        priorities = [m.properties["priority"] for m in r.matches]
        assert all(p > 2 for p in priorities)

    def test_gte_filter(self, vault: Vault):
        r = vault.query_properties(QueryPropertiesRequest(
            filters=[PropertyFilter(field="priority", op="gte", value=3)],
        ))
        priorities = [m.properties["priority"] for m in r.matches]
        assert all(p >= 3 for p in priorities)

    def test_lt_filter(self, vault: Vault):
        r = vault.query_properties(QueryPropertiesRequest(
            filters=[PropertyFilter(field="priority", op="lt", value=3)],
        ))
        priorities = [m.properties["priority"] for m in r.matches]
        assert all(p < 3 for p in priorities)

    def test_lte_filter(self, vault: Vault):
        r = vault.query_properties(QueryPropertiesRequest(
            filters=[PropertyFilter(field="priority", op="lte", value=2)],
        ))
        priorities = [m.properties["priority"] for m in r.matches]
        assert all(p <= 2 for p in priorities)

    def test_exists_filter(self, vault: Vault):
        r = vault.query_properties(QueryPropertiesRequest(
            filters=[PropertyFilter(field="priority", op="exists")],
        ))
        assert r.total_matches == 4  # project(3), idea(1), done(5), nested(2)

    def test_not_exists_filter(self, vault: Vault):
        r = vault.query_properties(QueryPropertiesRequest(
            filters=[PropertyFilter(field="priority", op="not_exists")],
        ))
        assert r.total_matches == 1  # notags

    def test_multiple_filters_anded(self, vault: Vault):
        r = vault.query_properties(QueryPropertiesRequest(
            filters=[
                PropertyFilter(field="status", op="eq", value="active"),
                PropertyFilter(field="priority", op="gte", value=3),
            ],
        ))
        titles = [m.properties["title"] for m in r.matches]
        assert titles == ["Project Alpha"]

    def test_no_filters_returns_all_with_frontmatter(self, vault: Vault):
        r = vault.query_properties(QueryPropertiesRequest())
        assert r.total_matches == 5  # all except nofrontmatter

    def test_filter_in_subdirectory(self, vault: Vault):
        r = vault.query_properties(QueryPropertiesRequest(
            filters=[PropertyFilter(field="status", op="eq", value="active")],
            path="notes/sub",
        ))
        titles = [m.properties["title"] for m in r.matches]
        assert titles == ["Nested Note"]

    def test_invalid_path_raises(self, vault: Vault):
        with pytest.raises(VaultFileError, match="not a directory"):
            vault.query_properties(QueryPropertiesRequest(path="nonexistent"))


# ---------------------------------------------------------------------------
# Property Query — sorting
# ---------------------------------------------------------------------------


class TestPropertySorting:
    def test_sort_by_property_ascending(self, vault: Vault):
        r = vault.query_properties(QueryPropertiesRequest(
            sort=PropertySort(field="priority", order=SortOrder.ASCENDING),
        ))
        priorities = [m.properties["priority"] for m in r.matches if "priority" in m.properties]
        assert priorities == sorted(priorities)

    def test_sort_by_property_descending(self, vault: Vault):
        r = vault.query_properties(QueryPropertiesRequest(
            sort=PropertySort(field="priority", order=SortOrder.DESCENDING),
        ))
        priorities = [m.properties["priority"] for m in r.matches if "priority" in m.properties]
        assert priorities == sorted(priorities, reverse=True)

    def test_sort_by_path(self, vault: Vault):
        r = vault.query_properties(QueryPropertiesRequest(
            sort=PropertySort(field="path", order=SortOrder.ASCENDING),
        ))
        paths = [m.path for m in r.matches]
        assert paths == sorted(paths)


# ---------------------------------------------------------------------------
# Property Query — select (projection)
# ---------------------------------------------------------------------------


class TestPropertySelect:
    def test_select_specific_fields(self, vault: Vault):
        r = vault.query_properties(QueryPropertiesRequest(
            select=["title", "status"],
        ))
        for m in r.matches:
            assert set(m.properties.keys()).issubset({"title", "status"})

    def test_select_nonexistent_field_yields_empty(self, vault: Vault):
        r = vault.query_properties(QueryPropertiesRequest(
            select=["nonexistent"],
        ))
        for m in r.matches:
            assert m.properties == {}

    def test_no_select_returns_all(self, vault: Vault):
        r = vault.query_properties(QueryPropertiesRequest())
        # At least one match should have multiple properties
        assert any(len(m.properties) > 2 for m in r.matches)


# ---------------------------------------------------------------------------
# Property Query — pagination
# ---------------------------------------------------------------------------


class TestPropertyPagination:
    def test_limit(self, vault: Vault):
        r = vault.query_properties(QueryPropertiesRequest(limit=2))
        assert len(r.matches) == 2
        assert r.total_matches >= 2  # total_matches is the unfiltered total

    def test_limit_and_offset(self, vault: Vault):
        r1 = vault.query_properties(QueryPropertiesRequest(limit=2, sort=PropertySort(field="path")))
        r2 = vault.query_properties(QueryPropertiesRequest(limit=2, offset=2, sort=PropertySort(field="path")))
        # No overlap
        paths1 = {m.path for m in r1.matches}
        paths2 = {m.path for m in r2.matches}
        assert not paths1.intersection(paths2)


# ---------------------------------------------------------------------------
# Tag Index
# ---------------------------------------------------------------------------


class TestTagIndex:
    def test_basic_tag_index(self, vault: Vault):
        r = vault.tag_index(TagIndexRequest())
        tag_map = {t.value: t.count for t in r.tags}
        assert tag_map["work"] == 3
        assert tag_map["urgent"] == 1
        assert tag_map["personal"] == 1

    def test_custom_property(self, vault: Vault):
        r = vault.tag_index(TagIndexRequest(properties=["status"]))
        values = [t.value for t in r.tags]
        assert "active" in values
        assert "done" in values

    def test_min_count_filter(self, vault: Vault):
        r = vault.tag_index(TagIndexRequest(min_count=2))
        for t in r.tags:
            assert t.count >= 2
        # "work" should still be present (count=3)
        values = [t.value for t in r.tags]
        assert "work" in values

    def test_sorted_by_count_descending(self, vault: Vault):
        r = vault.tag_index(TagIndexRequest())
        counts = [t.count for t in r.tags]
        assert counts == sorted(counts, reverse=True)

    def test_index_in_subdirectory(self, vault: Vault):
        r = vault.tag_index(TagIndexRequest(path="notes/sub"))
        tag_map = {t.value: t.count for t in r.tags}
        assert tag_map == {"work": 1}

    def test_invalid_path_raises(self, vault: Vault):
        with pytest.raises(VaultFileError, match="not a directory"):
            vault.tag_index(TagIndexRequest(path="nonexistent"))

    def test_files_scanned(self, vault: Vault):
        r = vault.tag_index(TagIndexRequest())
        # 5 md files with frontmatter + 1 without
        assert r.total_files_scanned == 6
