"""Tests for the unified CLI entrypoint engineering_journey.py."""

from unittest.mock import ANY, MagicMock, patch
import pytest

from engineering_journey import (
    _compute_date_range,
    run_backfill,
    run_generate,
)


def test_compute_date_range_explicit() -> None:
    """Test date range calculation when explicit start and end dates are provided."""
    s_date, e_date = _compute_date_range("2024-01-01", "2024-12-31", 3.0)
    assert s_date == "2024-01-01"
    assert e_date == "2024-12-31"


def test_compute_date_range_with_years() -> None:
    """Test start date computation when years argument is passed."""
    s_date, e_date = _compute_date_range(None, "2026-08-01", 3.0)
    assert e_date == "2026-08-01"
    assert s_date == "2023-08-02"


@patch("engineering_journey.get_fulcra_client")
@patch("engineering_journey.GitHubClient")
@patch("engineering_journey.backfill_full_github_activity")
@patch("engineering_journey.generate_day_week_rollups")
@patch("engineering_journey.generate_month_rollups")
@patch("engineering_journey.generate_layer_rollups")
@patch("engineering_journey.generate_notability_signals")
def test_run_backfill_orchestration_flow(
    mock_gen_signals: MagicMock,
    mock_gen_layer: MagicMock,
    mock_gen_month: MagicMock,
    mock_gen_day_week: MagicMock,
    mock_backfill_raw: MagicMock,
    mock_gh_cls: MagicMock,
    mock_get_client: MagicMock,
) -> None:
    """Test that run_backfill orchestrates raw backfill, rollups, and signals in order,
    splitting the range at the recent-90-days boundary before calling the day/week vs.
    month rollup functions (Interview decision #1's decaying-granularity boundary --
    see RECENT_WINDOW_DAYS in engineering_journey.py)."""
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client

    mock_backfill_raw.return_value = {"status": "completed", "completed_items_count": 10}
    mock_gen_day_week.return_value = {"status": "completed", "rollups_generated": 5}
    mock_gen_month.return_value = {"status": "completed", "rollups_generated": 3}
    mock_gen_layer.return_value = {"status": "completed", "rollups_generated": 2}
    mock_gen_signals.return_value = {"status": "completed", "signals_generated": 4}

    # A range spanning well over 90 days (~5 months) so both the recent
    # day/week window and the older month window are non-empty -- this is
    # the case that actually exercises the split, unlike a short range.
    res = run_backfill(
        username="testuser",
        token="testtoken",
        start_date="2026-01-01",
        end_date="2026-06-01",
        repo_names=["owner/repo1"],
        client=mock_client,
    )

    # 1. Verify GitHubClient initialized with token & username
    mock_gh_cls.assert_called_once_with(token="testtoken", username="testuser")

    # 2. Verify raw activity backfill called across the FULL range (raw
    # ingestion has its own internal decaying-granularity chunking; it is
    # not split here).
    mock_backfill_raw.assert_called_once_with(
        gh_client=mock_gh_cls.return_value,
        start_date="2026-01-01",
        end_date="2026-06-01",
        repo_names=["owner/repo1"],
        client=mock_client,
        progress_callback=ANY,
    )

    # 3. Verify day/week rollups called ONLY for the recent 90-day window
    # (ending 2026-06-01), NOT the full 2026-01-01 to 2026-06-01 range --
    # generate_day_week_rollups has no internal 90-day cutoff of its own,
    # so passing it the full multi-year range would generate one daily
    # rollup (and LLM call) per day across the entire backfill window.
    mock_gen_day_week.assert_called_once_with(
        username="testuser",
        start_date="2026-03-03",
        end_date="2026-06-01",
        client=mock_client,
        progress_callback=ANY,
    )
    # 4. Verify month rollups called ONLY for the older window (up to the
    # day before the recent window starts).
    mock_gen_month.assert_called_once_with(
        username="testuser",
        start_date="2026-01-01",
        end_date="2026-03-02",
        client=mock_client,
        progress_callback=ANY,
    )

    # 5. Verify layer rollups called for quarter and year, across the FULL range
    assert mock_gen_layer.call_count == 2
    quarter_call = mock_gen_layer.call_args_list[0]
    year_call = mock_gen_layer.call_args_list[1]
    assert quarter_call.kwargs["period_type"] == "quarter"
    assert year_call.kwargs["period_type"] == "year"

    # 6. Verify notability signals generated for day, week, month, quarter, year
    assert mock_gen_signals.call_count == 5
    signal_period_types = [call.kwargs["period_type"] for call in mock_gen_signals.call_args_list]
    assert signal_period_types == ["day", "week", "month", "quarter", "year"]

    assert res["username"] == "testuser"
    assert res["start_date"] == "2026-01-01"
    assert res["end_date"] == "2026-06-01"


def test_run_backfill_short_range_skips_month_rollups() -> None:
    """A range entirely within the recent 90-day window should skip month
    rollups (nothing older than the cutoff exists), not call
    generate_month_rollups with an inverted/empty range."""
    from datetime import datetime, timedelta, timezone

    with patch("engineering_journey.get_fulcra_client") as mock_get_client, \
         patch("engineering_journey.GitHubClient") as mock_gh_cls, \
         patch("engineering_journey.backfill_full_github_activity") as mock_backfill_raw, \
         patch("engineering_journey.generate_day_week_rollups") as mock_gen_day_week, \
         patch("engineering_journey.generate_month_rollups") as mock_gen_month, \
         patch("engineering_journey.generate_layer_rollups") as mock_gen_layer, \
         patch("engineering_journey.generate_notability_signals") as mock_gen_signals:

        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_backfill_raw.return_value = {"status": "completed", "completed_items_count": 1}
        mock_gen_day_week.return_value = {"status": "completed", "rollups_generated": 1}
        mock_gen_layer.return_value = {"status": "completed", "rollups_generated": 1}
        mock_gen_signals.return_value = {"status": "completed", "signals_generated": 1}

        end_dt = datetime.now(timezone.utc)
        start_dt = end_dt - timedelta(days=10)

        run_backfill(
            username="testuser",
            token="testtoken",
            start_date=start_dt.strftime("%Y-%m-%d"),
            end_date=end_dt.strftime("%Y-%m-%d"),
            client=mock_client,
        )

        mock_gen_day_week.assert_called_once()
        mock_gen_month.assert_not_called()


@patch("engineering_journey.get_fulcra_client")
@patch("engineering_journey.generate_journey_narrative")
def test_run_generate_orchestration_flow(
    mock_generate_narrative: MagicMock,
    mock_get_client: MagicMock,
) -> None:
    """Test that run_generate invokes generate_journey_narrative correctly."""
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    mock_generate_narrative.return_value = "# Engineering Journey\nGenerated Content"

    content = run_generate(
        username="testuser",
        start_date="2026-01-01",
        end_date="2026-06-01",
        output_path="test_journey.md",
        client=mock_client,
    )

    mock_generate_narrative.assert_called_once_with(
        username="testuser",
        start_date="2026-01-01",
        end_date="2026-06-01",
        client=mock_client,
        output_path="test_journey.md",
        progress_callback=ANY,
    )

    assert content == "# Engineering Journey\nGenerated Content"
