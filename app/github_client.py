"""GitHub API client for Engineering Journey backfill ingestion.

Communicates directly with GitHub REST and GraphQL APIs using the `requests`
library. Accepts runtime configuration (token, username) via constructor
arguments or environment variables (`GITHUB_TOKEN`, `GITHUB_USERNAME`).
"""

import os
from typing import Any, Dict, List, Optional
import requests


class GitHubAPIError(Exception):
    """Exception raised when a GitHub API request fails."""


class GitHubClient:
    """Client for interacting with GitHub REST and GraphQL APIs."""

    def __init__(
        self,
        token: Optional[str] = None,
        username: Optional[str] = None,
        base_url: str = "https://api.github.com",
    ) -> None:
        """Initialize GitHubClient with authentication credentials.

        Args:
            token: GitHub Personal Access Token or OAuth token. If None, checks GITHUB_TOKEN env.
            username: GitHub account username/login. If None, checks GITHUB_USERNAME env.
            base_url: GitHub API base URL (defaults to https://api.github.com).

        Raises:
            ValueError: If token or username is not provided via parameters or environment.
        """
        self.token = token or os.environ.get("GITHUB_TOKEN")
        self.username = username or os.environ.get("GITHUB_USERNAME")
        self.base_url = base_url.rstrip("/")

        if not self.token:
            raise ValueError(
                "GitHub token is required. Pass `token` or set GITHUB_TOKEN environment variable."
            )
        if not self.username:
            raise ValueError(
                "GitHub username is required. Pass `username` or set GITHUB_USERNAME environment variable."
            )

        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"token {self.token}",
                "Accept": "application/vnd.github.v3+json",
                "User-Agent": "EngineeringJourney-Skill",
            }
        )

    def _format_datetime(self, dt_str: str) -> str:
        """Ensure date/time string is ISO 8601 formatted for GraphQL."""
        if "T" in dt_str:
            return dt_str
        return f"{dt_str}T00:00:00Z"

    def get_contributions_collection(
        self, start_date: str, end_date: str
    ) -> Dict[str, Any]:
        """Query GraphQL contributionsCollection for commit, PR, review, issue activity across repos.

        Args:
            start_date: Start of date range (e.g., '2026-06-01' or ISO format).
            end_date: End of date range (e.g., '2026-07-01' or ISO format).

        Returns:
            Dict containing total contribution counts and sorted list of active repository names.
        """
        graphql_url = f"{self.base_url}/graphql"
        from_dt = self._format_datetime(start_date)
        to_dt = self._format_datetime(end_date)

        query = """
        query($username: String!, $from: DateTime!, $to: DateTime!) {
          user(login: $username) {
            contributionsCollection(from: $from, to: $to) {
              startedAt
              endedAt
              totalCommitContributions
              totalPullRequestContributions
              totalPullRequestReviewContributions
              totalIssueContributions
              commitContributionsByRepository {
                repository { nameWithOwner isPrivate }
                contributions { totalCount }
              }
              pullRequestContributionsByRepository {
                repository { nameWithOwner isPrivate }
                contributions { totalCount }
              }
              pullRequestReviewContributionsByRepository {
                repository { nameWithOwner isPrivate }
                contributions { totalCount }
              }
              issueContributionsByRepository {
                repository { nameWithOwner isPrivate }
                contributions { totalCount }
              }
            }
          }
        }
        """

        variables = {
            "username": self.username,
            "from": from_dt,
            "to": to_dt,
        }

        try:
            response = self.session.post(
                graphql_url,
                json={"query": query, "variables": variables},
                timeout=30,
            )
        except requests.RequestException as exc:
            raise GitHubAPIError(f"GraphQL request failed: {exc}") from exc

        if response.status_code != 200:
            raise GitHubAPIError(
                f"GraphQL query HTTP {response.status_code}: {response.text}"
            )

        data = response.json()
        if "errors" in data and data["errors"]:
            raise GitHubAPIError(f"GraphQL query returned errors: {data['errors']}")

        user_data = data.get("data", {}).get("user")
        if not user_data:
            raise GitHubAPIError(
                f"User '{self.username}' not found in GitHub GraphQL response."
            )

        collection = user_data.get("contributionsCollection", {})

        repo_set = set()

        def _extract_repos(repo_list: List[Dict[str, Any]]) -> List[str]:
            names = []
            for item in repo_list:
                repo_info = item.get("repository", {})
                name = repo_info.get("nameWithOwner")
                if name:
                    names.append(name)
                    repo_set.add(name)
            return names

        commit_repos = _extract_repos(
            collection.get("commitContributionsByRepository", [])
        )
        pr_repos = _extract_repos(
            collection.get("pullRequestContributionsByRepository", [])
        )
        review_repos = _extract_repos(
            collection.get("pullRequestReviewContributionsByRepository", [])
        )
        issue_repos = _extract_repos(
            collection.get("issueContributionsByRepository", [])
        )

        return {
            "username": self.username,
            "start_date": from_dt,
            "end_date": to_dt,
            "total_commit_contributions": collection.get("totalCommitContributions", 0),
            "total_pull_request_contributions": collection.get(
                "totalPullRequestContributions", 0
            ),
            "total_pull_request_review_contributions": collection.get(
                "totalPullRequestReviewContributions", 0
            ),
            "total_issue_contributions": collection.get("totalIssueContributions", 0),
            "repositories": sorted(list(repo_set)),
            "commit_repositories": commit_repos,
            "pull_request_repositories": pr_repos,
            "review_repositories": review_repos,
            "issue_repositories": issue_repos,
        }

    def fetch_commits(
        self, repo_name: str, start_date: str, end_date: str
    ) -> List[Dict[str, Any]]:
        """Fetch commits authored by username in a repository within date range via REST Search API."""
        start_day = start_date[:10]
        end_day = end_date[:10]
        query = f"author:{self.username} repo:{repo_name} committer-date:{start_day}..{end_day}"

        url = f"{self.base_url}/search/commits"
        return self._paginate_search(url, query)

    def fetch_pull_requests(
        self, repo_name: str, start_date: str, end_date: str
    ) -> List[Dict[str, Any]]:
        """Fetch pull requests authored by username in a repository within date range via REST Search API."""
        start_day = start_date[:10]
        end_day = end_date[:10]
        query = f"author:{self.username} type:pr repo:{repo_name} created:{start_day}..{end_day}"

        url = f"{self.base_url}/search/issues"
        return self._paginate_search(url, query)

    def fetch_issues(
        self, repo_name: str, start_date: str, end_date: str
    ) -> List[Dict[str, Any]]:
        """Fetch issues opened by username in a repository within date range via REST Search API."""
        start_day = start_date[:10]
        end_day = end_date[:10]
        query = f"author:{self.username} type:issue repo:{repo_name} created:{start_day}..{end_day}"

        url = f"{self.base_url}/search/issues"
        return self._paginate_search(url, query)

    def _paginate_search(self, url: str, query: str) -> List[Dict[str, Any]]:
        """Helper to handle paginated REST Search API requests."""
        items: List[Dict[str, Any]] = []
        page = 1
        per_page = 100

        while True:
            try:
                response = self.session.get(
                    url,
                    params={"q": query, "per_page": per_page, "page": page},
                    timeout=30,
                )
            except requests.RequestException as exc:
                raise GitHubAPIError(f"Search request failed: {exc}") from exc

            if response.status_code != 200:
                raise GitHubAPIError(
                    f"Search API HTTP {response.status_code}: {response.text}"
                )

            data = response.json()
            page_items = data.get("items", [])
            items.extend(page_items)

            total_count = data.get("total_count", len(items))
            if len(page_items) < per_page or len(items) >= total_count:
                break

            page += 1

        return items
