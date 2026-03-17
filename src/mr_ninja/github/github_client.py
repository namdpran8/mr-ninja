"""
github/github_client.py

GitHub API connector for Mr Ninja.

Provides a dependency-free client for interacting with GitHub's REST API.
Handles PR metadata, file diffs, comment posting, and pagination.

All API calls include automatic retry with backoff for rate limiting.
"""

from __future__ import annotations

import json
import logging
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Optional

logger = logging.getLogger("mr_ninja.github_client")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_GITHUB_URL = "https://api.github.com"
DEFAULT_TIMEOUT = 30
MAX_RETRIES = 2
RETRY_DELAY_SECONDS = 2
PER_PAGE = 100


class GitHubClientError(Exception):
    """Raised when a GitHub API call fails."""

    def __init__(self, message: str, status_code: int = 0):
        super().__init__(message)
        self.status_code = status_code


class GitHubClient:
    """Minimal, dependency-free GitHub REST API client.

    Uses only stdlib (urllib) to avoid requiring ``requests`` as a dependency.
    Supports all operations needed by the Mr Ninja pipeline:
    - Fetching PR metadata and file diffs
    - Reading file contents
    - Posting PR comments

    Args:
        base_url: Base URL for the GitHub API (default: https://api.github.com).
        token: Personal access token or GitHub App token.
        timeout: Request timeout in seconds.
    """

    def __init__(
        self,
        base_url: str = DEFAULT_GITHUB_URL,
        token: str = "",
        timeout: int = DEFAULT_TIMEOUT,
    ):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout

    # ------------------------------------------------------------------
    # Low-level HTTP helpers
    # ------------------------------------------------------------------

    def _request(
        self,
        method: str,
        path: str,
        params: Optional[dict] = None,
        data: Optional[dict] = None,
    ) -> Any:
        """Execute an HTTP request against the GitHub API.

        Includes automatic retry on 403/429 (rate limit) responses.

        Args:
            method: HTTP method (GET, POST, PUT).
            path: API path (appended to base_url).
            params: Query parameters.
            data: JSON body data.

        Returns:
            Parsed JSON response (dict or list).

        Raises:
            GitHubClientError: On non-retryable API failures.
        """
        url = f"{self.base_url}{path}"
        if params:
            filtered = {k: v for k, v in params.items() if v is not None}
            if filtered:
                url += "?" + urllib.parse.urlencode(filtered)

        body = json.dumps(data).encode() if data else None
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
        }

        for attempt in range(MAX_RETRIES + 1):
            try:
                req = urllib.request.Request(
                    url, data=body, headers=headers, method=method
                )
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    response_body = resp.read()
                    if not response_body:
                        return {}
                    return json.loads(response_body)

            except urllib.error.HTTPError as e:
                if e.code in (403, 429) and attempt < MAX_RETRIES:
                    logger.warning(
                        f"Rate limited on {method} {path}, "
                        f"retrying in {RETRY_DELAY_SECONDS}s "
                        f"(attempt {attempt + 1}/{MAX_RETRIES})"
                    )
                    time.sleep(RETRY_DELAY_SECONDS)
                    continue
                logger.error(f"GitHub API error: {method} {path} -> {e.code}")
                raise GitHubClientError(
                    f"API {method} {path} failed: HTTP {e.code}",
                    status_code=e.code,
                )

            except Exception as e:
                if attempt < MAX_RETRIES:
                    logger.warning(f"Request failed ({e}), retrying...")
                    time.sleep(RETRY_DELAY_SECONDS)
                    continue
                logger.error(f"GitHub API error: {method} {path} -> {e}")
                raise GitHubClientError(f"API {method} {path} failed: {e}")

        return {}

    def _get(self, path: str, params: Optional[dict] = None) -> Any:
        """Convenience GET request."""
        return self._request("GET", path, params=params)

    def _post(self, path: str, data: dict) -> Any:
        """Convenience POST request."""
        return self._request("POST", path, data=data)

    # ------------------------------------------------------------------
    # Pull Request operations
    # ------------------------------------------------------------------

    def get_pull_request(self, owner: str, repo: str, pr_number: int) -> dict:
        """Fetch pull request metadata.

        Args:
            owner: Repository owner (user or organisation).
            repo: Repository name.
            pr_number: Pull request number.

        Returns:
            PR metadata dict.
        """
        return self._get(f"/repos/{owner}/{repo}/pulls/{pr_number}")

    def get_all_pull_request_files(
        self,
        owner: str,
        repo: str,
        pr_number: int,
    ) -> list[dict]:
        """Fetch ALL files changed in a pull request, handling pagination.

        Each entry contains ``filename``, ``patch``, ``status``, etc.

        Args:
            owner: Repository owner.
            repo: Repository name.
            pr_number: Pull request number.

        Returns:
            List of file-diff dicts.
        """
        all_files: list[dict] = []
        page = 1

        while True:
            batch = self._get(
                f"/repos/{owner}/{repo}/pulls/{pr_number}/files",
                {"page": page, "per_page": PER_PAGE},
            )
            if not isinstance(batch, list) or not batch:
                break
            all_files.extend(batch)
            if len(batch) < PER_PAGE:
                break
            page += 1

        logger.info(
            f"Fetched {len(all_files)} file entries for PR #{pr_number}"
        )
        return all_files

    # ------------------------------------------------------------------
    # PR comments
    # ------------------------------------------------------------------

    def create_pull_request_comment(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        body: str,
    ) -> dict:
        """Post an issue comment on a pull request.

        Args:
            owner: Repository owner.
            repo: Repository name.
            pr_number: Pull request number.
            body: Markdown comment body.

        Returns:
            Created comment dict.
        """
        return self._post(
            f"/repos/{owner}/{repo}/issues/{pr_number}/comments",
            {"body": body},
        )

    # ------------------------------------------------------------------
    # Repository file operations
    # ------------------------------------------------------------------

    def get_file_content(
        self,
        owner: str,
        repo: str,
        file_path: str,
        ref: str = "main",
    ) -> str:
        """Fetch raw file content from the repository.

        Args:
            owner: Repository owner.
            repo: Repository name.
            file_path: Path to file in the repo.
            ref: Branch, tag, or commit SHA.

        Returns:
            Decoded file content as string.
        """
        import base64

        data = self._get(
            f"/repos/{owner}/{repo}/contents/{file_path}",
            {"ref": ref},
        )

        if isinstance(data, dict) and "content" in data:
            return base64.b64decode(data["content"]).decode(
                "utf-8", errors="replace"
            )
        return ""

    # ------------------------------------------------------------------
    # Utility: parse PR URL
    # ------------------------------------------------------------------

    @staticmethod
    def parse_pr_url(url: str) -> tuple[str, str, str, int]:
        """Parse a GitHub PR URL into components.

        Args:
            url: Full PR URL like
                 https://github.com/owner/repo/pull/42
                 or enterprise: https://github.mycompany.com/owner/repo/pull/42

        Returns:
            Tuple of (base_url, owner, repo, pr_number).

        Raises:
            ValueError: If URL format is not recognised.
        """
        match = re.match(
            r"(https?://[^/]+)/([^/]+)/([^/]+)/pull/(\d+)",
            url,
        )
        if not match:
            raise ValueError(f"Cannot parse PR URL: {url}")

        return (
            match.group(1),
            match.group(2),
            match.group(3),
            int(match.group(4)),
        )

    @staticmethod
    def parse_repo_string(repo_string: str) -> tuple[str, str]:
        """Parse an ``owner/repo`` string into components.

        Args:
            repo_string: Repository identifier like ``"octocat/Hello-World"``.

        Returns:
            Tuple of (owner, repo).

        Raises:
            ValueError: If format doesn't match ``owner/repo``.
        """
        parts = repo_string.split("/")
        if len(parts) != 2 or not parts[0] or not parts[1]:
            raise ValueError(
                f"Invalid repo string '{repo_string}': expected 'owner/repo'"
            )
        return parts[0], parts[1]
