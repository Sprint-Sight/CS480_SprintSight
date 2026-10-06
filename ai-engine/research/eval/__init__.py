"""SprintSight model-comparison evaluation pipeline.

Preliminary analysis layer that reuses `services.evaluator.evaluate_sprint`
and the existing bundle fixtures/registries. 
This package exposes a `judge_quality_score` slot in every per-example row 
that stays None until judge scores are attached (see attach_judge_scores.py).

Entry point: python -m research.eval.cli --help
"""

__version__ = "0.1.0"
