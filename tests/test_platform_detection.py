"""
tests/test_platform_detection.py
Tests for the Platform enum and detect_from_url().
"""
import pytest

from mr_ninja.core.models import Platform


class TestPlatformEnumValues:

    def test_gitlab_value(self):
        assert Platform.GITLAB.value == "gitlab"

    def test_github_value(self):
        assert Platform.GITHUB.value == "github"


class TestDetectFromUrl:

    def test_github_dot_com(self):
        result = Platform.detect_from_url(
            "https://github.com/octocat/Hello-World/pull/42"
        )
        assert result is Platform.GITHUB

    def test_gitlab_dot_com(self):
        result = Platform.detect_from_url(
            "https://gitlab.com/group/project/-/merge_requests/7"
        )
        assert result is Platform.GITLAB

    def test_self_hosted_gitlab(self):
        result = Platform.detect_from_url(
            "https://gitlab.mycompany.com/team/repo/-/merge_requests/3"
        )
        assert result is Platform.GITLAB

    def test_github_enterprise(self):
        result = Platform.detect_from_url(
            "https://github.com/enterprise/internal-app/pull/99"
        )
        assert result is Platform.GITHUB

    def test_unknown_url_raises_value_error(self):
        with pytest.raises(ValueError, match="Cannot detect platform"):
            Platform.detect_from_url("https://bitbucket.org/team/repo/pull-requests/1")
