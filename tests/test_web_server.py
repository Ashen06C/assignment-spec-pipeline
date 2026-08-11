"""Unit and integration test suite for the Web Studio HTTP Server & REST API."""

from __future__ import annotations

import json
import socket
import threading
import urllib.error
import urllib.request
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from spec_pipeline.web.server import create_server

if TYPE_CHECKING:
    from collections.abc import Generator

SPECS_DIR = Path(__file__).resolve().parent.parent / "examples" / "specs"


def find_free_port() -> int:
    """Find a free TCP port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture(scope="module")
def server_url() -> Generator[str, None, None]:
    """Start Web Studio server in a background thread for testing."""
    port = find_free_port()
    server = create_server(host="127.0.0.1", port=port)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    url = f"http://127.0.0.1:{port}"
    yield url

    server.shutdown()
    server.server_close()


def http_get(url: str) -> tuple[int, dict[str, str], bytes]:
    """Helper for GET requests."""
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req) as resp:
        return resp.status, dict(resp.headers), resp.read()


def http_post_json(url: str, data: dict[str, Any]) -> tuple[int, dict[str, str], dict[str, Any]]:
    """Helper for POST JSON requests."""
    body = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        resp_data = json.loads(resp.read().decode("utf-8"))
        return resp.status, dict(resp.headers), resp_data


# ──────────────────────────────────────────────────────────────────────────────
# Test Cases
# ──────────────────────────────────────────────────────────────────────────────


class TestWebStudioStaticServing:
    def test_serve_index_html(self, server_url: str) -> None:
        status, headers, body = http_get(f"{server_url}/")
        assert status == 200
        assert "text/html" in headers.get("Content-Type", "")
        assert b"Spec-Driven Pipeline" in body

    def test_serve_css(self, server_url: str) -> None:
        status, headers, body = http_get(f"{server_url}/index.css")
        assert status == 200
        assert "text/css" in headers.get("Content-Type", "")
        assert b"--bg-canvas" in body

    def test_serve_javascript(self, server_url: str) -> None:
        status, headers, body = http_get(f"{server_url}/app.js")
        assert status == 200
        assert "application/javascript" in headers.get("Content-Type", "")
        assert b"triggerValidation" in body or b"validate" in body


class TestWebStudioRestAPI:
    def test_get_specs(self, server_url: str) -> None:
        status, _, body = http_get(f"{server_url}/api/specs")
        assert status == 200
        data = json.loads(body.decode("utf-8"))
        assert "specs" in data
        assert len(data["specs"]) >= 3
        titles = [s["title"] for s in data["specs"]]
        assert "Token Bucket Rate Limiter" in titles

    def test_get_models(self, server_url: str) -> None:
        status, _, body = http_get(f"{server_url}/api/models")
        assert status == 200
        data = json.loads(body.decode("utf-8"))
        assert "providers" in data
        provider_ids = [p["id"] for p in data["providers"]]
        assert "mock" in provider_ids
        assert "gemini" in provider_ids
        assert "openai" in provider_ids

    def test_validate_endpoint_valid_yaml(self, server_url: str) -> None:
        spec_file = SPECS_DIR / "token_bucket_limiter.yaml"
        content = spec_file.read_text(encoding="utf-8")

        status, _, data = http_post_json(
            f"{server_url}/api/validate",
            {"content": content, "format": "yaml"},
        )
        assert status == 200
        assert data["valid"] is True
        assert data["spec"]["title"] == "Token Bucket Rate Limiter"
        assert len(data["spec_hash"]) == 64
        assert all(data["section_checklist"].values())

    def test_validate_endpoint_invalid_spec(self, server_url: str) -> None:
        invalid_spec = "title: Incomplete Feature\nobjective: Only an objective\n"
        status, _, data = http_post_json(
            f"{server_url}/api/validate",
            {"content": invalid_spec, "format": "yaml"},
        )
        assert status == 200
        assert data["valid"] is False
        assert len(data["errors"]) >= 1

    def test_plan_endpoint(self, server_url: str) -> None:
        spec_file = SPECS_DIR / "token_bucket_limiter.yaml"
        content = spec_file.read_text(encoding="utf-8")

        status, _, data = http_post_json(
            f"{server_url}/api/plan",
            {"content": content, "format": "yaml", "provider": "mock"},
        )
        assert status == 200
        assert "plan" in data
        assert len(data["plan"]["tasks"]) >= 1
        assert len(data["plan"]["risks"]) >= 1

    def test_run_endpoint_fast_auto(self, server_url: str) -> None:
        spec_file = SPECS_DIR / "token_bucket_limiter.yaml"
        content = spec_file.read_text(encoding="utf-8")

        status, _, data = http_post_json(
            f"{server_url}/api/run",
            {
                "content": content,
                "format": "yaml",
                "provider": "mock",
                "auto_approve": True,
                "reviewer": "Automated Tester",
            },
        )
        assert status == 200
        assert data["session_id"] is not None
        assert data["result"]["quality_results"]["all_passed"] is True
        assert "/api/artifacts/" in data["dashboard_url"]

    def test_staged_governed_workflow_end_to_end(self, server_url: str) -> None:
        spec_file = SPECS_DIR / "token_bucket_limiter.yaml"
        content = spec_file.read_text(encoding="utf-8")

        # 1. Start Governed Session (Stage 1 & 2)
        status, _, step1 = http_post_json(
            f"{server_url}/api/pipeline/start",
            {"content": content, "format": "yaml", "provider": "mock"},
        )
        assert status == 200
        session_id = step1["session_id"]
        assert step1["stage"] == "PLAN_READY"
        assert step1["requires_approval"] == "checkpoint_1"
        assert step1["spec"]["title"] == "Token Bucket Rate Limiter"

        # 2. Approve Checkpoint #1 (Stage 3 -> Stage 4-6: Synthesis, Tests, Gates)
        status, _, step2 = http_post_json(
            f"{server_url}/api/pipeline/approve-plan",
            {
                "session_id": session_id,
                "reviewer": "Architect Alice",
                "comments": "Approved technical plan.",
            },
        )
        assert status == 200
        assert step2["stage"] == "VERIFIED"
        assert step2["checkpoint_1"]["status"] == "approved"
        assert step2["checkpoint_1"]["signature"] != ""
        assert step2["quality_results"]["all_passed"] is True
        assert step2["requires_approval"] == "checkpoint_2"

        # 3. Approve Checkpoint #2 (Stage 7: Finalize Merge, Provenance & Reports)
        status, _, step3 = http_post_json(
            f"{server_url}/api/pipeline/approve-merge",
            {
                "session_id": session_id,
                "reviewer": "Release Lead Bob",
                "comments": "All gates passed.",
            },
        )
        assert status == 200
        assert step3["stage"] == "COMPLETED"
        assert step3["checkpoint_2"]["status"] == "approved"
        assert step3["provenance"]["_type"] == "https://in-toto.io/Statement/v0.1"

        # 4. Fetch generated artifacts via REST
        art_status, _, art_body = http_get(f"{server_url}{step3['dashboard_url']}")
        assert art_status == 200
        assert b"<!DOCTYPE html>" in art_body

    def test_staged_governed_workflow_rejection(self, server_url: str) -> None:
        spec_file = SPECS_DIR / "token_bucket_limiter.yaml"
        content = spec_file.read_text(encoding="utf-8")

        # Start session
        status, _, step1 = http_post_json(
            f"{server_url}/api/pipeline/start",
            {"content": content, "format": "yaml", "provider": "mock"},
        )
        assert status == 200
        session_id = step1["session_id"]

        # Reject at Checkpoint #1
        status, _, step_rej = http_post_json(
            f"{server_url}/api/pipeline/reject",
            {
                "session_id": session_id,
                "checkpoint": "checkpoint_1",
                "reviewer": "Security Lead",
                "reason": "Blast radius exceeds safety threshold.",
            },
        )
        assert status == 200
        assert step_rej["stage"] == "REJECTED"
        assert step_rej["decision"]["status"] == "rejected"
