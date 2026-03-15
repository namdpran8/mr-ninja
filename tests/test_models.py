"""
tests/test_models.py
Tests for core Pydantic data models.
"""
import pytest
from mr_ninja.core.models import (
    Severity, FilePriority, AgentType,
    FileEntry, Chunk, ChunkPlan, Finding,
    ChunkSummary, AnalysisReport,
    AnalyzeRequest, AnalyzeResponse, HealthResponse,
)


class TestSeverity:

    def test_rank_ordering(self):
        assert Severity.CRITICAL.rank < Severity.HIGH.rank
        assert Severity.HIGH.rank < Severity.MEDIUM.rank
        assert Severity.MEDIUM.rank < Severity.LOW.rank
        assert Severity.LOW.rank < Severity.INFO.rank

    def test_less_than_operator(self):
        assert Severity.CRITICAL < Severity.HIGH
        assert Severity.HIGH < Severity.MEDIUM
        assert not Severity.LOW < Severity.CRITICAL

    def test_string_values(self):
        assert Severity.CRITICAL.value == "CRITICAL"
        assert Severity.INFO.value == "INFO"


class TestFileEntry:

    def test_churn_computed(self):
        f = FileEntry(path="app.py", additions=10, deletions=5)
        assert f.churn == 15

    def test_default_priority(self):
        f = FileEntry(path="app.py")
        assert f.priority == FilePriority.CHANGED_FILE

    def test_path_required(self):
        with pytest.raises(Exception):
            FileEntry()


class TestChunk:

    def test_file_count_computed(self):
        files = [
            FileEntry(path=f"f{i}.py", estimated_tokens=100)
            for i in range(3)
        ]
        chunk = Chunk(chunk_id=1, files=files, estimated_tokens=300)
        assert chunk.file_count == 3

    def test_file_paths_computed(self):
        files = [FileEntry(path="a.py"), FileEntry(path="b.py")]
        chunk = Chunk(chunk_id=1, files=files, estimated_tokens=200)
        assert "a.py" in chunk.file_paths
        assert "b.py" in chunk.file_paths

    def test_summary_line(self):
        chunk = Chunk(
            chunk_id=2,
            files=[FileEntry(path="x.py", estimated_tokens=1000)],
            estimated_tokens=1000,
            recommended_agent=AgentType.SECURITY,
        )
        line = chunk.summary_line()
        assert "Chunk 2" in line
        assert "Security" in line


class TestChunkPlan:

    def test_chunk_count_computed(self):
        plan = ChunkPlan(
            mr_id="1",
            chunks=[
                Chunk(chunk_id=1, files=[], estimated_tokens=0),
                Chunk(chunk_id=2, files=[], estimated_tokens=0),
            ],
        )
        assert plan.chunk_count == 2

    def test_empty_chunks(self):
        plan = ChunkPlan(mr_id="1")
        assert plan.chunk_count == 0


class TestFinding:

    def test_defaults(self):
        f = Finding(file="app.py")
        assert f.severity == Severity.INFO
        assert f.category == "general"

    def test_severity_set(self):
        f = Finding(file="app.py", severity=Severity.CRITICAL)
        assert f.severity == Severity.CRITICAL


class TestAnalysisReport:

    def test_severity_counts(self):
        findings = [
            Finding(file="a.py", severity=Severity.CRITICAL),
            Finding(file="b.py", severity=Severity.CRITICAL),
            Finding(file="c.py", severity=Severity.HIGH),
        ]
        report = AnalysisReport(mr_id="1", findings=findings)
        assert report.severity_counts["CRITICAL"] == 2
        assert report.severity_counts["HIGH"] == 1
        assert report.critical_count == 2
        assert report.high_count == 1

    def test_empty_findings(self):
        report = AnalysisReport(mr_id="1")
        assert report.critical_count == 0
        assert report.severity_counts == {}


class TestApiModels:

    def test_analyze_request_defaults(self):
        req = AnalyzeRequest()
        assert req.max_chunk_tokens == 70_000
        assert req.post_comment is True

    def test_analyze_response_defaults(self):
        resp = AnalyzeResponse()
        assert resp.status == "ok"
        assert resp.error is None

    def test_health_response(self):
        h = HealthResponse()
        assert h.status == "healthy"
        assert h.service == "mr-ninja"
