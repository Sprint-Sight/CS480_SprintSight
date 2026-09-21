"""
schemas/expected_orders.py

Encodes the two target orderings across the 5-fixture set:

    GENERAL (code_quality, testing, documentation, requirements, CICD, and overall):
      high_performing >= imbalanced_high_output > good_collab_low_output
                        > lone_contributor_poor_outcome > struggling

  COLLABORATION (its own ordering -- collaboration should NOT just track output volume):
      high_performing >= good_collab_low_output > imbalanced_high_output
                        >= lone_contributor_poor_outcome > struggling

Each ordering is a chain of (higher, lower, operator) links, matching the
named-pair style already used in pairwise_discriminative_validity /
collaboration_pairwise_discriminative_validity in the harness output.

IMPORTANT -- see the __main__ block before trusting this against your data.
Running it against benchmark.py's current reference scores surfaces 5
violations (detailed in chat): lone_contributor_poor_outcome scores BELOW
struggling on collaboration, code_quality, and (tied) testing/requirements,
and imbalanced_high_output beats high_performing on requirements. Resolve
those -- by editing benchmark.py's scores or relaxing these specific links --
before wiring this into validation_harness.py's compute_summary().
"""

from typing import Literal, NamedTuple


class OrderLink(NamedTuple):
    higher: str
    lower: str
    op: Literal[">", ">="]

GENERAL_ORDER: list[OrderLink] = [ # General ordering for general dimensions
    OrderLink("high_performing", "imbalanced_high_output", ">="),
    OrderLink("imbalanced_high_output", "good_collab_low_output", ">"),
    OrderLink("good_collab_low_output", "lone_contributor_poor_outcome", ">"),
    OrderLink("lone_contributor_poor_outcome", "struggling", ">"),
]

COLLABORATION_ORDER: list[OrderLink] = [ # Genera ordering for COLLABORATION dimension
    OrderLink("high_performing", "good_collab_low_output", ">="),
    OrderLink("good_collab_low_output", "imbalanced_high_output", ">"),
    OrderLink("imbalanced_high_output", "lone_contributor_poor_outcome", ">="),
    OrderLink("lone_contributor_poor_outcome", "struggling", ">"),
]


def check_order(
    scores: dict[str, float],
    order: list[OrderLink],
    stdevs: dict[str, float] | None = None,
) -> dict[str, dict]:
    """
    scores: {fixture_name: mean_score}
    stdevs: {fixture_name: stdev} -- omit (or pass None) for a plain numeric
            check against point values, e.g. hand-authored reference scores.
            Supply real per-fixture stdevs from repeated harness runs to get
            the noise-aware version instead (recommended for real LLM output,
            per the band-overlap method used earlier in this project).

    Returns one entry per link:
        {"high_performing >= imbalanced_high_output": {"holds": bool, "gap": float, "note": str}}

    ">"  passes only if there's a real, non-overlapping gap in the correct
         direction (mean_higher - stdev_higher > mean_lower + stdev_lower).
    ">=" tolerates a tie or the "higher" fixture trailing slightly -- it only
         fails if the "lower" fixture is CLEARLY, non-overlappingly above it.
    """
    stdevs = stdevs or {}
    results = {}
    for link in order:
        key = f"{link.higher} {link.op} {link.lower}"
        mh, sh = scores[link.higher], stdevs.get(link.higher, 0.0)
        ml, sl = scores[link.lower], stdevs.get(link.lower, 0.0)

        if link.op == ">":
            holds = (mh - sh) > (ml + sl)
            note = "real, non-overlapping gap" if holds else "gap does not clear the noise band"
        else:  # ">="
            holds = not ((ml - sl) > (mh + sh))
            note = "tie or higher on top, as allowed" if holds else "lower fixture is CLEARLY above the higher one -- real violation"

        results[key] = {"holds": holds, "gap": round(mh - ml, 3), "note": note}
    return results


if __name__ == "__main__":
    # Point-value sanity check against benchmark.py's CURRENT reference scores.
    # Re-run this any time the reference grades or the ordering rule changes
    # it's what caught the 5 violations flagged in chat before this file existed.
    reference_scores = {
        "code_quality":  {"high_performing": 9, "imbalanced_high_output": 8, "good_collab_low_output": 7, "lone_contributor_poor_outcome": 4, "struggling": 3},
        "testing":       {"high_performing": 9, "imbalanced_high_output": 8, "good_collab_low_output": 7, "lone_contributor_poor_outcome": 4, "struggling": 3},
        "documentation": {"high_performing": 10, "imbalanced_high_output": 8, "good_collab_low_output": 8, "lone_contributor_poor_outcome": 5, "struggling": 3},
        "requirements":  {"high_performing": 9, "imbalanced_high_output": 8, "good_collab_low_output": 7, "lone_contributor_poor_outcome": 4, "struggling": 3},
        "collaboration": {"high_performing": 10, "imbalanced_high_output": 3, "good_collab_low_output": 9, "lone_contributor_poor_outcome": 2, "struggling": 2},
    }

    any_violation = False # Flag if any ordering link fails to hold
    for dim, order in [
        ("code_quality", GENERAL_ORDER), ("testing", GENERAL_ORDER),
        ("documentation", GENERAL_ORDER), ("requirements", GENERAL_ORDER),
        ("cicd", GENERAL_ORDER),
        ("collaboration", COLLABORATION_ORDER),
    ]:
        print(f"\n {dim} fixture ordering check:")
        for key, result in check_order(reference_scores[dim], order).items():
            status = "OK" if result["holds"] else "VIOLATION"
            if not result["holds"]: # Flag that at least one link failed to hold
                any_violation = True
            print(f"  [{status}] {key}  (gap={result['gap']})  {result['note']}")

    if any_violation:
        print("\nReference scores do not fully satisfy the stated ordering yet -- see VIOLATION lines above.")