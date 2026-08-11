"""Safe atomic patch engine with unified diff generation and rollback."""

from __future__ import annotations

import difflib
from pathlib import Path
from typing import TYPE_CHECKING

from spec_pipeline.core.models import FileChange

if TYPE_CHECKING:
    from collections.abc import Sequence


class PatchEngine:
    """Applies file changes atomically with unified diff generation and rollback on failure."""

    def apply_changes(
        self,
        changes: Sequence[FileChange],
        sandbox_root: str | Path,
    ) -> list[FileChange]:
        """Apply *changes* to the filesystem under *sandbox_root*.

        If any error occurs during application, all changes made during
        the session are rolled back atomically to restore the original state.

        Returns
        -------
        list[FileChange]
            Updated list of FileChange objects enriched with diffs.
        """
        root = Path(sandbox_root).resolve()
        root.mkdir(parents=True, exist_ok=True)

        # Track previous state for rollback: Path -> original content (None if did not exist)
        backups: dict[Path, str | None] = {}
        processed_changes: list[FileChange] = []

        try:
            for change in changes:
                target_file = (root / change.path).resolve()

                # Ensure target is still within sandbox_root
                if not str(target_file).startswith(str(root)):
                    raise ValueError(
                        f"Target path {change.path!r} resolves outside sandbox root {root}"
                    )

                # Record backup before touching file
                if target_file not in backups:
                    if target_file.is_file():
                        backups[target_file] = target_file.read_text(encoding="utf-8")
                    else:
                        backups[target_file] = None

                new_change = self._apply_single_change(change, target_file)
                processed_changes.append(new_change)

            return processed_changes

        except Exception as exc:
            # Perform atomic rollback
            self._rollback(backups)
            raise exc

    def generate_diff(
        self,
        original_content: str,
        new_content: str,
        filepath: str,
    ) -> str:
        """Generate a standard unified diff between two text versions."""
        orig_lines = original_content.splitlines(keepends=True)
        new_lines = new_content.splitlines(keepends=True)

        diff_lines = list(
            difflib.unified_diff(
                orig_lines,
                new_lines,
                fromfile=f"a/{filepath}",
                tofile=f"b/{filepath}",
            )
        )
        return "".join(diff_lines)

    # ── Internal Helpers ─────────────────────────────────────────────────── #

    def _apply_single_change(self, change: FileChange, target_file: Path) -> FileChange:
        """Apply a single FileChange action and compute unified diff."""
        action = change.action.lower()
        original_content = ""

        if target_file.is_file():
            original_content = target_file.read_text(encoding="utf-8")

        new_content = change.content or ""
        diff_text = self.generate_diff(original_content, new_content, change.path)

        if action in {"create", "modify"}:
            target_file.parent.mkdir(parents=True, exist_ok=True)
            target_file.write_text(new_content, encoding="utf-8")
            diff_summary = change.diff_summary or (
                f"Created {change.path}" if action == "create" else f"Modified {change.path}"
            )
        elif action == "delete":
            if target_file.is_file():
                target_file.unlink()
            diff_summary = change.diff_summary or f"Deleted {change.path}"
        else:
            raise ValueError(f"Unknown change action: {change.action!r}")

        return FileChange(
            path=change.path,
            action=change.action,
            content=change.content,
            diff_summary=diff_summary if not diff_text else f"{diff_summary}\n{diff_text}".strip(),
        )

    def _rollback(self, backups: dict[Path, str | None]) -> None:
        """Restore all backed up files to their original states."""
        for path, original_content in backups.items():
            try:
                if original_content is None:
                    # File was newly created, remove it
                    if path.is_file():
                        path.unlink()
                else:
                    # File was modified/deleted, restore original content
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(original_content, encoding="utf-8")
            except Exception:
                # Best-effort rollback
                pass
