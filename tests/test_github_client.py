"""
tests/test_github_client.py
Tests for the GitHub API client.
"""
import json
import urllib.error

import pytest
from unittest.mock import patch, MagicMock

from mr_ninja.github.github_client import GitHubClient, GitHubClientError


# -----------------------------------------------------------------------
# parse_pr_url
# -----------------------------------------------------------------------


class TestParsePrUrl:

    def test_standard_url(self):
        base, owner, repo, number = GitHubClient.parse_pr_url(
            "https://github.com/octocat/Hello-World/pull/42"
        )
        assert base == "https://github.com"
        assert owner == "octocat"
        assert repo == "Hello-World"
        assert number == 42

    def test_enterprise_url(self):
        base, owner, repo, number = GitHubClient.parse_pr_url(
            "https://github.mycompany.com/team/service/pull/7"
        )
        assert base == "https://github.mycompany.com"
        assert owner == "team"
        assert repo == "service"
        assert number == 7

    def test_invalid_url_raises_value_error(self):
        with pytest.raises(ValueError):
            GitHubClient.parse_pr_url(
                "https://gitlab.com/group/project/-/merge_requests/42"
            )

    def test_missing_pr_number_raises(self):
        with pytest.raises(ValueError):
            GitHubClient.parse_pr_url(
                "https://github.com/owner/repo/pull/"
            )


# -----------------------------------------------------------------------
# parse_repo_string
# -----------------------------------------------------------------------


class TestParseRepoString:

    def test_valid_string(self):
        owner, repo = GitHubClient.parse_repo_string("octocat/Hello-World")
        assert owner == "octocat"
        assert repo == "Hello-World"

    def test_missing_slash_raises(self):
        with pytest.raises(ValueError):
            GitHubClient.parse_repo_string("just-a-name")

    def test_too_many_slashes_raises(self):
        with pytest.raises(ValueError):
            GitHubClient.parse_repo_string("a/b/c")

    def test_empty_parts_raise(self):
        with pytest.raises(ValueError):
            GitHubClient.parse_repo_string("/repo")
        with pytest.raises(ValueError):
            GitHubClient.parse_repo_string("owner/")


# -----------------------------------------------------------------------
# Mocked API calls
# -----------------------------------------------------------------------


class TestGitHubClientRequests:

    def _make_mock_response(self, data, status: int = 200):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(data).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        return mock_resp

    def test_get_pull_request(self):
        client = GitHubClient(token="fake-token")
        mock_resp = self._make_mock_response(
            {"number": 42, "title": "Test PR"}
        )
        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = client.get_pull_request("octocat", "Hello-World", 42)
        assert result["title"] == "Test PR"
        assert result["number"] == 42

    def test_get_all_pull_request_files_single_page(self):
        client = GitHubClient(token="fake-token")
        files = [
            {"filename": "a.py", "patch": "@@ -1 +1 @@\n-old\n+new"},
            {"filename": "b.py", "patch": "@@ -0,0 +1 @@\n+added"},
        ]
        mock_resp = self._make_mock_response(files)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = client.get_all_pull_request_files("o", "r", 1)
        assert len(result) == 2
        assert result[0]["filename"] == "a.py"

    def test_get_all_pull_request_files_pagination(self):
        client = GitHubClient(token="fake-token")
        # First page: full page (PER_PAGE items) -> triggers next page
        page1 = [{"filename": f"f{i}.py", "patch": ""} for i in range(100)]
        page2 = [{"filename": "last.py", "patch": ""}]

        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return self._make_mock_response(page1)
            return self._make_mock_response(page2)

        with patch("urllib.request.urlopen", side_effect=side_effect):
            result = client.get_all_pull_request_files("o", "r", 1)
        assert len(result) == 101
        assert call_count == 2

    def test_create_pull_request_comment(self):
        client = GitHubClient(token="fake-token")
        mock_resp = self._make_mock_response({"id": 99, "body": "LGTM"})
        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = client.create_pull_request_comment(
                "octocat", "Hello-World", 42, "LGTM"
            )
        assert result["id"] == 99
        assert result["body"] == "LGTM"

    # -------------------------------------------------------------------
    # Rate limit retry
    # -------------------------------------------------------------------

    def test_rate_limit_retries_on_429(self):
        client = GitHubClient(token="fake-token")
        mock_resp = self._make_mock_response({"number": 1, "title": "PR"})
        rate_limit_error = urllib.error.HTTPError(
            url="", code=429, msg="Too Many Requests", hdrs={}, fp=None
        )
        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise rate_limit_error
            return mock_resp

        with patch("urllib.request.urlopen", side_effect=side_effect):
            with patch("time.sleep"):
                result = client.get_pull_request("o", "r", 1)
        assert result["title"] == "PR"
        assert call_count == 2

    def test_rate_limit_retries_on_403(self):
        client = GitHubClient(token="fake-token")
        mock_resp = self._make_mock_response({"number": 1, "title": "PR"})
        rate_limit_error = urllib.error.HTTPError(
            url="", code=403, msg="Forbidden", hdrs={}, fp=None
        )
        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise rate_limit_error
            return mock_resp

        with patch("urllib.request.urlopen", side_effect=side_effect):
            with patch("time.sleep"):
                result = client.get_pull_request("o", "r", 1)
        assert result["title"] == "PR"
        assert call_count == 2

    # -------------------------------------------------------------------
    # Error handling
    # -------------------------------------------------------------------

    def test_404_raises_github_client_error(self):
        client = GitHubClient(token="fake-token")
        with patch(
            "urllib.request.urlopen",
            side_effect=urllib.error.HTTPError(
                url="", code=404, msg="Not Found", hdrs={}, fp=None
            ),
        ):
            with pytest.raises(GitHubClientError) as exc_info:
                client.get_pull_request("octocat", "missing", 999)
        assert exc_info.value.status_code == 404
