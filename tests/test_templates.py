"""Tests for template functionality."""

from __future__ import annotations

from pathlib import Path

import pytest

from obsidian_workspace_mcp.models import (
    CreateFromTemplateRequest,
    CreateTemplateRequest,
    TemplateField,
)
from obsidian_workspace_mcp.vault import Vault, VaultFileError


@pytest.fixture
def vault(tmp_path: Path) -> Vault:
    return Vault(tmp_path)


class TestCreateTemplate:
    def test_create_basic_template(self, vault: Vault):
        req = CreateTemplateRequest(
            name="paper",
            description="Academic paper template",
            fields=[
                TemplateField(name="title", type="string", description="Paper title"),
                TemplateField(name="authors", type="list", default=[]),
                TemplateField(name="date", type="date", default=""),
                TemplateField(name="tags", type="multi-list", default=[]),
                TemplateField(name="status", type="string", default="todo"),
            ],
        )
        r = vault.create_template(req)
        assert r.name == "paper"

    def test_get_template(self, vault: Vault):
        vault.create_template(CreateTemplateRequest(
            name="event",
            description="Event template",
            fields=[TemplateField(name="name", type="string")],
        ))
        r = vault.get_template("event")
        assert r.template.name == "event"
        assert len(r.template.fields) == 1

    def test_get_nonexistent_raises(self, vault: Vault):
        with pytest.raises(VaultFileError, match="Template not found"):
            vault.get_template("nonexistent")

    def test_list_templates(self, vault: Vault):
        vault.create_template(CreateTemplateRequest(
            name="a", description="Template A",
            fields=[TemplateField(name="x", type="string")],
        ))
        vault.create_template(CreateTemplateRequest(
            name="b", description="Template B",
            fields=[TemplateField(name="y", type="string")],
        ))
        r = vault.list_templates()
        assert len(r.templates) == 2
        names = [t.name for t in r.templates]
        assert "a" in names
        assert "b" in names


class TestCreateFromTemplate:
    def _create_paper_template(self, vault: Vault):
        vault.create_template(CreateTemplateRequest(
            name="paper",
            description="Paper template",
            fields=[
                TemplateField(name="title", type="string", required=True),
                TemplateField(name="authors", type="list", required=False, default=[]),
                TemplateField(name="date", type="string", default=""),
                TemplateField(name="status", type="string", default="reading"),
                TemplateField(name="tags", type="multi-list", default=[]),
            ],
        ))

    def test_create_from_template_basic(self, vault: Vault):
        self._create_paper_template(vault)
        r = vault.create_from_template(CreateFromTemplateRequest(
            template_name="paper",
            path="papers/My Paper.md",
            values={"title": "Test Paper", "date": "2026-01-01"},
        ))
        assert r.path == "papers/My Paper.md"
        assert "---" in r.content
        assert "title: Test Paper" in r.content
        assert "date: 2026-01-01" in r.content

    def test_uses_defaults_for_missing_fields(self, vault: Vault):
        self._create_paper_template(vault)
        r = vault.create_from_template(CreateFromTemplateRequest(
            template_name="paper",
            path="papers/Draft.md",
            values={"title": "Draft"},
        ))
        assert "status: reading" in r.content
        assert "authors:" in r.content

    def test_file_actually_created(self, vault: Vault):
        self._create_paper_template(vault)
        vault.create_from_template(CreateFromTemplateRequest(
            template_name="paper",
            path="papers/Test.md",
            values={"title": "Test"},
        ))
        read = vault.read_file("papers/Test.md")
        assert "title: Test" in read.content

    def test_body_appended_after_frontmatter(self, vault: Vault):
        self._create_paper_template(vault)
        r = vault.create_from_template(CreateFromTemplateRequest(
            template_name="paper",
            path="notes/Note.md",
            values={"title": "Note"},
            body="## Summary\n\nSome content here.",
        ))
        assert r.content.endswith("## Summary\n\nSome content here.")

    def test_nonexistent_template_raises(self, vault: Vault):
        with pytest.raises(VaultFileError, match="Template not found"):
            vault.create_from_template(CreateFromTemplateRequest(
                template_name="nonexistent",
                path="notes/test.md",
            ))

    def test_list_type_formatting(self, vault: Vault):
        vault.create_template(CreateTemplateRequest(
            name="list_test",
            description="Test",
            fields=[
                TemplateField(name="items", type="list", default=[]),
            ],
        ))
        r = vault.create_from_template(CreateFromTemplateRequest(
            template_name="list_test",
            path="test.md",
            values={"items": ["apple", "banana"]},
        ))
        assert "- apple" in r.content
        assert "- banana" in r.content

    def test_multi_list_inline_formatting(self, vault: Vault):
        vault.create_template(CreateTemplateRequest(
            name="tags_test",
            description="Test",
            fields=[
                TemplateField(name="tags", type="multi-list", default=[]),
            ],
        ))
        r = vault.create_from_template(CreateFromTemplateRequest(
            template_name="tags_test",
            path="test.md",
            values={"tags": ["ml", "nlp"]},
        ))
        assert "tags: [ml, nlp]" in r.content
