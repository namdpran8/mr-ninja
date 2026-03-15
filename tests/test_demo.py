"""
tests/test_demo.py
Tests for the demo simulation and file generator.
"""
import pytest
from mr_ninja.demo.simulate_large_mr import generate_demo_files
from mr_ninja.core.models import FileEntry


class TestGenerateDemoFiles:

    def test_returns_list_of_file_entries(self):
        files = generate_demo_files(file_count=30)
        assert isinstance(files, list)
        assert len(files) > 0
        assert all(isinstance(f, FileEntry) for f in files)

    def test_file_count_roughly_matches_request(self):
        files = generate_demo_files(file_count=50)
        # Generator creates files per-service so count may vary slightly
        assert len(files) >= 30

    def test_files_have_paths(self):
        files = generate_demo_files(file_count=30)
        assert all(f.path for f in files)
        # Most files have directory separators; root-level files like .gitlab-ci.yml may not
        files_with_dirs = [f for f in files if "/" in f.path]
        assert len(files_with_dirs) > len(files) * 0.9

    def test_files_have_diff_content(self):
        files = generate_demo_files(file_count=30)
        files_with_content = [f for f in files if f.diff_content]
        assert len(files_with_content) > 0

    def test_security_critical_files_present(self):
        """Each service should get a .env and Dockerfile."""
        files = generate_demo_files(file_count=30)
        paths = [f.path for f in files]
        env_files = [p for p in paths if p.endswith(".env")]
        dockerfiles = [p for p in paths if "Dockerfile" in p]
        assert len(env_files) > 0
        assert len(dockerfiles) > 0

    def test_test_files_present(self):
        files = generate_demo_files(file_count=30)
        paths = [f.path for f in files]
        test_files = [p for p in paths if "test_" in p or "/tests/" in p]
        assert len(test_files) > 0

    def test_token_estimates_are_positive(self):
        files = generate_demo_files(file_count=30)
        assert all(f.estimated_tokens > 0 for f in files)

    def test_vulnerability_patterns_present(self):
        """Vulnerable files should be generated with detectable patterns."""
        import random
        random.seed(42)  # fix seed so ~20% vuln rate is deterministic
        files = generate_demo_files(file_count=100)
        all_content = " ".join(f.diff_content for f in files)
        # At least one of the known vuln patterns should appear
        vuln_signals = [
            "eval(", "shell=True", "pickle.loads",
            "verify=False", "password =", "secret_key ="
        ]
        found = [sig for sig in vuln_signals if sig in all_content]
        assert len(found) > 0, (
            f"No vulnerability patterns found. Checked: {vuln_signals}"
        )


class TestFullDemoPipeline:

    def test_small_demo_runs_without_error(self):
        """End-to-end smoke test with a tiny file count."""
        from mr_ninja.agents.orchestrator import Orchestrator
        files = generate_demo_files(file_count=20)
        orchestrator = Orchestrator(post_comments=False, use_duo_agents=False)
        report = orchestrator.analyze_files(
            files=files,
            mr_id="test-smoke",
            mr_title="Smoke test MR",
        )
        assert report is not None
        assert report.mr_id == "test-smoke"
        assert report.chunks_processed >= 1
        assert report.processing_time_seconds > 0

    def test_demo_report_contains_findings(self):
        """With vulnerable files, the report should flag issues."""
        from mr_ninja.agents.orchestrator import Orchestrator
        import random
        random.seed(0)
        files = generate_demo_files(file_count=60)
        orchestrator = Orchestrator(post_comments=False, use_duo_agents=False)
        report = orchestrator.analyze_files(
            files=files, mr_id="vuln-test", mr_title="Vuln test"
        )
        assert len(report.findings) > 0

    def test_markdown_report_renders(self):
        """The aggregator should produce non-empty Markdown output."""
        from mr_ninja.agents.orchestrator import Orchestrator
        from mr_ninja.agents.chunk_planner import ChunkPlanner
        files = generate_demo_files(file_count=20)
        orchestrator = Orchestrator(post_comments=False, use_duo_agents=False)
        report = orchestrator.analyze_files(
            files=files, mr_id="md-test", mr_title="Markdown test"
        )
        planner = ChunkPlanner()
        plan = planner.plan_from_files(files, "md-test", "Markdown test")
        markdown = orchestrator.aggregator.render_markdown(
            plan, report.processing_time_seconds
        )
        assert "Mr Ninja Analysis Report" in markdown
        assert "md-test" in markdown
        assert len(markdown) > 200
