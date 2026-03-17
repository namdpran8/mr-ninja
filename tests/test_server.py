"""
tests/test_server.py
Tests for the FastAPI REST API endpoints.
"""
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from mr_ninja.server import app


@pytest.fixture
def client():
    return TestClient(app)


class TestHealthEndpoint:

    def test_health_returns_200(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_health_body(self, client):
        data = client.get("/health").json()
        assert data["status"] == "healthy"
        assert data["service"] == "mr-ninja"
        assert data["version"] == "1.0.0"


class TestAnalyzeEndpoint:

    def test_missing_token_returns_400(self, client):
        with patch.dict("os.environ", {}, clear=True):
            import os
            os.environ.pop("GITLAB_TOKEN", None)
            resp = client.post("/analyze", json={
                "mr_url": "https://gitlab.com/g/p/-/merge_requests/1",
            })
        assert resp.status_code == 400
        assert "gitlab_token" in resp.json()["detail"]

    def test_missing_mr_info_returns_400(self, client):
        resp = client.post("/analyze", json={
            "gitlab_token": "tok",
        })
        assert resp.status_code == 400
        assert "mr_url" in resp.json()["detail"] or "project_id" in resp.json()["detail"]

    def test_successful_analyze(self, client):
        from mr_ninja.core.models import AnalysisReport, Severity
        mock_report = MagicMock(spec=AnalysisReport)
        mock_report.mr_id = "42"
        mock_report.mr_title = "Test MR"
        mock_report.chunks_processed = 2
        mock_report.findings = [MagicMock()] * 5
        mock_report.critical_count = 1
        mock_report.overall_risk = Severity.HIGH
        mock_report.processing_time_seconds = 1.5

        with patch("mr_ninja.server.Orchestrator") as MockOrch:
            instance = MockOrch.return_value
            instance.analyze_from_url.return_value = mock_report
            instance.aggregator.render_markdown.return_value = "# Report"
            resp = client.post("/analyze", json={
                "mr_url": "https://gitlab.com/g/p/-/merge_requests/42",
                "gitlab_token": "fake-token",
            })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["mr_id"] == "42"
        assert data["chunks_processed"] == 2
        assert data["total_findings"] == 5

    def test_error_response_returns_500(self, client):
        with patch("mr_ninja.server.Orchestrator") as MockOrch:
            instance = MockOrch.return_value
            instance.analyze_from_url.side_effect = RuntimeError("Something went wrong")
            resp = client.post("/analyze", json={
                "mr_url": "https://gitlab.com/g/p/-/merge_requests/42",
                "gitlab_token": "fake-token",
            })
        assert resp.status_code == 500
        assert "Something went wrong" in resp.json()["detail"]


class TestDemoEndpoint:

    def test_demo_returns_200(self, client):
        resp = client.post("/demo")
        assert resp.status_code == 200

    def test_demo_response_body(self, client):
        data = client.post("/demo").json()
        assert data["status"] == "ok"
        assert data["mr_id"] == "demo-512"
        assert data["chunks_processed"] >= 1
        assert data["total_findings"] > 0
        assert len(data["report_markdown"]) > 100

    def test_demo_report_contains_header(self, client):
        data = client.post("/demo").json()
        assert "Mr Ninja Analysis Report" in data["report_markdown"]


class TestOpenApiDocs:

    def test_docs_endpoint(self, client):
        resp = client.get("/docs")
        assert resp.status_code == 200

    def test_redoc_endpoint(self, client):
        resp = client.get("/redoc")
        assert resp.status_code == 200

    def test_openapi_json(self, client):
        resp = client.get("/openapi.json")
        assert resp.status_code == 200
        schema = resp.json()
        assert schema["info"]["title"] == "Mr Ninja"
        assert "/health" in schema["paths"]
        assert "/analyze" in schema["paths"]
        assert "/demo" in schema["paths"]
