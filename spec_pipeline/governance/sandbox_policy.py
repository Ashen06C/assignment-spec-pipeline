"""Sandbox policy enforcer for path traversal prevention and blast radius containment."""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import TYPE_CHECKING

from spec_pipeline.core.exceptions import SandboxPolicyViolationError

if TYPE_CHECKING:
    from collections.abc import Sequence

    from spec_pipeline.core.models import FileChange


class SandboxPolicyEnforcer:
    """Enforces deterministic isolation and security bounds on file operations."""

    # Standard package and test markers permitted inside allowed module hierarchies
    ALLOWED_PACKAGE_MARKERS: frozenset[str] = frozenset(
        {
            "__init__.py",
            "conftest.py",
        }
    )

    # Blacklisted paths and sensitive files that can NEVER be modified by synthesized code
    PROTECTED_PATTERNS: frozenset[str] = frozenset(
        {
            ".env",
            ".git",
            ".gitignore",
            ".github",
            ".ssh",
            ".aws",
            "id_rsa",
            "secrets",
            "credentials",
            "passwd",
            "shadow",
        }
    )

    def is_path_safe(
        self,
        target_path: str,
        allowed_files: Sequence[str] | None = None,
    ) -> bool:
        """Evaluate whether *target_path* satisfies all security constraints."""
        return len(self.check_violations(target_path, allowed_files)) == 0

    def check_violations(
        self,
        target_path: str,
        allowed_files: Sequence[str] | None = None,
    ) -> list[str]:
        """Check *target_path* for violations and return error reasons (empty if safe)."""
        reasons: list[str] = []

        if not target_path or not target_path.strip():
            return ["Empty path"]

        raw_path = target_path.strip().replace("\\", "/")

        # 1. Path Traversal & Absolute Path Checks
        if raw_path.startswith("/") or (len(raw_path) > 1 and raw_path[1] == ":"):
            reasons.append(f"Absolute paths not permitted: {target_path}")
            return reasons

        parts = raw_path.split("/")
        if ".." in parts:
            reasons.append(f"Path traversal ('..') detected: {target_path}")
            return reasons

        # Normalized posix path
        norm_path = PurePosixPath(raw_path).as_posix()

        # 2. Protected Files / Sensitive Paths
        lower_parts = [p.lower() for p in parts]
        for protected in self.PROTECTED_PATTERNS:
            if any(p == protected or p.startswith(f"{protected}.") for p in lower_parts):
                reasons.append(f"Modification to protected path forbidden: {target_path}")
                return reasons
            if protected in norm_path.lower():
                reasons.append(f"Protected keyword '{protected}' in path: {target_path}")
                return reasons

        # 3. Blast Radius Containment (if allowed_files is specified)
        if allowed_files is not None:
            normalized_allowed = {
                PurePosixPath(f.strip().replace("\\", "/")).as_posix()
                for f in allowed_files
                if f.strip()
            }

            filename = PurePosixPath(norm_path).name
            is_package_marker = filename in self.ALLOWED_PACKAGE_MARKERS

            # Check if exactly in allowed list
            if norm_path not in normalized_allowed:
                # If it's a package marker, check if its directory is within an allowed module
                if is_package_marker:
                    parent_dir = str(PurePosixPath(norm_path).parent)
                    allowed_parents = {
                        str(PurePosixPath(af).parent) for af in normalized_allowed
                    }
                    if parent_dir not in allowed_parents and parent_dir != ".":
                        reasons.append(
                            f"Package marker outside approved modules: {target_path}"
                        )
                else:
                    reasons.append(
                        f"Blast radius containment: '{target_path}' is not in approved "
                        "impacted_files list"
                    )

        return reasons

    def validate_changes(
        self,
        changes: Sequence[FileChange],
        allowed_files: Sequence[str] | None = None,
    ) -> None:
        """Validate all proposed changes against sandbox rules.

        Raises
        ------
        SandboxPolicyViolationError
            If any change violates path traversal, protected path, or blast radius policies.
        """
        violating_paths: list[str] = []

        for change in changes:
            violations = self.check_violations(change.path, allowed_files)
            if violations:
                for v in violations:
                    violating_paths.append(f"{change.path} ({v})")

        if violating_paths:
            raise SandboxPolicyViolationError(violating_paths=violating_paths)
