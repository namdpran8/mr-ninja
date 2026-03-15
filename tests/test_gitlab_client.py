"""
tests/test_gitlab_client.py
Tests for the GitLab API client.
"""
import pytest
import json
from unittest.mock import patch, MagicMock, call
from mr_ninja.gitlab.gitlab_client import GitLabClient, GitLabClientError


class TestParseMrUrl:

    def test_standard_url(self):
        base, project, iid = GitLabClient.parse_mr_url(
            "https://gitlab.com/mygroup/myproject/-/merge_requests/42"
        )
        assert base == "https://gitlab.com"
        assert project == "mygroup/myproject"
        assert iid == 42

    def test_nested_group_url(self):
        base, project, iid = GitLabClient.parse_mr_url(
            "https://gitlab.com/a/b/c/-/merge_requests/7"
        )
        assert project == "a/b/c"
        assert iid == 7

    def test_self_hosted_instance(self):
        base, project, iid = GitLabClient.parse_mr_url(
            "https://gitlab.mycompany.com/team/repo/-/merge_requests/5"
        )
        assert base == "https://gitlab.mycompany.com"
        assert project == "team/repo"
        assert iid == 5

    def test_invalid_url_raises_value_error(self):
        with pytest.raises(ValueError):
            GitLabClient.parse_mr_url("https://github.com/org/repo/pull/42")

    def test_missing_mr_number_raises(self):
        with pytest.raises(ValueError):
            GitLabClient.parse_mr_url(
                "https://gitlab.com/group/project/-/merge_requests/"
            )


class TestGitLabClientInit:

    def test_default_url(self):
        client = GitLabClient()
        assert "gitlab.com" in client.base_url

    def test_custom_url(self):
        client = GitLabClient(gitlab_url="https://mygitlab.com")
        assert "mygitlab.com" in client.base_url

    def test_trailing_slash_stripped(self):
        client = GitLabClient(gitlab_url="https://gitlab.com/")
        assert not client.base_url.endswith("//api/v4")


class TestGitLabClientRequests:

    def _make_mock_response(self, data: dict | list, status: int = 200):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(data).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        return mock_resp

    def test_get_merge_request(self):
        client = GitLabClient(token="fake-token")
        mock_resp = self._make_mock_response(
            {"id": 1, "iid": 42, "title": "Test MR"}
        )
        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = client.get_merge_request("group/project", 42)
        assert result["title"] == "Test MR"
        assert result["iid"] == 42

    def test_create_note(self):
        client = GitLabClient(token="fake-token")
        mock_resp = self._make_mock_response({"id": 99, "body": "hello"})
        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = client.create_merge_request_note(
                "group/project", 42, "hello"
            )
        assert result["id"] == 99

    def test_empty_response_returns_empty_dict(self):
        client = GitLabClient(token="fake-token")
        mock_resp = MagicMock()
        mock_resp.read.return_value = b""
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = client.get_project("group/project")
        assert result == {}

    def test_http_error_raises_client_error(self):
        import urllib.error
        client = GitLabClient(token="fake-token")
        with patch(
            "urllib.request.urlopen",
            side_effect=urllib.error.HTTPError(
                url="", code=404, msg="Not Found", hdrs={}, fp=None
            ),
        ):
            with pytest.raises(GitLabClientError) as exc_info:
                client.get_merge_request("group/project", 999)
        assert exc_info.value.status_code == 404

    def test_rate_limit_retries(self):
        import urllib.error
        client = GitLabClient(token="fake-token")
        mock_resp = self._make_mock_response({"id": 1, "title": "MR"})
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
                result = client.get_merge_request("group/project", 1)
        assert result["title"] == "MR"
        assert call_count == 2
