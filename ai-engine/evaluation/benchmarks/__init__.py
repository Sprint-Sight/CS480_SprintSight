"""Benchmark reference data: sprint bundles with hand-written gold assessments.

    synthetic_v1     five synthetic teams + gold. Offline only: the d1_fixtures dataset, the judge
                     study and the validation harness.
    synthetic_v2     five synthetic teams + gold. Online judge and research/trials/run_fixture_trial.py.
    cs203            two real CS203 sprints + gold. Online judge, trials and the judge canary.
    expected_orders  the ranking the synthetic_v1 teams should get.
    data/            the JSON the modules above load, plus data/real_sprints/ (the d_real_sprints
                     dataset, written locally by backend/scripts/export_eval_bundles.py and not
                     committed: it holds student data).

synthetic_v1 and synthetic_v2 reuse the same team_ids (Team_Alpha, ...) for different bundles and
gold. `online_gold` and `online_bundles` cover synthetic_v2 and cs203 only: the teams the
production judge can compare against gold.

Nothing is loaded until a submodule or one of these functions is used.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from schemas.artifact_bundle import ArtifactBundle
    from schemas.sprint_assessment import SprintAssessment

DATA_DIR = Path(__file__).resolve().parent / "data"


def online_gold() -> dict[str, SprintAssessment]:
    """Gold assessments the online judge compares against, keyed by lower-cased team_id."""
    from evaluation.benchmarks.cs203 import CS203_GOLD
    from evaluation.benchmarks.synthetic_v2 import FIXTURES_GOLD

    return {**CS203_GOLD, **{g.team_id.lower(): g for g in FIXTURES_GOLD.values()}}


def online_bundles() -> dict[str, ArtifactBundle]:
    """Bundles the online judge falls back to when a trace does not carry its own, keyed by team_id."""
    from evaluation.benchmarks.cs203 import CS203G6_BUNDLE, CS203JY_BUNDLE
    from evaluation.benchmarks.synthetic_v2 import FIXTURES_TEAMS

    return {b.team_id: b for b in (CS203G6_BUNDLE, CS203JY_BUNDLE, *FIXTURES_TEAMS)}
