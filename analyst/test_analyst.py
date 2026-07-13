"""Tests for the Analyst."""
from common.contract import load_corpus
from analyst.analyst import profile, coverage_gaps


def test_finds_all_twelve_engagements():
    assert profile(load_corpus())["total_engagements"] == 12


def test_spots_the_engagement_with_no_outcome():
    """eng-12 is the only one with nothing measurable. Find it."""
    assert profile(load_corpus())["no_outcome"] == ["eng-12"]


def test_finds_the_coverage_gaps():
    """There are 15 domain x region combinations we cannot prove."""
    assert len(coverage_gaps(load_corpus())) == 15


# TODO(Elif): chart the gaps. A table nobody looks at is not an insight.
