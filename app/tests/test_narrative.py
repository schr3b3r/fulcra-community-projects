"""Tests for narrative generation module (Milestone 7)."""

import os
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock

import pytest

from fulcra_client import get_fulcra_client
from notability import NotabilitySignal
from rollup import ActivityRollup
from narrative import (
    SectionContext,
    _format_section_title,
    build_section_contexts,
    generate_journey_narrative,
)


def test_format_section_title() -> None:
    """Verify section title formatting for different period types."""
    assert _format_section_title("quarter", "2026-07-01", "2026-09-30") == "Q3 2026 (July 2026 – September 2026)"
    assert _format_section_title("month", "2026-08-01", "2026-08-31") == "August 2026"
    assert _format_section_title("year", "2026-01-01", "2026-12-31") == "Year 2026"
    assert _format_section_title("custom", "2026-07-15", "2026-07-20") == "2026-07-15 to 2026-07-20"


def test_build_section_contexts() -> None:
    """Verify building SectionContext blocks from rollups and notability signals."""
    username = "testuser"
    rollups = [
        ActivityRollup(
            period_type="quarter",
            start_date="2026-07-01",
            end_date="2026-09-30",
            username=username,
            summary="Q3 Quarter Summary",
            stats={"commit_count": 50, "total_activities": 60, "repos_touched": ["repo1"]},
            id="q3-rollup-id",
        ),
        ActivityRollup(
            period_type="week",
            start_date="2026-07-01",
            end_date="2026-07-07",
            username=username,
            summary="Week 1 Summary",
            stats={"commit_count": 20, "total_activities": 25, "repos_touched": ["repo1"]},
            id="w1-rollup-id",
        ),
        ActivityRollup(
            period_type="week",
            start_date="2026-08-01",
            end_date="2026-08-07",
            username=username,
            summary="Week 2 Quiet Summary",
            stats={"commit_count": 0, "total_activities": 0, "repos_touched": []},
            id="w2-rollup-id",
        ),
    ]

    signals = [
        NotabilitySignal(
            period_type="quarter",
            start_date="2026-07-01",
            end_date="2026-09-30",
            username=username,
            notability_score=0.8,
            flags=["high_volume"],
            explanation="Q3 high volume signal",
            source_rollup_id="q3-rollup-id",
        ),
        NotabilitySignal(
            period_type="week",
            start_date="2026-07-01",
            end_date="2026-07-07",
            username=username,
            notability_score=0.9,
            flags=["high_volume", "new_repo"],
            explanation="Week 1 new repo spike",
            source_rollup_id="w1-rollup-id",
        ),
        NotabilitySignal(
            period_type="week",
            start_date="2026-08-01",
            end_date="2026-08-07",
            username=username,
            notability_score=0.35,
            flags=["low_volume_gap"],
            explanation="Week 2 quiet gap",
            source_rollup_id="w2-rollup-id",
        ),
    ]

    sections = build_section_contexts(
        username=username,
        start_date="2026-07-01",
        end_date="2026-09-30",
        rollups=rollups,
        signals=signals,
    )

    assert len(sections) == 1
    sec = sections[0]
    assert sec.period_type == "quarter"
    assert sec.start_date == "2026-07-01"
    assert sec.end_date == "2026-09-30"
    assert sec.max_notability_score == 0.9
    assert "high_volume" in sec.all_flags
    assert "new_repo" in sec.all_flags
    assert "low_volume_gap" in sec.all_flags
    assert len(sec.child_rollups) == 2


def test_generate_journey_narrative_with_mock_llm() -> None:
    """Verify narrative markdown generation with a mock LLM callable."""
    username = "mockuser"
    start_date = "2026-07-01"
    end_date = "2026-09-30"

    mock_llm = MagicMock()
    mock_llm.return_value = "Mocked LLM narrative prose for engineering journey section."

    mock_client = MagicMock()

    # Return sample rollups and signals
    mock_rollups = [
        ActivityRollup(
            period_type="quarter",
            start_date=start_date,
            end_date=end_date,
            username=username,
            summary="Mock Quarter Summary",
            stats={"commit_count": 30, "total_activities": 35, "repos_touched": ["org/repo-a"]},
            id="mock-q-id",
        )
    ]
    mock_signals = [
        NotabilitySignal(
            period_type="quarter",
            start_date=start_date,
            end_date=end_date,
            username=username,
            notability_score=0.85,
            flags=["high_volume", "new_repo"],
            explanation="Mock high volume signal",
            source_rollup_id="mock-q-id",
        )
    ]

    # Mock read_rollups and read_notability_signals via monkeypatch in narrative module
    from unittest.mock import patch

    with patch("narrative.read_rollups", return_value=mock_rollups), patch(
        "narrative.read_notability_signals", return_value=mock_signals
    ):
        with TemporaryDirectory() as tmpdir:
            out_path = os.path.join(tmpdir, "mock_journey.md")
            markdown_content = generate_journey_narrative(
                username=username,
                start_date=start_date,
                end_date=end_date,
                client=mock_client,
                output_path=out_path,
                llm_callable=mock_llm,
            )

            assert os.path.exists(out_path)
            assert f"# Engineering Journey: {username}" in markdown_content
            assert "## Overview" in markdown_content
            assert "## Appendix: Provenance & Data References" in markdown_content
            assert "`high_volume, new_repo`" in markdown_content or "`high_volume`, `new_repo`" in markdown_content
            assert mock_llm.called


def test_real_account_journey_narrative_end_to_end() -> None:
    """Verify end-to-end journey narrative generation against real Fulcra data for schr3b3r."""
    client = get_fulcra_client()
    username = "schr3b3r"
    start_date = "2026-07-01"
    end_date = "2026-09-30"

    with TemporaryDirectory() as tmpdir:
        out_path = os.path.join(tmpdir, "real_journey_test.md")
        markdown_text = generate_journey_narrative(
            username=username,
            start_date=start_date,
            end_date=end_date,
            client=client,
            output_path=out_path,
        )

        assert os.path.exists(out_path)
        assert len(markdown_text) > 500
        assert f"# Engineering Journey: {username}" in markdown_text
        assert "## Overview" in markdown_text
        assert "## Appendix: Provenance & Data References" in markdown_text
        # Verify real repos are cited
        assert "community-skills" in markdown_text or "fulcra-community-projects" in markdown_text
        # Verify table header in provenance appendix
        assert "| Section / Period | Top-Level Rollup ID |" in markdown_text
