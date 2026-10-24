"""Command-line driver for the model-comparison pipeline.

Three subcommands:

    python -m research.eval.cli list-datasets

    python -m research.eval.cli run \\
        --model sprintsight-qwen \\
        --dataset d1_fixtures \\
        --prompt-version v1.0 \\
        --seed 42 \\
        --repeats 1

    python -m research.eval.cli analyze \\
        --experiment sprintsight-model-comparison \\
        --out-dir research/eval_report \\
        --pairwise-metric overall_score

The `run` subcommand runs ONE condition at a time. To sweep 3 models you
run it three times — this keeps each MLflow run self-contained and makes
partial failures (e.g. one model crashes mid-sweep) easy to retry
without redoing the healthy runs.

See research/eval/README.md for the recommended invocation sequence.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from research.eval.datasets import list_datasets
from research.eval.runner import DEFAULT_EXPERIMENT, run_evaluation

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
log = logging.getLogger("research.eval.cli")


def _cmd_list_datasets(_: argparse.Namespace) -> int:
    for name, description in list_datasets():
        print(f"- {name}: {description}\n")
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    subset = args.subset.split(",") if args.subset else None
    run_id = run_evaluation(
        model=args.model,
        dataset_name=args.dataset,
        prompt_version=args.prompt_version,
        seed=args.seed,
        repeats=args.repeats,
        subset=subset,
        experiment=args.experiment,
        phase=args.phase,
        note=args.note,
    )
    print(f"MLflow run_id: {run_id}")
    return 0


def _cmd_analyze(args: argparse.Namespace) -> int:
    # Imported here so the CLI's --help doesn't need pandas/matplotlib.
    from research.eval.analysis import (
        DEFAULT_METRICS,
        comparison_table,
        consistency_summary,
        load_runs,
        pairwise_ci_table,
    )
    from research.eval.plots import save_all

    df = load_runs(args.experiment, filter_string=args.filter)
    if df.empty:
        print(f"No per-example rows found in experiment '{args.experiment}'.")
        return 1

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    table = comparison_table(df)
    table_path = out_dir / "comparison_table.csv"
    table.to_csv(table_path)
    print(f"Wrote {table_path}")

    for spec in DEFAULT_METRICS:
        pw = pairwise_ci_table(df, metric=spec.column)
        pw_path = out_dir / f"pairwise__{spec.column}.csv"
        pw.to_csv(pw_path, index=False)
        print(f"Wrote {pw_path}")

    cs = consistency_summary(df, metric="overall_score")
    if not cs.empty:
        cs_path = out_dir / "consistency__overall_score.csv"
        cs.to_csv(cs_path, index=False)
        print(f"Wrote {cs_path}")

    plot_paths = save_all(df, out_dir, metric_for_pairwise=args.pairwise_metric)
    for p in plot_paths:
        print(f"Wrote {p}")

    df.to_csv(out_dir / "raw_long_format.csv", index=False)
    print(f"Wrote {out_dir / 'raw_long_format.csv'}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list-datasets", help="List registered datasets.").set_defaults(func=_cmd_list_datasets)

    run_p = sub.add_parser("run", help="Run ONE (model × dataset × prompt × seed) condition.")
    run_p.add_argument("--model", required=True, help="Ollama tag, e.g. sprintsight-qwen")
    run_p.add_argument("--dataset", required=True, help="Dataset name from list-datasets")
    run_p.add_argument("--prompt-version", default="v1.0")
    run_p.add_argument("--seed", type=int, default=None,
                       help="Logged with the run; passing it does NOT currently reach Ollama "
                            "(evaluator.py would need an extra_body hook). Use for versioning only.")
    run_p.add_argument("--repeats", type=int, default=1,
                       help="How many times to run the whole dataset within this run "
                            "— for consistency measurement.")
    run_p.add_argument("--subset", default=None, help="Comma-separated example IDs; omit for full dataset.")
    run_p.add_argument("--experiment", default=DEFAULT_EXPERIMENT)
    run_p.add_argument("--phase", default="preliminary",
                       help='One of: "preliminary", "deep_eval", "final", "finetune_eval".')
    run_p.add_argument("--note", default="", help="Free-text note persisted as a param.")
    run_p.set_defaults(func=_cmd_run)

    ana_p = sub.add_parser("analyze", help="Collect runs, write tables/plots.")
    ana_p.add_argument("--experiment", default=DEFAULT_EXPERIMENT)
    ana_p.add_argument("--out-dir", default="research/eval_report")
    ana_p.add_argument("--filter", default="", help="mlflow.search_runs filter string.")
    ana_p.add_argument("--pairwise-metric", default="overall_score",
                       help="Metric for the headline pairwise plot. Switch to judge_quality_score "
                            "once judge scores are attached.")
    ana_p.set_defaults(func=_cmd_analyze)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
