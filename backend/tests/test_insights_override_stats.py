from app.services.insightsService.override_stats import MIN_SAMPLE, override_stats
from tests.insights_support import AI_SCORES, make_report

# Override statistics: pure maths, hand-worked numbers (no DB, no HTTP)

def overridden(report_id, requirements):
    """A saved override on the shared AI snapshot (requirements 7.0). requirements is a typed
    field stored on 0-100."""
    report = make_report(report_id, "c", "p", original=dict(AI_SCORES), override=True)
    return report.model_copy(update={"requirements_score": requirements})

def req(stats):
    return next(r for r in stats["by_dimension"] if r["dimension"] == "requirements")

def test_small_sample_below_five_saved_overrides():
    stats = override_stats([overridden(f"r{i}", 50.0) for i in range(MIN_SAMPLE - 1)])
    assert stats["small_sample"] is True and stats["min_sample"] == 5
    assert req(stats)["small_sample"] is True

def test_five_saved_overrides_clear_the_flag_and_the_maths_is_hand_checkable():
    stats = override_stats([overridden(f"r{i}", 50.0) for i in range(5)])  # 7.0 -> 5.0 each
    assert stats["small_sample"] is False and req(stats)["small_sample"] is False
    r = req(stats)
    assert (r["overrides_saved"], r["changed"], r["change_rate"]) == (5, 5, 1.0)
    assert (r["mean_adjustment"], r["mean_abs_adjustment"], r["direction"]) == (-2.0, 2.0, "lowered")

def test_unsaved_reports_do_not_count_toward_the_sample():
    reports = [overridden(f"r{i}", 50.0) for i in range(4)] + [
        make_report("n", "c", "p", original=dict(AI_SCORES)) for _ in range(10)]
    stats = override_stats(reports)
    assert stats["reports"] == 14 and stats["reports_overridden"] == 4
    assert stats["small_sample"] is True

def test_overall_flag_counts_saved_reports_even_when_a_dimension_was_never_assessed():
    # The AI did not assess cicd, so cicd has 0 comparable rows. Five saved reports are still a
    # big enough sample overall (regression: the flag once used the last dimension's count).
    original = {k: v for k, v in AI_SCORES.items() if k != "cicd"}
    reports = [
        make_report(f"r{i}", "c", "p", original=dict(original), override=True).model_copy(
            update={"requirements_score": 50.0}
        )
        for i in range(5)
    ]
    stats = override_stats(reports)
    cicd = next(r for r in stats["by_dimension"] if r["dimension"] == "cicd")
    assert cicd["overrides_saved"] == 0 and cicd["small_sample"] is True
    assert stats["reports_overridden"] == 5 and stats["small_sample"] is False

def test_empty_scope_does_not_divide_by_zero():
    stats = override_stats([])
    assert stats["override_rate"] is None and stats["small_sample"] is True