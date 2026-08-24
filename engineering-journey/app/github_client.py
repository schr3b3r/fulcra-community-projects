"""GitHub API client for Engineering Journey backfill ingestion.

Communicates directly with GitHub REST and GraphQL APIs using the `requests`
library. Accepts runtime configuration (token, username) via constructor
arguments or environment variables (`GITHUB_TOKEN`, `GITHUB_USERNAME`).
"""

from datetime import datetime, timedelta, timezone
import os
import time
from typing import Any, Dict, List, Optional, Union
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

    def enumerate_repositories(
        self,
        start_date: Optional[Union[datetime, str]] = None,
        end_date: Optional[Union[datetime, str]] = None,
    ) -> List[str]:
        """Enumerate all repositories contributed to across a date window (e.g. 3 years).

        Queries GraphQL contributionsCollection in <= 1-year windows to comply with
        GitHub API constraints.

        Args:
            start_date: Start of query window (defaults to 3 years ago).
            end_date: End of query window (defaults to current time in UTC).

        Returns:
            Sorted list of unique repository names ('owner/repo').
        """
        now = datetime.now(timezone.utc)
        if end_date is None:
            end_dt = now
        elif isinstance(end_date, str):
            end_dt = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
            if end_dt.tzinfo is None:
                end_dt = end_dt.replace(tzinfo=timezone.utc)
        else:
            end_dt = end_date

        if start_date is None:
            start_dt = end_dt - timedelta(days=365 * 3)
        elif isinstance(start_date, str):
            start_dt = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
            if start_dt.tzinfo is None:
                start_dt = start_dt.replace(tzinfo=timezone.utc)
        else:
            start_dt = start_date

        repo_set = set()
        curr = start_dt

        while curr < end_dt:
            window_end = min(curr + timedelta(days=365), end_dt)
            start_str = curr.strftime("%Y-%m-%d")
            end_str = window_end.strftime("%Y-%m-%d")

            collection = self.get_contributions_collection(start_str, end_str)
            repo_set.update(collection.get("repositories", []))

            curr = window_end + timedelta(days=1)

        return sorted(list(repo_set))

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

    def _paginate_search(
        self, url: str, query: str, max_rate_limit_retries: int = 5
    ) -> List[Dict[str, Any]]:
        """Helper to handle paginated REST Search API requests.

        GitHub's Search API has a stricter rate limit (30 req/min for
        authenticated requests) than the core REST API -- empirically hit
        during Milestone 3's real multi-repo/multi-period backfill (3
        search calls per work item, tens of items in quick succession
        exceeds this easily). On a 403 that looks like a rate-limit
        response, sleep until the limit resets (per `Retry-After` or
        `X-RateLimit-Reset`, whichever is present) and retry, up to
        `max_rate_limit_retries` times, rather than failing the whole
        backfill on a transient/expected condition.
        """
        items: List[Dict[str, Any]] = []
        page = 1
        per_page = 100
        rate_limit_retries = 0

        while True:
            try:
                response = self.session.get(
                    url,
                    params={"q": query, "per_page": per_page, "page": page},
                    timeout=30,
                )
            except requests.RequestException as exc:
                raise GitHubAPIError(f"Search request failed: {exc}") from exc

            if response.status_code == 403 and self._is_rate_limit_response(response):
                if rate_limit_retries >= max_rate_limit_retries:
                    raise GitHubAPIError(
                        f"Search API rate limit exceeded after "
                        f"{max_rate_limit_retries} retries: {response.text}"
                    )
                wait_seconds = self._rate_limit_wait_seconds(response)
                rate_limit_retries += 1
                time.sleep(wait_seconds)
                continue

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

    @staticmethod
    def _is_rate_limit_response(response: "requests.Response") -> bool:
        """Detect a GitHub rate-limit 403 (vs. other 403 causes like a
        private/missing repo) by inspecting headers/body rather than
        assuming every 403 is a rate limit."""
        if response.headers.get("X-RateLimit-Remaining") == "0":
            return True
        try:
            message = response.json().get("message", "")
        except Exception:
            message = response.text
        return "rate limit" in message.lower()

    @staticmethod
    def _rate_limit_wait_seconds(response: "requests.Response") -> float:
        """Compute how long to sleep before retrying a rate-limited request."""
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                return max(float(retry_after), 1.0) + 1.0
            except ValueError:
                pass

        reset_header = response.headers.get("X-RateLimit-Reset")
        if reset_header:
            try:
                reset_epoch = float(reset_header)
                return max(reset_epoch - time.time(), 1.0) + 1.0
            except ValueError:
                pass

        # No usable header: GitHub's search rate limit window is 60s.
        return 60.0
