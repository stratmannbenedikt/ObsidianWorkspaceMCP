"""Core vault operations — directory traversal, file I/O, search."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from .models import (
    CreateFileResponse,
    DeleteFileResponse,
    DirectoryEntry,
    EditFileRequest,
    EditFileResponse,
    FileChangeType,
    ListDirectoryResponse,
    ReadFileResponse,
    SearchMatch,
    SearchRequest,
    SearchResponse,
    SortBy,
    SortOrder,
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
