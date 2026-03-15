"""
tests/test_cli.py
Tests for the CLI argument parser and subcommand routing.
"""
import pytest
from unittest.mock import patch, MagicMock
from mr_ninja.cli import build_parser, main


class TestBuildParser:

    def test_parser_exists(self):
        parser = build_parser()
        assert parser is not None

    def test_analyze_subcommand_registered(self):
        parser = build_parser()
        args = parser.parse_args([
            "analyze", "https://gitlab.com/g/p/-/merge_requests/1",
            "--token", "tok"
        ])
        assert args.command == "analyze"
        assert args.mr_url == "https://gitlab.com/g/p/-/merge_requests/1"

    def test_demo_subcommand_registered(self):
        parser = build_parser()
        args = parser.parse_args(["demo", "--files", "10"])
        assert args.command == "demo"
        assert args.files == 10

    def test_demo_default_files(self):
        parser = build_parser()
        args = parser.parse_args(["demo"])
        assert args.files == 512

    def test_serve_subcommand_registered(self):
        parser = build_parser()
        args = parser.parse_args(["serve", "--port", "9000"])
        assert args.command == "serve"
        assert args.port == 9000

    def test_no_subcommand_returns_zero(self):
        result = main([])
        assert result == 0

    def test_analyze_requires_token(self):
        """analyze without a token and no env var should return error code."""
        with patch.dict("os.environ", {}, clear=True):
            import os
            os.environ.pop("GITLAB_TOKEN", None)
            result = main(["analyze", "--project", "g/p", "--mr", "1"])
        assert result == 1

    def test_demo_runs_end_to_end(self):
        """Demo with a small file count should complete without error."""
        with patch("mr_ninja.demo.simulate_large_mr.run_demo") as mock_demo:
            mock_demo.return_value = None
            result = main(["demo", "--files", "5"])
        mock_demo.assert_called_once_with(file_count=5, output_file="")
        assert result == 0


class TestMainRouting:

    def test_unknown_command_exits(self):
        with pytest.raises(SystemExit) as exc_info:
            main(["nonexistent_command"])
        assert exc_info.value.code == 2

    def test_keyboard_interrupt_returns_130(self):
        with patch("mr_ninja.cli.cmd_demo", side_effect=KeyboardInterrupt):
            result = main(["demo"])
        assert result == 130
