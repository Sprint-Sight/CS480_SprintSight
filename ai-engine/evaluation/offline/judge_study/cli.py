"""Command-line driver: python -m evaluation.offline.judge_study <command>, plus the selftest
invariants.
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Sequence
from pathlib import Path

import pandas as pd

from evaluation.offline.judge_study.artifacts import (
    classify_errors,
    judge_card,
    taxonomy_counts,
)
from evaluation.offline.judge_study.bias import pairwise_tournament
from evaluation.offline.judge_study.config import DEFAULT_JUDGE_MODEL, JUDGE_EXPERIMENT
from evaluation.offline.judge_study.frame import JudgeRecord, run_judge_evaluation
from evaluation.offline.judge_study.inference import model_comparison_report
from evaluation.offline.judge_study.integration import (
    attach_llm_grounding,
    export_judge_scores,
)
from evaluation.offline.judge_study.meta import calibration_table
from evaluation.offline.judge_study.records import (
    attach_human_annotations,
    install_stub_judge,
    load_records_from_run,
    synthetic_records,
    uninstall_stub_judge,
)
from evaluation.offline.judge_study.robustness import (
    consistency_summary,
    perturbation_summary,
    self_consistency_probe,
)
from evaluation.offline.judge_study.specs import JUDGE_METRIC_NAMES

log = logging.getLogger(__name__)


# -- CLI ----------------------------------------------------------------------

def _print_frame(title: str, frame: pd.DataFrame) -> None:
    print(f"\n=== {title} ===")
    if frame is None or frame.empty:
        print("(empty)")
        return
    with pd.option_context("display.width", 200, "display.max_columns", 50):
        print(frame.to_string())


def _records_for_cli(arguments: argparse.Namespace) -> list[JudgeRecord]:
    if arguments.run_id:
        return load_records_from_run(
            arguments.run_id,
            model=arguments.model,
            human_annotations=arguments.human_annotations,
        )
    records = synthetic_records()
    if arguments.human_annotations:
        attach_human_annotations(records, arguments.human_annotations)
    log.warning(
            "No --run-id given: using the SYNTHETIC validation dataset. These "
            "numbers validate the pipeline and must not appear in the report."
    )
    return records


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m evaluation.offline.judge_study",
        description="MLflow-native LLM-as-a-Judge evaluation for SprintSight.",
    )
    parser.add_argument(
        "command",
        choices=["evaluate", "calibrate", "pairwise", "consistency", "compare", "selftest"],
    )
    parser.add_argument("--run-id", help="MLflow run id from evaluation.offline.runner to judge")
    parser.add_argument("--model", help="Override the candidate model name for --run-id")
    parser.add_argument("--judge-model", default=DEFAULT_JUDGE_MODEL)
    parser.add_argument("--experiment", default=JUDGE_EXPERIMENT)
    parser.add_argument("--run-name")
    parser.add_argument("--human-annotations", help="CSV of human baseline 1-5 scores")
    parser.add_argument("--metrics", nargs="*", choices=list(JUDGE_METRIC_NAMES))
    parser.add_argument("--max-workers", type=int, default=1)
    parser.add_argument("--replicates", type=int, default=3)
    parser.add_argument("--phase", default="preliminary")
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Deterministic metrics only -- no judge calls",
    )
    parser.add_argument(
        "--cot-mode",
        choices=["two_stage", "inline"],
        default="two_stage",
        help=(
            "two_stage (default) runs an evidence audit before scoring, so the "
            "score is conditioned on committed reasoning; inline is one call "
            "per cell and cannot guarantee reasoning precedes the score"
        ),
    )
    parser.add_argument(
        "--stub-judge",
        action="store_true",
        help="Use the offline stub judge (synthetic scores, for testing only)",
    )
    parser.add_argument(
        "--llm-grounding",
        action="store_true",
        help=(
            "Also run evaluation/judges/citation_grounding.py and attach its "
            "per-claim grounding verdict as extra columns"
        ),
    )
    parser.add_argument(
        "--out-dir",
        default="research/judge_eval_report",
        help="Where to write CSV copies of the tables",
    )
    arguments = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )

    if arguments.command == "selftest":
        arguments.stub_judge = True
    if arguments.stub_judge:
        install_stub_judge()

    out_dir = Path(arguments.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        records = _records_for_cli(arguments)
        if not records:
            print("No records to evaluate.", file=sys.stderr)
            return 1

        if arguments.command in {"evaluate", "selftest"}:
            result, frame = run_judge_evaluation(
                records,
                judge_model=arguments.judge_model,
                experiment=arguments.experiment,
                run_name=arguments.run_name,
                only_metrics=arguments.metrics,
                include_llm_metrics=not arguments.no_llm,
                cot_mode=arguments.cot_mode,
                max_workers=arguments.max_workers,
                phase="selftest" if arguments.command == "selftest" else arguments.phase,
            )
            if arguments.llm_grounding:
                # Three-way cross-check on the same citations: deterministic
                # anchors, deterministic string grounding, semantic grounding.
                frame = attach_llm_grounding(
                    frame, records, judge_model=arguments.judge_model
                )
            print("\nAggregate metrics:")
            for name, value in sorted(result.metrics.items()):
                print(f"  {name:<52} {value}")

            # Named explicitly, not by a "judge_" prefix match: summarise_example
            # contributes judge_quality_score / judge_rationale placeholder
            # columns, and a prefix match would print those empty columns as
            # though the judge had failed to score anything.
            judge_columns = [
                column
                for column in [f"judge_{name}" for name in JUDGE_METRIC_NAMES]
                + ["judge_composite"]
                if column in frame.columns
            ]
            if judge_columns:
                _print_frame(
                    "Judge scores by model",
                    frame.groupby("model")[judge_columns]
                    .apply(lambda group: group.apply(pd.to_numeric, errors="coerce").mean())
                    .round(2),
                )
            calibration = calibration_table(frame)
            _print_frame(
                "Judge calibration vs human baseline",
                calibration[
                    ["n", "quadratic_kappa", "spearman_rho", "icc_2_1",
                     "mean_signed_error", "interpretation", "warnings"]
                ].round(3),
            )
            comparison = model_comparison_report(frame)
            if not comparison.empty:
                columns = [
                    column
                    for column in ("metric", "pair", "n", "mean_diff", "ci_low",
                                   "ci_high", "cliffs_delta", "effect_magnitude",
                                   "wilcoxon_p", "p_adjusted", "min_attainable_p",
                                   "significant")
                    if column in comparison.columns
                ]
                _print_frame("Paired model comparisons (Holm-corrected)",
                             comparison[columns].round(4))
                comparison.to_csv(out_dir / "model_comparisons.csv", index=False)
            frame.to_csv(out_dir / "judge_eval_rows.csv", index=False)
            calibration.to_csv(out_dir / "judge_calibration.csv")
            if "judge_composite" in frame.columns:
                # Closes the loop with evaluation/offline/attach_judge_scores.py,
                # which has been waiting for this file since the harness was
                # written. See export_judge_scores for the column contract.
                exported = export_judge_scores(
                    frame,
                    out_dir / "judge_scores_for_attach.csv",
                    run_id=arguments.run_id,
                )
                print(
                    "To merge these into the model-comparison run:"
                    "\n  python -m "
                    "evaluation.offline.attach_judge_scores --judge-file "
                    f"{exported} --run-id <runner run_id>"
                )
            _print_frame("Error taxonomy", taxonomy_counts(classify_errors(frame)))

            if arguments.command == "selftest":
                return _assert_selftest_invariants(frame)
            return 0

        if arguments.command == "calibrate":
            _, frame = run_judge_evaluation(
                records,
                judge_model=arguments.judge_model,
                experiment=arguments.experiment,
                only_metrics=arguments.metrics,
                cot_mode=arguments.cot_mode,
                max_workers=arguments.max_workers,
                phase=arguments.phase,
            )
            calibration = calibration_table(frame)
            _print_frame("Judge calibration", calibration.round(3))
            calibration.to_csv(out_dir / "judge_calibration.csv")
            print("\n" + judge_card(
                judge_model=arguments.judge_model, frame=frame, calibration=calibration
            ))
            return 0

        if arguments.command == "pairwise":
            rows, matrix, diagnostics = pairwise_tournament(
                records, judge_model=arguments.judge_model
            )
            _print_frame("Pairwise comparisons", rows)
            _print_frame("Win matrix (consistent verdicts only)", matrix)
            print("\nDiagnostics:")
            for name, value in diagnostics.items():
                print(f"  {name:<28} {value}")
            rows.to_csv(out_dir / "pairwise_comparisons.csv", index=False)
            return 0

        if arguments.command == "consistency":
            probe = self_consistency_probe(
                records,
                judge_model=arguments.judge_model,
                replicates=arguments.replicates,
                metrics=tuple(arguments.metrics or ("Code_Faithfulness",)),
            )
            _print_frame("Self-consistency", consistency_summary(probe).round(3))
            _print_frame("Perturbation sensitivity", perturbation_summary(probe).round(3))
            probe.to_csv(out_dir / "consistency_probe.csv", index=False)
            return 0

        if arguments.command == "compare":
            _, frame = run_judge_evaluation(
                records,
                judge_model=arguments.judge_model,
                experiment=arguments.experiment,
                include_llm_metrics=not arguments.no_llm,
                cot_mode=arguments.cot_mode,
                max_workers=arguments.max_workers,
                phase=arguments.phase,
            )
            comparison = model_comparison_report(frame)
            _print_frame("Paired model comparisons", comparison.round(4))
            comparison.to_csv(out_dir / "model_comparisons.csv", index=False)
            return 0

        return 1
    finally:
        if arguments.stub_judge:
            uninstall_stub_judge()


def _assert_selftest_invariants(frame: pd.DataFrame) -> int:
    """Check the framework reproduces known-answer properties of the synthetic set.

    These are the assertions a marker can run. They test the PIPELINE, not
    the models: the synthetic degraded candidate is worse by construction, so
    any failure here is a wiring bug in this package.
    """
    failures: list[str] = []

    for metric in ("Code_Faithfulness", "Evidence_Specificity"):
        column = f"judge_{metric}"
        if column not in frame.columns:
            failures.append(f"{column} missing: judge scores were not merged")
            continue
        means = frame.groupby("model")[column].apply(
            lambda series: pd.to_numeric(series, errors="coerce").mean()
        )
        if {"synthetic-faithful", "synthetic-degraded"}.issubset(means.index) and not (
            means["synthetic-faithful"] > means["synthetic-degraded"]
        ):
            failures.append(
                f"{column}: faithful ({means['synthetic-faithful']:.2f}) did not "
                f"beat degraded ({means['synthetic-degraded']:.2f})"
            )

    if "citation_anchor_rate" in frame.columns:
        degraded = frame[frame["model"] == "synthetic-degraded"]["citation_anchor_rate"]
        if degraded.notna().any():
            failures.append(
                "citation_anchor_rate should be None for the degraded candidate, "
                "whose citations were all stripped"
            )

    # The inherited columns must be present, or the summarise_example layer
    # silently stopped being wired in and the two pipelines have diverged.
    for inherited in ("groundedness_rate", "format_valid", "dimension_completion_rate"):
        if inherited not in frame.columns:
            failures.append(
                f"{inherited} missing: evaluation.offline.metrics.summarise_example "
                "is no longer layered into build_eval_frame"
            )

    if "lint_warning_count" in frame.columns:
        by_model = frame.groupby("model")["lint_warning_count"].mean()
        if {"synthetic-faithful", "synthetic-degraded"}.issubset(by_model.index) and not (
            by_model["synthetic-degraded"] > by_model["synthetic-faithful"]
        ):
            failures.append("lint did not flag the degraded candidate more often")

    if "grade_signed_error_overall" in frame.columns:
        degraded_bias = frame[frame["model"] == "synthetic-degraded"][
            "grade_signed_error_overall"
        ].mean()
        if not degraded_bias > 0:
            failures.append(
                f"degraded candidate was built 2 points inflated but signed error "
                f"is {degraded_bias}"
            )

    print("\n=== selftest ===")
    if failures:
        for failure in failures:
            print(f"  FAIL  {failure}")
        return 1
    print("  PASS  all pipeline invariants hold on the synthetic known-answer set")
    return 0
