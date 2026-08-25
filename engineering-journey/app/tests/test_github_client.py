"""Tests for GitHub API client."""

import os
import subprocess
import pytest
from github_client import GitHubAPIError, GitHubClient


def get_test_credentials():
    token = os.environ.get("GITHUB_TOKEN")
    username = os.environ.get("GITHUB_USERNAME") or "schr3b3r"
    if not token:
        try:
            token = subprocess.check_output(["gh", "auth", "token"], text=True).strip()
        except Exception:
            token = None
    return token, username


def test_github_client_init_requires_credentials(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_USERNAME", raising=False)

    with pytest.raises(ValueError, match="GitHub token is required"):
        GitHubClient(username="testuser")

    with pytest.raises(ValueError, match="GitHub username is required"):
        GitHubClient(token="testtoken")


def test_github_client_init_with_args():
    client = GitHubClient(token="dummy_token", username="dummy_user")
    assert client.token == "dummy_token"
    assert client.username == "dummy_user"


def test_github_client_init_with_env(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "env_token")
    monkeypatch.setenv("GITHUB_USERNAME", "env_user")

    client = GitHubClient()
    assert client.token == "env_token"
    assert client.username == "env_user"


def test_list_accessible_repositories_mock_pagination_and_filter(monkeypatch):
    """Test list_accessible_repositories pagination and pushed_at filtering with mock HTTP responses."""
    client = GitHubClient(token="dummy_token", username="dummy_user")

    # Construct 100 items for page 1 to trigger pagination to page 2
    page_1 = [
        {"full_name": "dummy_user/repo1", "pushed_at": "2026-05-10T12:00:00Z"},
        {"full_name": "dummy_user/repo2", "pushed_at": "2026-01-01T00:00:00Z"},
    ] + [
        {"full_name": f"dummy_user/old_repo_{i}", "pushed_at": "2025-01-01T00:00:00Z"}
        for i in range(98)
    ]
    page_2 = [
        {"full_name": "dummy_user/repo3", "pushed_at": "2026-05-20T15:30:00Z"},
    ]

    def mock_get(url, params=None, timeout=None):
        class MockResponse:
            status_code = 200

            def json(self):
                if params and params.get("page") == 1:
                    return page_1
                return page_2

        return MockResponse()

    monkeypatch.setattr(client.session, "get", mock_get)

    # Filter for May 2026
    repos = client.list_accessible_repositories(
        pushed_after="2026-05-01", pushed_before="2026-05-31"
    )
    assert repos == ["dummy_user/repo1", "dummy_user/repo3"]
    assert "dummy_user/repo2" not in repos


def test_has_author_activity_mock_short_circuits_on_commits(monkeypatch):
    """Test that has_author_activity returns True on commit match and short-circuits the issues search."""
    client = GitHubClient(token="dummy_token", username="dummy_user")
    requests_made = []

    def mock_get(url, params=None, timeout=None):
        requests_made.append(url)

        class MockResponse:
            status_code = 200

            def json(self):
                if "search/commits" in url:
                    return {"total_count": 1, "items": [{"sha": "12345"}]}
                return {"total_count": 0, "items": []}

        return MockResponse()

    monkeypatch.setattr(client.session, "get", mock_get)

    result = client.has_author_activity("dummy_user/repo1", "2026-01-01", "2026-06-01")
    assert result is True
    # Only 1 call made (search/commits) because commits > 0 short-circuits issues search
    assert len(requests_made) == 1
    assert "search/commits" in requests_made[0]


def test_has_author_activity_mock_checks_issues_when_no_commits(monkeypatch):
    """Test that has_author_activity checks issues search when commits search returns 0."""
    client = GitHubClient(token="dummy_token", username="dummy_user")
    requests_made = []

    def mock_get(url, params=None, timeout=None):
        requests_made.append(url)

        class MockResponse:
            status_code = 200

            def json(self):
                if "search/commits" in url:
                    return {"total_count": 0, "items": []}
                if "search/issues" in url:
                    return {"total_count": 2, "items": [{"id": 1}]}
                return {"total_count": 0, "items": []}

        return MockResponse()

    monkeypatch.setattr(client.session, "get", mock_get)

    result = client.has_author_activity("dummy_user/repo1", "2026-01-01", "2026-06-01")
    assert result is True
    assert len(requests_made) == 2
    assert "search/commits" in requests_made[0]
    assert "search/issues" in requests_made[1]


def test_has_author_activity_mock_returns_false_when_no_activity(monkeypatch):
    """Test that has_author_activity returns False when both commits and issues searches return 0."""
    client = GitHubClient(token="dummy_token", username="dummy_user")
    requests_made = []

    def mock_get(url, params=None, timeout=None):
        requests_made.append(url)

        class MockResponse:
            status_code = 200

            def json(self):
                return {"total_count": 0, "items": []}

        return MockResponse()

    monkeypatch.setattr(client.session, "get", mock_get)

    result = client.has_author_activity("dummy_user/repo1", "2026-01-01", "2026-06-01")
    assert result is False
    assert len(requests_made) == 2


def test_real_github_client_contributions_and_search():
    token, username = get_test_credentials()
    if not token:
        pytest.skip("No GitHub token available for live API test.")

    client = GitHubClient(token=token, username=username)

    # Query 2026-06 contributions
    contributions = client.get_contributions_collection("2026-06-01", "2026-07-01")
    assert contributions["username"] == username
    assert "repositories" in contributions
    assert "fulcradynamics/agent-skills" in contributions["repositories"]

    # Query commits
    commits = client.fetch_commits(
        "fulcradynamics/agent-skills", "2026-06-01", "2026-07-01"
    )
    assert len(commits) > 0
    assert "sha" in commits[0]
    assert "commit" in commits[0]

    # Query PRs
    prs = client.fetch_pull_requests(
        "fulcradynamics/agent-skills", "2026-06-01", "2026-07-01"
    )
    assert len(prs) > 0
    assert "title" in prs[0]

    # Query Issues
    issues = client.fetch_issues(
        "fulcradynamics/agent-skills", "2026-06-01", "2026-07-01"
    )
    assert len(issues) > 0
    assert "title" in issues[0]


def test_has_author_activity_real():
    """Real live API test for has_author_activity."""
    token, username = get_test_credentials()
    if not token:
        pytest.skip("No GitHub token available for live API test.")

    client = GitHubClient(token=token, username=username)

    # Repo with activity in June 2026
    has_act = client.has_author_activity(
        "fulcradynamics/agent-skills", "2026-06-01", "2026-07-01"
    )
    assert has_act is True

    # Check a repo/range with no activity
    no_act = client.has_author_activity(
        "octocat/Hello-World", "2026-06-01", "2026-07-01"
    )
    assert no_act is False


def test_list_accessible_repositories_real():
    """Real live API test for list_accessible_repositories."""
    token, username = get_test_credentials()
    if not token:
        pytest.skip("No GitHub token available for live API test.")

    client = GitHubClient(token=token, username=username)
    repos = client.list_accessible_repositories()

    assert isinstance(repos, list)
    assert f"{username}/shimmer" in repos


def test_enumerate_repositories_includes_private_repos_real():
    """Real live API test proving enumerate_repositories includes private repos (e.g. shimmer)
    which GraphQL contributionsCollection missed."""
    token, username = get_test_credentials()
    if not token:
        pytest.skip("No GitHub token available for live API test.")

    client = GitHubClient(token=token, username=username)

    # Window covering shimmer May 2026 activity
    repos = client.enumerate_repositories("2026-05-01", "2026-05-31")
    assert isinstance(repos, list)
    assert f"{username}/shimmer" in repos


def test_contributions_collection_rejects_spans_over_one_year():
    """Empirically confirmed (Milestone 3): GitHub's GraphQL API rejects a
    contributionsCollection 'from'/'to' span exceeding 1 year, with a real
    VALIDATION error -- not just a documentation claim. enumerate_repositories
    must chunk into <=1-year windows to work across a ~3-year span."""
    token, username = get_test_credentials()
    if not token:
        pytest.skip("No GitHub token available for live API test.")

    client = GitHubClient(token=token, username=username)

    with pytest.raises(GitHubAPIError, match="must not exceed 1 year"):
        client.get_contributions_collection("2022-01-01", "2026-01-01")


def test_enumerate_repositories_multi_year_span_real():
    """Real, multi-year (>1 year) enumeration -- must internally chunk into
    <=1-year contributionsCollection queries and merge results, per
    Milestone 3's empirical GitHub API constraint discovery."""
    token, username = get_test_credentials()
    if not token:
        pytest.skip("No GitHub token available for live API test.")

    client = GitHubClient(token=token, username=username)

    repos = client.enumerate_repositories("2024-01-01", "2026-07-01")
    assert isinstance(repos, list)
    assert repos == sorted(repos)
    assert len(set(repos)) == len(repos)  # no duplicates across window boundary
    assert "fulcradynamics/agent-skills" in repos
