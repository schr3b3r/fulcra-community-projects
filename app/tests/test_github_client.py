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
    commits = client.fetch_commits("fulcradynamics/agent-skills", "2026-06-01", "2026-07-01")
    assert len(commits) > 0
    assert "sha" in commits[0]
    assert "commit" in commits[0]

    # Query PRs
    prs = client.fetch_pull_requests("fulcradynamics/agent-skills", "2026-06-01", "2026-07-01")
    assert len(prs) > 0
    assert "title" in prs[0]

    # Query Issues
    issues = client.fetch_issues("fulcradynamics/agent-skills", "2026-06-01", "2026-07-01")
    assert len(issues) > 0
    assert "title" in issues[0]
