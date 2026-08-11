"""Automated heuristic risk analyzer for feature specifications and implementation plans.

Evaluates specifications across 4 critical risk categories:
1. Concurrency    — Shared state, multi-threading, rate limiting, race conditions, atomic locks.
2. Security       — Tokens, credentials, authentication, encryption, PII, mTLS, authorization.
3. Blast Radius   — Broad file impacts, multiple module alterations, structural scope.
4. Performance    — In-memory growth, latency SLAs (p99), throughput, caching, complexity.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from spec_pipeline.core.models import EvaluatedRisk

if TYPE_CHECKING:
    from spec_pipeline.core.models import FeatureSpec


class RiskAnalyzer:
    """Heuristic-based deterministic risk assessment engine."""

    # ── Rule matchers ────────────────────────────────────────────────────── #

    _CONCURRENCY_PATTERNS = [
        (
            r"\b(concurren\w*|shared\s+state|race\s+condition|multi-?thread\w*|"
            r"atomic\w*|lock\w*|mutex|synchroni[zs]\w*|token\s+bucket|rate\s+limit\w*)\b",
            "Potential race conditions or state synchronization bottlenecks in concurrent "
            "workflows.",
            "concurrency",
            "medium",
            "high",
            "Use atomic primitives (e.g. Redis Lua scripts, distributed locks, or "
            "compare-and-swap semantics) and implement multi-threaded stress tests.",
        )
    ]

    _SECURITY_PATTERNS = [
        (
            r"\b(token\w*|credential\w*|auth\w*|secret\w*|password\w*|api[_\s]key\w*|"
            r"pii|encrypt\w*|mtls|permission\w*|tamper\w*|audit\s+log\w*)\b",
            "Sensitive data, cryptographic keys, authentication, or audit integrity "
            "requirements detected.",
            "security",
            "medium",
            "high",
            "Enforce strict mTLS/TLS, sanitize logs to prevent credential leaks, employ "
            "envelope encryption for PII, and validate authorization boundaries.",
        )
    ]

    _PERFORMANCE_PATTERNS = [
        (
            r"\b(latenc\w*|throughput|p9[0-9]|cache\w*|in-memory|growth|scale|scaling|"
            r"50[,.]?000|10[,.]?000|eps|rpm|bottleneck|algorithmic)\b",
            "High-throughput constraints, low-latency SLAs, or memory growth risks identified.",
            "performance",
            "medium",
            "medium",
            "Implement caching with bounded TTL, optimize data structures for O(1) lookups, "
            "profile latency budgets under peak load, and configure eviction policies.",
        )
    ]

    def analyze(
        self,
        spec: FeatureSpec,
        impacted_files: list[str] | None = None,
    ) -> list[EvaluatedRisk]:
        """Analyze *spec* and optional *impacted_files* for potential risks.

        Returns
        -------
        list[EvaluatedRisk]
            Deduplicated list of identified risks with actionable mitigations.
        """
        corpus = self._build_spec_corpus(spec)
        risks: list[EvaluatedRisk] = []
        counter = 1

        # 1. Concurrency Analysis
        for pattern, desc, cat, likelihood, impact, mitigation in self._CONCURRENCY_PATTERNS:
            if re.search(pattern, corpus, re.IGNORECASE):
                risks.append(
                    EvaluatedRisk(
                        risk_id=f"RISK-{counter:03d}",
                        category=cat,
                        description=desc,
                        likelihood=likelihood,
                        impact=impact,
                        mitigation=mitigation,
                    )
                )
                counter += 1

        # 2. Security Analysis
        for pattern, desc, cat, likelihood, impact, mitigation in self._SECURITY_PATTERNS:
            if re.search(pattern, corpus, re.IGNORECASE):
                risks.append(
                    EvaluatedRisk(
                        risk_id=f"RISK-{counter:03d}",
                        category=cat,
                        description=desc,
                        likelihood=likelihood,
                        impact=impact,
                        mitigation=mitigation,
                    )
                )
                counter += 1

        # 3. Performance Analysis
        for pattern, desc, cat, likelihood, impact, mitigation in self._PERFORMANCE_PATTERNS:
            if re.search(pattern, corpus, re.IGNORECASE):
                risks.append(
                    EvaluatedRisk(
                        risk_id=f"RISK-{counter:03d}",
                        category=cat,
                        description=desc,
                        likelihood=likelihood,
                        impact=impact,
                        mitigation=mitigation,
                    )
                )
                counter += 1

        # 4. Blast Radius Analysis
        blast_risks = self._check_blast_radius(impacted_files, counter)
        risks.extend(blast_risks)

        return risks

    # ── Internal Helpers ─────────────────────────────────────────────────── #

    def _check_blast_radius(
        self,
        impacted_files: list[str] | None,
        start_counter: int,
    ) -> list[EvaluatedRisk]:
        """Check for wide blast radius based on impacted files."""
        if not impacted_files:
            return []

        risks: list[EvaluatedRisk] = []
        # Flag if more than 4 files modified
        if len(impacted_files) >= 4:
            risks.append(
                EvaluatedRisk(
                    risk_id=f"RISK-{start_counter:03d}",
                    category="blast_radius",
                    description=(
                        f"Wide blast radius: implementation alters {len(impacted_files)} files "
                        "across multiple modules."
                    ),
                    likelihood="medium",
                    impact="high" if len(impacted_files) > 6 else "medium",
                    mitigation=(
                        "Decompose into smaller modular pull requests, enforce strict "
                        "sandbox boundaries, and guard release behind feature flags."
                    ),
                )
            )
        return risks

    @staticmethod
    def _build_spec_corpus(spec: FeatureSpec) -> str:
        """Concatenate all spec text fields into a single searchable corpus."""
        parts: list[str] = [spec.title, spec.objective]
        for s in spec.user_stories:
            parts.extend([s.as_a, s.i_want, s.so_that])
        for r in spec.business_rules:
            parts.extend([r.rule_id, r.description])
        for c in spec.acceptance_criteria:
            parts.extend([c.criterion_id, c.title, c.given, c.when, c.then])
        for n in spec.non_functional_requirements:
            parts.extend([n.category, n.description, n.threshold or ""])
        parts.extend(spec.out_of_scope)
        return " ".join(parts)
