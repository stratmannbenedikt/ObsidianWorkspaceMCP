"""Core vault operations — directory traversal, file I/O, search."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

import json
from pathlib import Path

from .models import (
    CreateFileResponse,
    CreateFromTemplateRequest,
    CreateFromTemplateResponse,
    CreateTemplateRequest,
    CreateTemplateResponse,
    DeleteFileResponse,
    DirectoryEntry,
    DirectoryTreeNode,
    DirectoryTreeResponse,
    EditFileRequest,
    EditFileResponse,
    FileChangeType,
    GetTemplateResponse,
    ListDirectoryResponse,
    ListTemplatesResponse,
    ReadFileResponse,
    SearchMatch,
    SearchRequest,
    SearchResponse,
    SortBy,
    SortOrder,
    Template,
    TemplateField,
    VaultStats,
)


class VaultSecurityError(Exception):
    """Raised when an operation would escape the configured vault directory."""

    pass


class VaultFileError(Exception):
    """Raised when a file operation fails (not found, permission, etc.)."""

    pass


class Vault:
    """Operations against a single configured vault root directory."""

    def __init__(self, root: Path) -> None:
        self._root = root.resolve()
        if not self._root.is_dir():
            raise ValueError(f"Vault root is not a directory: {self._root}")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve(self, relative: str) -> Path:
        """Resolve a relative path, enforcing the vault boundary."""
        if ".." in relative:
            # Block path traversal explicitly
            resolved = (self._root / relative).resolve()
            if not str(resolved).startswith(str(self._root)):
                raise VaultSecurityError(
                    f"Path traversal attempt detected: {relative!r}"
                )
            return resolved
        return self._root / relative

    @staticmethod
    def _mtime(path: Path) -> datetime | None:
        try:
            return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        except OSError:
            return None

    # ------------------------------------------------------------------
    # Read-only operations
    # ------------------------------------------------------------------

    def stats(self) -> VaultStats:
        """Return aggregate statistics for the vault."""
        total_files = 0
        total_size = 0
        last_modified: datetime | None = None

        for path in self._root.rglob("*"):
            if not path.is_file():
                continue
            total_files += 1
            try:
                total_size += path.stat().st_size
            except OSError:
                pass
            mtime = self._mtime(path)
            if mtime is not None and (last_modified is None or mtime > last_modified):
                last_modified = mtime

        return VaultStats(
            total_files=total_files,
            total_size_bytes=total_size,
            last_modified=last_modified,
        )

    def list_directory(
        self,
        path: str = "",
        sort_by: SortBy = SortBy.NAME,
        sort_order: SortOrder = SortOrder.ASCENDING,
    ) -> ListDirectoryResponse:
        """List the contents of a vault subdirectory."""
        target = self._resolve(path)
        if not target.is_dir():
            raise VaultFileError(f"Not a directory: {path!r}")

        entries: list[DirectoryEntry] = []
        for child in target.iterdir():
            stat = child.stat() if child.exists() else None
            entries.append(
                DirectoryEntry(
                    name=child.name,
                    path=child.relative_to(self._root).as_posix(),
                    is_dir=child.is_dir(),
                    size_bytes=stat.st_size if stat else None,
                    modified=self._mtime(child),
                )
            )

        # Sort
        key = _sort_key(sort_by)
        entries.sort(key=key, reverse=(sort_order == SortOrder.DESCENDING))

        return ListDirectoryResponse(entries=entries, path=path or ".")

    def read_file(self, path: str) -> ReadFileResponse:
        """Read the full contents of a vault file."""
        target = self._resolve(path)
        if not target.is_file():
            raise VaultFileError(f"File not found: {path!r}")
        try:
            content = target.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise VaultFileError(
                f"File is not valid UTF-8: {path!r}"
            ) from exc
        except OSError as exc:
            raise VaultFileError(f"Could not read {path!r}: {exc}") from exc

        return ReadFileResponse(
            path=path,
            content=content,
            size_bytes=len(content.encode("utf-8")),
            modified=self._mtime(target),
        )

    def search(self, request: SearchRequest) -> SearchResponse:
        """Search for text inside vault files."""
        root = self._resolve(request.path) if request.path else self._root
        if not root.is_dir():
            raise VaultFileError(f"Search path not a directory: {request.path!r}")

        flags = 0 if request.case_sensitive else re.IGNORECASE
        pattern = re.compile(re.escape(request.query), flags)

        total_matches = 0
        files_searched = 0
        matches: list[SearchMatch] = []

        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if request.file_extension and path.suffix != request.file_extension:
                continue
            files_searched += 1

            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue

            for lineno, line in enumerate(text.splitlines(), start=1):
                for m in pattern.finditer(line):
                    total_matches += 1
                    matches.append(
                        SearchMatch(
                            path=str(path.relative_to(self._root).as_posix()),
                            line_number=lineno,
                            line_content=line,
                            match_start=m.start(),
                            match_end=m.end(),
                        )
                    )

        return SearchResponse(
            query=request.query,
            total_matches=total_matches,
            files_searched=files_searched,
            matches=matches,
        )

    # ------------------------------------------------------------------
    # Directory tree
    # ------------------------------------------------------------------

    def directory_tree(
        self,
        path: str = "",
        max_depth: int = 3,
        max_files_per_dir: int = 20,
    ) -> DirectoryTreeResponse:
        """Build a tree-style representation of a vault directory."""
        target = self._resolve(path) if path else self._root
        if not target.is_dir():
            raise VaultFileError(f"Not a directory: {path!r}")

        lines: list[str] = []
        root_node = self._build_tree_node(
            target, prefix="", is_last=True, is_root=True,
            depth=0, max_depth=max_depth,
            max_files_per_dir=max_files_per_dir,
            lines=lines,
        )

        return DirectoryTreeResponse(
            tree=root_node,
            text="\n".join(lines),
        )

    def _build_tree_node(
        self,
        path: Path,
        prefix: str,
        is_last: bool,
        is_root: bool,
        depth: int,
        max_depth: int,
        max_files_per_dir: int,
        lines: list[str],
    ) -> DirectoryTreeNode:
        """Recursively build tree nodes and append text lines."""
        name = path.name or path.as_posix()
        rel = path.relative_to(self._root).as_posix()

        if is_root:
            lines.append(f"{name}/")
        else:
            connector = "└── " if is_last else "├── "
            suffix = "/" if path.is_dir() else ""
            lines.append(f"{prefix}{connector}{name}{suffix}")

        node = DirectoryTreeNode(
            name=name,
            path=rel,
            is_dir=path.is_dir(),
        )

        if not path.is_dir() or depth >= max_depth:
            return node

        try:
            children = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except OSError:
            return node

        # Apply max_files_per_dir limit
        truncated = False
        if len(children) > max_files_per_dir:
            children = children[:max_files_per_dir]
            truncated = True

        child_prefix = prefix + ("    " if is_root else ("    " if is_last else "│   "))

        for i, child in enumerate(children):
            is_last_child = (i == len(children) - 1) and not truncated
            child_node = self._build_tree_node(
                child,
                prefix=child_prefix,
                is_last=is_last_child,
                is_root=False,
                depth=depth + 1,
                max_depth=max_depth,
                max_files_per_dir=max_files_per_dir,
                lines=lines,
            )
            node.children.append(child_node)

        if truncated:
            remaining = 0
            try:
                remaining = sum(1 for _ in path.iterdir()) - max_files_per_dir
            except OSError:
                pass
            connector = "└── "
            lines.append(f"{child_prefix}{connector}... ({remaining} more)")
            node.truncated = True

        return node

    # ------------------------------------------------------------------
    # Templates
    # ------------------------------------------------------------------

    @property
    def _templates_dir(self) -> Path:
        d = self._root / ".templates"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _template_path(self, name: str) -> Path:
        safe = re.sub(r'[^a-zA-Z0-9_-]', '_', name).strip('_')
        return self._templates_dir / f"{safe}.json"

    def create_template(self, req: CreateTemplateRequest) -> CreateTemplateResponse:
        """Create or update a page template."""
        template = Template(name=req.name, description=req.description, fields=req.fields)
        path = self._template_path(req.name)
        path.write_text(template.model_dump_json(indent=2), encoding="utf-8")
        return CreateTemplateResponse(name=req.name)

    def get_template(self, name: str) -> GetTemplateResponse:
        """Retrieve a template by name."""
        path = self._template_path(name)
        if not path.is_file():
            raise VaultFileError(f"Template not found: {name!r}")
        template = Template.model_validate_json(path.read_text(encoding="utf-8"))
        return GetTemplateResponse(template=template)

    def list_templates(self) -> ListTemplatesResponse:
        """List all available templates."""
        templates: list[Template] = []
        for p in sorted(self._templates_dir.glob("*.json")):
            try:
                templates.append(Template.model_validate_json(p.read_text(encoding="utf-8")))
            except Exception:
                continue
        return ListTemplatesResponse(templates=templates)

    def create_from_template(self, req: CreateFromTemplateRequest) -> CreateFromTemplateResponse:
        """Create a new file using a template's frontmatter structure."""
        tpl_path = self._template_path(req.template_name)
        if not tpl_path.is_file():
            raise VaultFileError(f"Template not found: {req.template_name!r}")
        template = Template.model_validate_json(tpl_path.read_text(encoding="utf-8"))

        # Build frontmatter
        fm_lines = ["---"]
        for field in template.fields:
            value = req.values.get(field.name)
            if value is None:
                value = field.default

            if value is None and field.required:
                value = f""  # placeholder for required fields with no value

            fm_lines.append(self._format_field(field.name, value, field.type))
        fm_lines.append("---")

        content = "\n".join(fm_lines)
        if req.body:
            content += "\n\n" + req.body

        # Write the file
        target = self._resolve(req.path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

        return CreateFromTemplateResponse(
            path=req.path,
            template_name=req.template_name,
            content=content,
        )

    @staticmethod
    def _format_field(name: str, value: Any, field_type: str) -> str:
        """Format a single frontmatter field."""
        if value is None:
            return f"{name}:"

        if field_type == "multi-list" and isinstance(value, list):
            return f"{name}: [{', '.join(str(v) for v in value)}]"

        if isinstance(value, list):
            if len(value) == 0:
                return f"{name}: []"
            return f"{name}:\n" + "\n".join(f"  - {v}" for v in value)

        if isinstance(value, bool):
            return f"{name}: {str(value).lower()}"

        if isinstance(value, (int, float)):
            return f"{name}: {value}"

        # String — quote if contains special chars
        s = str(value)
        if any(c in s for c in '":{}[]|>!#%@`*,'):
            return f'{name}: "{s}"'
        return f"{name}: {s}"

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    def create_file(self, path: str, content: str = "") -> CreateFileResponse:
        """Create a new file (or overwrite an existing one) in the vault."""
        target = self._resolve(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            target.write_text(content, encoding="utf-8")
        except OSError as exc:
            raise VaultFileError(f"Could not create {path!r}: {exc}") from exc

        return CreateFileResponse(
            path=path,
            change_type=FileChangeType.CREATED,
            size_bytes=len(content.encode("utf-8")),
        )

    def edit_file(self, request: EditFileRequest) -> EditFileResponse:
        """Perform an in-place text replacement in a vault file."""
        target = self._resolve(request.path)
        if not target.is_file():
            raise VaultFileError(f"File not found: {request.path!r}")

        content = target.read_text(encoding="utf-8")
        old_text = request.old_text
        new_text = request.new_text

        if request.count == 0:
            # Replace all occurrences
            new_content, count = content.replace(old_text, new_text), content.count(old_text)
        else:
            # Replace first `count` occurrences
            count = 0
            new_content = content
            start = 0
            for _ in range(request.count):
                idx = new_content.find(old_text, start)
                if idx == -1:
                    break
                new_content = new_content[:idx] + new_text + new_content[idx + len(old_text):]
                start = idx + len(new_text)
                count += 1

        if count == 0:
            raise VaultFileError(
                f"Text to replace not found in {request.path!r}"
            )

        target.write_text(new_content, encoding="utf-8")
        return EditFileResponse(
            path=request.path,
            change_type=FileChangeType.MODIFIED,
            replacements_made=count,
        )

    def delete_file(self, path: str) -> DeleteFileResponse:
        """Delete a file from the vault."""
        target = self._resolve(path)
        if not target.exists():
            raise VaultFileError(f"File not found: {path!r}")
        if not target.is_file():
            raise VaultFileError(f"Not a regular file: {path!r}")
        try:
            target.unlink()
        except OSError as exc:
            raise VaultFileError(f"Could not delete {path!r}: {exc}") from exc

        return DeleteFileResponse(
            path=path,
            change_type=FileChangeType.DELETED,
        )


def _sort_key(sort_by: SortBy):
    """Return a sort key function for DirectoryEntry lists."""
    if sort_by == SortBy.NAME:
        return lambda e: (not e.is_dir, e.name.lower())
    if sort_by == SortBy.MODIFIED:
        return lambda e: (e.modified or datetime.min)
    if sort_by == SortBy.SIZE:
        return lambda e: (e.size_bytes or 0)
    return lambda e: e.name.lower()
