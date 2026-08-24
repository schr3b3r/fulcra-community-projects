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


def _parse_datetime(
    dt_val: Union[datetime, str], is_end_of_day: bool = False
) -> datetime:
    """Parse string or datetime into a UTC timezone-aware datetime object."""
    if isinstance(dt_val, str):
        dt_str = dt_val.strip()
        if "T" not in dt_str:
            if is_end_of_day:
                dt_str = f"{dt_str}T23:59:59Z"
            else:
                dt_str = f"{dt_str}T00:00:00Z"
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    else:
        dt = dt_val

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


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

    def list_accessible_repositories(
        self,
        pushed_after: Optional[Union[datetime, str]] = None,
        pushed_before: Optional[Union[datetime, str]] = None,
    ) -> List[str]:
        """List repositories accessible to the user via GET /user/repos.

        Args:
            pushed_after: Optional start of pushed_at window.
            pushed_before: Optional end of pushed_at window.

        Returns:
            Sorted list of unique repository full names ('owner/repo').
        """
        after_dt = (
            _parse_datetime(pushed_after, is_end_of_day=False)
            if pushed_after is not None
            else None
        )
        before_dt = (
            _parse_datetime(pushed_before, is_end_of_day=True)
            if pushed_before is not None
            else None
        )

        repo_set: set[str] = set()
        page = 1
        per_page = 100

        while True:
            try:
                response = self.session.get(
                    f"{self.base_url}/user/repos",
                    params={
                        "affiliation": "owner,collaborator,organization_member",
                        "per_page": per_page,
                        "page": page,
                    },
                    timeout=30,
                )
            except requests.RequestException as exc:
                raise GitHubAPIError(f"User repos request failed: {exc}") from exc

            if response.status_code != 200:
                raise GitHubAPIError(
                    f"User repos API HTTP {response.status_code}: {response.text}"
                )

            repos_page = response.json()
            if not isinstance(repos_page, list):
                raise GitHubAPIError(
                    f"User repos API expected list, got {type(repos_page).__name__}"
                )

            for item in repos_page:
                full_name = item.get("full_name")
                if not full_name:
                    continue

                pushed_at_str = item.get("pushed_at")
                if after_dt or before_dt:
                    if not pushed_at_str:
                        continue
                    pushed_dt = _parse_datetime(pushed_at_str, is_end_of_day=False)
                    if after_dt and pushed_dt < after_dt:
                        continue
                    if before_dt and pushed_dt > before_dt:
                        continue

                repo_set.add(full_name)

            if len(repos_page) < per_page:
                break
            page += 1

        return sorted(list(repo_set))

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
        """Enumerate all repositories contributed to or accessible across a date window (e.g. 3 years).

        Queries GraphQL contributionsCollection in <= 1-year windows and unions
        with GET /user/repos listing (filtered to repos with pushed_at in window)
        to ensure private repositories missed by contributionsCollection are included.

        Args:
            start_date: Start of query window (defaults to 3 years ago).
            end_date: End of query window (defaults to current time in UTC).

        Returns:
            Sorted list of unique repository names ('owner/repo').
        """
        now = datetime.now(timezone.utc)
        if end_date is None:
            end_dt = now
        else:
            end_dt = _parse_datetime(end_date, is_end_of_day=True)

        if start_date is None:
            start_dt = end_dt - timedelta(days=365 * 3)
        else:
            start_dt = _parse_datetime(start_date, is_end_of_day=False)

        repo_set = set()

        # 1. Listing-based discovery for accessible repos (includes private repos)
        accessible_repos = self.list_accessible_repositories(
            pushed_after=start_dt,
            pushed_before=end_dt,
        )
        repo_set.update(accessible_repos)

        # 2. GraphQL contributionsCollection discovery across window chunks
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
