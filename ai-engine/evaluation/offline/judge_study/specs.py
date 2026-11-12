"""The rubric layer (Parts 1-2): chain-of-thought protocol, anchored 1-5 bands, few-shot
exemplars, and the five native MLflow GenAI metrics built from them.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from mlflow.metrics.genai import EvaluationExample, make_genai_metric
from mlflow.metrics.genai.prompts.v1 import EvaluationModel

from evaluation.offline.judge_study.config import _assert_brace_free, judge_parameters

# Requested reasoning format for the SCORING call. We ask for a JSON object
# with the reasoning keys first, which MLflow's parser accepts because it
# tries json.loads before its score-first regex.
#
# Measured caveat: this request is NOT reliably honoured. MLflow appends its
# own "score, then justification" instruction after this rubric, and a local
# 3B-8B judge follows the closing instruction -- observed output was
# {"score": 5, "justification": ...}, i.e. the number first. In-completion
# CoT is therefore requested but never relied upon; the real guarantee comes
# from the two-stage reasoning pass below (ANALYSIS_PROTOCOL), whose output
# is injected as grading context so the score is conditioned on reasoning
# that was already committed to text.
COT_PROTOCOL = _assert_brace_free(
    """
Reasoning protocol -- follow it exactly:

Reply with a single JSON object and nothing else. Emit its keys in EXACTLY
this order, so that all of your reasoning is written down before you commit
to a number:

  1. key "evidence_scan" -- an array of 2 to 5 short strings. Each string
     names one concrete item you actually checked and what you found: a
     commit SHA, a Jira ticket key, a filename, a peer-review comment, or a
     numeric claim you either verified or could not verify.
  2. key "anchor_check" -- one string. Walk the numbered rubric tests below
     in order and state for each whether it PASSED or FAILED, and on what
     evidence. Use the form T1 PASSED because ..., T2 FAILED because ...
  3. key "justification" -- two to four sentences explaining which score band
     the evidence places this output in, referring to the anchors by their
     wording rather than by number alone.
  4. key "score" -- a single integer from 1 to 5, and nothing else.

Hard rules:
- Never write the score key before the three reasoning keys.
- Never wrap the JSON in code fences and never add prose outside the object.
- Judge only the output in front of you. Do not reward length, confidence or
  polished writing: a short output citing real evidence outranks a long one
  that does not.
- If the output is empty or unparseable, score 1 and say so.
""",
    "COT_PROTOCOL",
)


def _render_anchors(anchors: Mapping[int, str]) -> str:
    """Render 1-5 score anchors as brace-free prose, highest band first."""
    lines = [
        ("Score anchors -- choose the single highest band whose description is "
        "fully true of the output:")
    ]
    for level in sorted(anchors, reverse=True):
        lines.append(f"- Score {level}: {' '.join(anchors[level].split())}")
    return "\n".join(lines)


def _render_tests(tests: Sequence[str]) -> str:
    lines = ["Rubric tests -- answer every one of these in anchor_check:"]
    for index, test in enumerate(tests, start=1):
        lines.append(f"- T{index}: {' '.join(test.split())}")
    return "\n".join(lines)


@dataclass(frozen=True)
class JudgeMetricSpec:
    """One LLM-judged dimension, assembled into a native MLflow GenAI metric.

    Keeping the rubric as data rather than as a formatted blob means the
    anchors can be hashed for provenance (``rubric_hash``), diffed in review,
    and reused verbatim by the self-consistency probe in Part 7 -- which must
    send the *same* prompt as ``mlflow.evaluate`` or it measures nothing.
    """

    name: str
    definition: str
    tests: tuple[str, ...]
    anchors: Mapping[int, str]
    grading_context_columns: tuple[str, ...]
    examples: tuple[EvaluationExample, ...] = ()
    greater_is_better: bool = True

    def grading_prompt(self) -> str:
        return _assert_brace_free(
            "\n\n".join([
                _render_tests(self.tests),
                _render_anchors(self.anchors),
                COT_PROTOCOL.strip(),
            ]),
            f"grading_prompt for {self.name}",
        )

    def analysis_prompt(
        self, *, prediction: str, grading_context: Mapping[str, str]
    ) -> str:
        """Stage-one prompt: reasoning only, with no score field available.

        Built by hand rather than through MLflow, precisely because MLflow
        appends a "return a score" instruction to everything it renders --
        which is the behaviour this stage exists to escape. Withholding the
        score field is the whole mechanism: the judge cannot pick a number
        and work backwards if it has not been asked for a number yet.
        """
        context = "\n\n".join(
            f"{key.upper()}:\n{value}" for key, value in grading_context.items()
        )
        return "\n".join([
            ("You are auditing one dimension of an AI-generated software "
            "engineering sprint assessment. Do NOT award a score. Do NOT say "
            "whether the output is good or bad overall. Your only job is to "
            "establish the facts another evaluator will score from."),
            "",
            f"DIMENSION UNDER AUDIT: {self.name}",
            f"WHAT THIS DIMENSION MEANS:\n{self.definition}",
            "",
            _render_tests(self.tests),
            "",
            context,
            "",
            f"ASSESSMENT UNDER AUDIT:\n{prediction}",
            "",
            "Reply with a single JSON object and nothing else, with these keys:",
            ('  "evidence_scan": an array of 2 to 5 strings, each naming one '
            "concrete item you checked (a commit SHA, a ticket key, a "
            "filename, a named metric, a person) and what you found when you "
            "looked for it in the ground-truth material above."),
            ('  "anchor_check": an array with one string per rubric test, in '
            "order, each of the form T1 PASSED because ... or T1 FAILED "
            "because ... citing the specific evidence."),
            ('  "unresolved": an array of strings naming anything you could not '
            "verify either way, or an empty array. Do not guess."),
            "",
            ("Report only what you can check. An empty or unparseable "
            "assessment is a finding, not an error: say so in evidence_scan."),
        ])

    def rubric_hash(self) -> str:
        """Stable hash of the full rubric text, logged as an MLflow param.

        A judge score is only comparable across runs if the rubric that
        produced it was identical. Version strings get forgotten; a hash of
        the actual text does not.
        """
        hasher = hashlib.sha256()
        hasher.update(self.name.encode())
        hasher.update(self.definition.encode())
        hasher.update(self.grading_prompt().encode())
        for example in self.examples:
            hasher.update(str(example).encode())
        return hasher.hexdigest()[:16]

    def eval_prompt_for(
        self,
        *,
        judge_uri: str,
        prediction: str,
        inputs: str,
        grading_context: Mapping[str, str],
        parameters: Mapping[str, Any] | None = None,
    ) -> str:
        """The exact payload ``mlflow.evaluate`` would send for one row.

        Built through MLflow's own ``EvaluationModel`` rather than a
        hand-rolled copy, so Parts 6 and 7 cannot drift away from what the
        headline numbers were produced with.
        """
        model = EvaluationModel(
            name=self.name,
            definition=self.definition,
            grading_prompt=self.grading_prompt(),
            examples=list(self.examples),
            model=judge_uri,
            parameters=dict(parameters or judge_parameters()),
            include_input=True,
        )
        context_lines = "\n".join(
            f"key: {key}\nvalue:\n{value}" for key, value in grading_context.items()
        )
        rendered = model.to_dict()["eval_prompt"].format(
            input=inputs, output=prediction, grading_context_columns=context_lines
        )
        if not rendered.strip():
            raise RuntimeError(
                f"Rendered an empty judge prompt for metric '{self.name}'. This is "
                "the PromptTemplate brace failure described in the module docstring."
            )
        return rendered

    def cot_column(self) -> str:
        """Name of the frame column holding this metric's stage-one analysis."""
        return f"cot_{self.name}"

    def _example_context(self, example: EvaluationExample) -> dict[str, str]:
        """An exemplar's grading context as a dict, whatever form it was given in.

        ``EvaluationExample.grading_context`` is typed ``dict | str | None``.
        A bare string is legal and MLflow renders it as one unlabelled blob,
        so it has to be mapped onto a named column before the two-stage path
        can add its own -- otherwise building the metric raises on the
        dict unpacking, at import time, for an example that was perfectly
        valid in single-stage mode.
        """
        context = example.grading_context
        if isinstance(context, dict):
            return dict(context)
        if isinstance(context, str):
            first = (
                self.grading_context_columns[0]
                if self.grading_context_columns
                else "grading_context"
            )
            return {first: context}
        return {}

    def build(
        self, judge_uri: str, *, max_workers: int = 1, two_stage: bool = False
    ) -> Any:
        _assert_brace_free(self.definition, f"definition for {self.name}")
        grading_prompt = self.grading_prompt()
        context_columns = list(self.grading_context_columns)
        examples = list(self.examples)

        if two_stage:
            context_columns.append(self.cot_column())
            grading_prompt = _assert_brace_free(
                "A PRIOR EVIDENCE AUDIT of this output has already been "
                f"carried out and is supplied above as {self.cot_column()}. "
                "Treat its findings as established. Score the band its "
                "anchor_check results place this output in, and say in your "
                "justification which of its findings decided the band. If the "
                "audit reports a test FAILED, you may not award a band whose "
                "anchor requires that test to pass.\n\n" + grading_prompt,
                f"two-stage grading_prompt for {self.name}",
            )
            # MLflow validates that every example carries every grading
            # context column. The exemplar justifications already ARE anchor
            # checks, so reusing them keeps the few-shot demonstrations
            # consistent with what the judge will actually be shown.
            examples = [
                EvaluationExample(
                    output=example.output,
                    score=example.score,
                    justification=example.justification,
                    input=example.input,
                    grading_context={
                        **self._example_context(example),
                        self.cot_column(): example.justification,
                    },
                )
                for example in examples
            ]

        for index, example in enumerate(examples):
            _assert_brace_free(str(example), f"example {index} for {self.name}")
        return make_genai_metric(
            name=self.name,
            definition=self.definition,
            grading_prompt=grading_prompt,
            examples=examples,
            version="v1",
            model=judge_uri,
            grading_context_columns=context_columns,
            include_input=True,
            parameters=judge_parameters(),
            aggregations=["mean", "variance", "p90"],
            greater_is_better=self.greater_is_better,
            # One worker by default: these judges run against a single local
            # Ollama server, and MLflow's default of 10 concurrent requests
            # makes it thrash between loaded models instead of going faster.
            max_workers=max_workers,
            metric_metadata={"rubric_hash": self.rubric_hash(), "scale": "1-5"},
        )


#
# Why five and not one "overall quality" judge: a single scalar cannot
# separate the two failure modes that matter to a grading tool. A model can
# be perfectly faithful to the evidence and still give useless advice, or
# give excellent advice built on a fabricated commit. Collapsing those into
# one number means a stakeholder cannot tell which risk they are carrying.
# Each metric below is also chosen to be judgeable: it asks the judge to
# verify something present in the evidence, never to guess a latent "quality".
#
# Deliberately NOT judged by an LLM (handled arithmetically in Part 3):
# numeric grade accuracy against gold, and cross-fixture rank ordering.
# Asking a 3B model to compare two integers adds latency and a second error
# source to something `abs(a - b)` does exactly.

# -- Few-shot calibration examples -------------------------------------------
#
# Each metric gets one HIGH and one LOW exemplar. Two is a deliberate floor:
# few-shot examples are what stop a local judge collapsing onto the middle of
# the scale, but each one is also prompt budget spent before the real output
# is read, and more than two or three measurably crowds out the bundle on a
# 4k-context judge. The exemplars are written in the project's own domain
# (AUTH-* tickets, real commit-shaped SHAs) so the judge calibrates on inputs
# shaped like the ones it will see. All text is brace-free -- see Part 0.

_FAITHFULNESS_HIGH = EvaluationExample(
    input="Grade the testing dimension for team CS203-G6, sprint S1.",
    output=(
        "testing scored 8 of 10. Justification: testing was planned as its own "
        "ticket and delivered alongside the feature it covers. Evidence: Jira "
        "ticket AUTH-2 titled Auth Tests is marked Done and assigned to Bob; "
        "commit 4f21ab9 by Bob added 120 lines to tests/test_auth.py."
    ),
    score=5,
    justification=(
        "T1 PASSED: both identifiers, AUTH-2 and 4f21ab9, appear in the bundle. "
        "T2 PASSED: the 120-line figure and the Done status match the bundle "
        "exactly. T3 PASSED: Bob is a commit author and the ticket assignee. "
        "T4 PASSED: no tool or file outside the bundle is claimed. Every "
        "factual claim is traceable, which is the top band."
    ),
    grading_context={
        "artifact_bundle": (
            "commits: 4f21ab9 by Bob, message Write unit tests for auth, plus "
            "120 lines minus 0, files tests/test_auth.py. jira_tickets: AUTH-2 "
            "Auth Tests, status Done, assignee Bob, story_points 3."
        )
    },
)

_FAITHFULNESS_LOW = EvaluationExample(
    input="Grade the cicd dimension for team CS203-G6, sprint S1.",
    output=(
        "cicd scored 7 of 10. Justification: the team maintains a mature "
        "deployment pipeline with automated rollback. Evidence: commit 9c0d7e1 "
        "configured the GitHub Actions release workflow; Jenkinsfile defines "
        "the staging promotion gate."
    ),
    score=1,
    justification=(
        "T1 FAILED: neither 9c0d7e1 nor Jenkinsfile appears anywhere in the "
        "bundle, which contains no CI configuration at all. T2 FAILED: there "
        "is no evidence of a pipeline to quantify. T4 FAILED: automated "
        "rollback and a staging gate are inventions. The central claims are "
        "fabricated, so this is the bottom band regardless of how confident "
        "the prose sounds."
    ),
    grading_context={
        "artifact_bundle": (
            "commits: 4f21ab9 by Bob, files tests/test_auth.py; 1a2b3c4 by "
            "Alice, files src/auth.py. jira_tickets: AUTH-2 Auth Tests, Done. "
            "artifact_metrics: none. No workflow, Dockerfile or CI file present."
        )
    },
)

_ACTIONABILITY_HIGH = EvaluationExample(
    input="Review the recommendations for team CS203-JY, sprint S2.",
    output=(
        "Recommendations: 1. Assign Dana to add integration tests for the "
        "payment handler in src/payments.py, which AUTH-7 left untested. "
        "2. Split the 900-line commit 7de45f2 into reviewable units before the "
        "next sprint review."
    ),
    score=5,
    justification=(
        "T1 PASSED: both recommendations name a file and an owner or a specific "
        "commit. T2 PASSED: both are completable inside one sprint. T3 PASSED: "
        "testing at 3 and code_quality at 4 are the two lowest dimensions in "
        "the gold reference, and the recommendations target exactly those. "
        "T4 PASSED: neither action is already done in the bundle. Concrete, "
        "assignable and aimed at the real bottleneck."
    ),
    grading_context={
        "gold_reference": (
            "rubric scores out of 10: testing 3, code_quality 4, documentation "
            "7, requirements 8, collaboration 8, cicd 6. Lowest two dimensions "
            "are testing and code_quality."
        ),
        "artifact_bundle": (
            "commits: 7de45f2 by Dana, plus 900 lines minus 12, files "
            "src/payments.py. jira_tickets: AUTH-7 Payment handler, status Done, "
            "assignee Dana. artifact_metrics: no coverage key present."
        ),
    },
)

_ACTIONABILITY_LOW = EvaluationExample(
    input="Review the recommendations for team CS203-JY, sprint S2.",
    output=(
        "Recommendations: 1. Keep up the great communication. 2. Continue to "
        "improve code quality going forward. 3. Maintain the strong "
        "requirements tracking the team has shown."
    ),
    score=1,
    justification=(
        "T1 FAILED: no file, ticket or owner is named in any of the three. "
        "T2 FAILED: continue and maintain are not assignable actions. "
        "T3 FAILED: two of the three praise collaboration and requirements, "
        "the team's two STRONGEST dimensions in gold, while testing at 3 is "
        "never mentioned. This is generic filler, the bottom band."
    ),
    grading_context={
        "gold_reference": (
            "rubric scores out of 10: testing 3, code_quality 4, documentation "
            "7, requirements 8, collaboration 8, cicd 6. Lowest two dimensions "
            "are testing and code_quality."
        ),
        "artifact_bundle": (
            "commits: 7de45f2 by Dana, files src/payments.py. jira_tickets: "
            "AUTH-7 Payment handler, status Done. peer_evaluations: 3 entries."
        ),
    },
)

_CORRECTNESS_HIGH = EvaluationExample(
    input="Check the technical reasoning for the testing dimension.",
    output=(
        "testing scored 4 of 10. A test file exists, tests/test_auth.py with "
        "120 lines added in 4f21ab9, but the bundle reports no coverage "
        "metric, so the presence of tests cannot be read as the code being "
        "covered. Scored on demonstrated test work only."
    ),
    score=5,
    justification=(
        "T2 PASSED and is the whole point: the output explicitly refuses to "
        "infer coverage from the existence of a test file, and says so. "
        "T1 PASSED: the 120 lines are reported as volume of test work, not as "
        "evidence of quality. T3 and T4 are not engaged. Every inference from "
        "evidence to judgement is valid."
    ),
    grading_context={
        "artifact_bundle": (
            "commits: 4f21ab9 by Bob, plus 120 lines, files tests/test_auth.py. "
            "artifact_metrics: no coverage key present."
        ),
        "gold_reference": "Human reference: testing 4 of 10.",
    },
)

_CORRECTNESS_LOW = EvaluationExample(
    input="Check the technical reasoning for the code_quality dimension.",
    output=(
        "code_quality scored 9 of 10. The team added 4,200 lines this sprint, "
        "far above average, and the CI workflow file proves the test suite is "
        "green. AUTH-9 is marked Done so the refactor is merged and in "
        "production."
    ),
    score=1,
    justification=(
        "T1 FAILED: 4,200 added lines is used directly as a quality proxy, "
        "when high churn is at least as consistent with copied or generated "
        "code. T3 FAILED: the presence of a workflow FILE is treated as proof "
        "the suite passes, which it cannot establish. T4 FAILED: a Done ticket "
        "is conflated with merged and deployed code. Three invalid inferences, "
        "and the conclusion does not follow from the cited evidence."
    ),
    grading_context={
        "artifact_bundle": (
            "commits: 8 commits by 2 authors, plus 4200 lines minus 60. "
            "jira_tickets: AUTH-9 Refactor auth, status Done. artifact_metrics: "
            "no test result or coverage key present."
        ),
        "gold_reference": "Human reference: code_quality 5 of 10.",
    },
)

_SPECIFICITY_HIGH = EvaluationExample(
    input="Check evidence specificity across all six dimensions.",
    output=(
        "code_quality cites 1a2b3c4 in src/auth.py. testing cites AUTH-2 and "
        "tests/test_auth.py. documentation cites AUTH-5 and docs/auth.md. "
        "requirements cites 8 of 10 story points Done. collaboration cites "
        "Bob's peer review of Alice. cicd cites the absent coverage metric."
    ),
    score=5,
    justification=(
        "T1 PASSED: all six dimensions carry a hard anchor, a SHA, a ticket "
        "key, a file path or a named metric. T2 PASSED: each anchor is tied to "
        "the dimension it is cited for in one sentence. Top band."
    ),
    grading_context={"artifact_bundle": "All cited SHAs, tickets and files are present."},
)

_SPECIFICITY_LOW = EvaluationExample(
    input="Check evidence specificity across all six dimensions.",
    output=(
        "The team made several good commits and the tickets were mostly "
        "completed. Documentation was adequate. Collaboration was strong "
        "based on the peer feedback. CI looked reasonable."
    ),
    score=1,
    justification=(
        "T1 FAILED: not one commit SHA, ticket key, filename or metric name "
        "appears. Several, mostly and reasonable are unverifiable quantifiers. "
        "T2 FAILED: nothing is tied to a dimension by evidence. No hard "
        "anchors anywhere, the bottom band."
    ),
    grading_context={"artifact_bundle": "Bundle contains 8 commits and 10 tickets with keys."},
)

_ADHERENCE_HIGH = EvaluationExample(
    input="Check whether the numeric score matches the published rubric band.",
    output=(
        "requirements scored 7 of 10. 8 of 10 assigned tickets are Done, 21 of "
        "26 story points completed, none abandoned or blocked."
    ),
    score=5,
    justification=(
        "T1 PASSED: the published band for 6 to 8 is most tickets Done with "
        "none abandoned or stuck, and 8 of 10 Done with zero blocked sits "
        "squarely inside it. T2 PASSED: the narrative supports the number "
        "without inflating it, and gold also records 7. No drift."
    ),
    grading_context={
        "rubric_criteria": (
            "requirements band 9 to 10: all tickets Done and high story points. "
            "Band 6 to 8: most tickets Done, none abandoned or stuck. Band 3 to "
            "5: fewer than half Done. Band 1 to 2: little or no progress."
        ),
        "gold_reference": "requirements 7 of 10.",
    },
)

_ADHERENCE_LOW = EvaluationExample(
    input="Check whether the numeric score matches the published rubric band.",
    output=(
        "requirements scored 9 of 10. The team showed excellent commitment and "
        "a positive attitude. 3 of 10 tickets are Done and two are Blocked."
    ),
    score=1,
    justification=(
        "T1 FAILED: 3 of 10 Done with two Blocked falls in the published 3 to 5 "
        "band, fewer than half Done, yet the output awards 9. T2 FAILED: the "
        "stated reason, commitment and attitude, is not a rubric criterion for "
        "this dimension. The score is inflated by two whole bands on "
        "non-rubric grounds, the bottom band."
    ),
    grading_context={
        "rubric_criteria": (
            "requirements band 9 to 10: all tickets Done and high story points. "
            "Band 6 to 8: most tickets Done, none abandoned or stuck. Band 3 to "
            "5: fewer than half Done. Band 1 to 2: little or no progress."
        ),
        "gold_reference": "requirements 4 of 10.",
    },
)


CODE_FAITHFULNESS = JudgeMetricSpec(
    name="Code_Faithfulness",
    definition=(
        "Code faithfulness measures whether every factual claim the assessment "
        "makes about the team's software artifacts can be traced back to the "
        "artifact bundle it was given. The bundle of real commits, Jira tickets "
        "and peer evaluations is the only ground truth. A claim is unfaithful "
        "if its identifier does not exist in the bundle, if a verifiable "
        "attribute of that identifier is wrong, such as the author, the line "
        "count, the status or the filename, or if it describes work, tooling or "
        "files the bundle does not contain. Confident, fluent prose about "
        "artifacts that are not there is the most damaging failure a grading "
        "tool can have, so it scores at the bottom of this scale."
    ),
    tests=(
        ("Every citation identifier, commit SHA, ticket key, filename or metric "
        "name, appears in the artifact bundle."),
        ("Every number quoted, line counts, ticket counts, story points, "
        "percentages, matches the bundle."),
        ("Every person named appears in the bundle as a commit author, a ticket "
        "assignee or a peer reviewer."),
        ("No file, tool, pipeline or process is described that the bundle does "
        "not contain."),
    ),
    anchors={
        5: "Every factual claim is traceable. Each citation identifier appears "
           "in the bundle and each verifiable attribute of it is correct.",
        4: "Every citation resolves to a real bundle item and all attributes are "
           "correct, but at most one non-citation claim is a mild overstatement "
           "of what the evidence shows.",
        3: "All citation identifiers exist, but at least one misattributes a "
           "verifiable attribute, naming the wrong author, count, status or file.",
        2: "At least one citation identifier cannot be found in the bundle at "
           "all, or several attributes across the output are wrong.",
        1: "Central claims are fabricated. The narrative describes commits, "
           "files, tooling or work the bundle does not contain.",
    },
    grading_context_columns=("artifact_bundle",),
    examples=(_FAITHFULNESS_HIGH, _FAITHFULNESS_LOW),
)


BUG_ACTIONABILITY = JudgeMetricSpec(
    name="Bug_Actionability",
    definition=(
        "Bug actionability measures whether the weaknesses and recommendations "
        "in the assessment give the student team something they can actually "
        "do next, aimed at the problem that is actually holding them back. An "
        "actionable item names a concrete artifact, a file, a ticket, a commit "
        "or a named person, and a verb a team member could be assigned this "
        "week. A targeted item addresses one of the dimensions the gold "
        "reference scores lowest, rather than praising a dimension that was "
        "already strong. Generic encouragement such as communicate better or "
        "keep improving code quality is the characteristic failure here: it "
        "reads as feedback while carrying no information."
    ),
    tests=(
        ("Each recommendation names a concrete artifact or an owner, not just a "
        "dimension or a virtue."),
        ("Each recommendation uses a verb that could be assigned to one person "
        "and completed within a single sprint."),
        ("The recommendations address at least one of the two lowest-scoring "
        "dimensions in the gold reference."),
        ("No recommendation asks for work the artifact bundle shows is already "
        "finished."),
    ),
    anchors={
        5: "Every recommendation names a specific artifact or owner with an "
           "assignable next step, and the set targets the gold reference's "
           "lowest-scoring dimensions.",
        4: "Recommendations are concrete and assignable, but at least one aims "
           "at a dimension that was already strong.",
        3: "A mix of concrete and generic items. The true bottleneck is "
           "mentioned, but the action proposed for it is vague.",
        2: "Mostly generic advice with no named artifact or owner, and no clear "
           "link to the weakest dimension.",
        1: "No actionable content at all, or it recommends work the bundle "
           "shows is already complete.",
    },
    grading_context_columns=("gold_reference", "artifact_bundle"),
    examples=(_ACTIONABILITY_HIGH, _ACTIONABILITY_LOW),
)


TECHNICAL_CORRECTNESS = JudgeMetricSpec(
    name="Technical_Correctness",
    definition=(
        "Technical correctness measures whether the software-engineering "
        "reasoning that connects the evidence to the judgement is valid. The "
        "question is not whether the conclusion feels right but whether it "
        "follows. The recurring invalid inferences in automated code analysis "
        "are well known: treating lines added as a proxy for code quality, "
        "reading the existence of a test file as evidence of test coverage, "
        "reading a CI configuration file as evidence that CI passes, and "
        "treating a ticket marked Done as proof that code was merged and "
        "shipped. An output that explicitly declines to make one of these "
        "leaps, and says why, is demonstrating the behaviour this metric "
        "rewards most."
    ),
    tests=(
        ("Volume of code, lines added or commit count, is not used as a proxy "
        "for code quality."),
        ("The presence of tests is kept distinct from the extent of test "
        "coverage, and coverage is only claimed where a coverage metric exists."),
        ("A CI or workflow configuration file is kept distinct from evidence "
        "that the pipeline actually ran or passed."),
        ("A ticket status is kept distinct from code being merged, reviewed or "
        "deployed."),
        ("Collaboration metrics and peer scores are read as association, not as "
        "proof of cause."),
    ),
    anchors={
        5: "Every inference from evidence to judgement is technically valid, "
           "and the output explicitly declines at least one unsupported leap "
           "where the evidence invites one.",
        4: "Reasoning is sound throughout, with one minor technical imprecision "
           "that does not change the conclusion.",
        3: "One clearly invalid inference, for example treating added lines as "
           "quality or a test file as coverage, which affects one dimension.",
        2: "Multiple invalid inferences. The conclusions do not follow from the "
           "evidence that is cited for them.",
        1: "Technically wrong about what the artifacts are, misreading what a "
           "file, pipeline, status or metric actually represents.",
    },
    grading_context_columns=("artifact_bundle", "gold_reference"),
    examples=(_CORRECTNESS_HIGH, _CORRECTNESS_LOW),
)


EVIDENCE_SPECIFICITY = JudgeMetricSpec(
    name="Evidence_Specificity",
    definition=(
        "Evidence specificity measures whether the assessment anchors its "
        "judgements to hard, checkable identifiers rather than to unverifiable "
        "prose. A hard anchor is a commit SHA, a Jira ticket key, a file path "
        "or a named metric with its value. Quantifiers such as several "
        "commits, mostly complete or generally good are not anchors: a human "
        "marker cannot audit them, and neither can a downstream grounding "
        "check. This metric is scored independently of whether the claims are "
        "true, which is Code Faithfulness, because a specific-but-wrong claim "
        "and a vague-but-safe one are different problems with different fixes."
    ),
    tests=(
        ("Each scored dimension cites at least one hard anchor, a commit SHA, a "
        "ticket key, a file path or a named metric with a value."),
        ("Each anchor is tied to the dimension it is cited for by at least one "
        "sentence of explanation."),
        ("Unverifiable quantifiers are not doing the work that an anchor should "
        "be doing."),
    ),
    anchors={
        5: "Every scored dimension cites at least one hard anchor and ties it "
           "to the judgement in a sentence.",
        4: "All but one scored dimension is anchored, and the unanchored one is "
           "a dimension with genuinely thin evidence in the bundle.",
        3: "About half the dimensions are anchored; the rest rest on prose "
           "alone.",
        2: "Anchors are present in name only, generic references such as "
           "several commits or the test file, with no identifier.",
        1: "No hard anchors anywhere in the output.",
    },
    grading_context_columns=("artifact_bundle",),
    examples=(_SPECIFICITY_HIGH, _SPECIFICITY_LOW),
)


RUBRIC_ADHERENCE = JudgeMetricSpec(
    name="Rubric_Adherence",
    definition=(
        "Rubric adherence measures whether the number awarded is the number "
        "the published rubric band calls for, given the evidence the output "
        "itself presents. The failure mode is score inflation: a narrative "
        "that describes band-three evidence while awarding a nine, or that "
        "justifies a score on grounds the rubric does not list, such as effort, "
        "attitude or improvement over last sprint. This is judged against the "
        "rubric criteria text supplied as grading context, not against the "
        "judge's own taste, and the gold reference is provided as a second "
        "opinion on where the band should fall rather than as the answer key."
    ),
    tests=(
        ("The evidence the output presents falls inside the published band for "
        "the score it awarded."),
        ("The stated reasons for the score are criteria the published rubric "
        "lists for that dimension, not effort, attitude or improvement."),
        ("The direction and size of any disagreement with the gold reference is "
        "explainable from the evidence rather than arbitrary."),
    ),
    anchors={
        5: "The evidence presented places every score inside its published "
           "band, and the reasons given are rubric criteria.",
        4: "Scores sit inside their bands, with one score justified partly on a "
           "non-rubric ground such as effort.",
        3: "At least one score sits one band away from what the output's own "
           "evidence supports.",
        2: "Several scores sit outside the band their evidence supports, "
           "consistently in the same direction.",
        1: "Scores are two or more bands away from the evidence, or are "
           "justified on grounds the rubric does not contain at all.",
    },
    grading_context_columns=("rubric_criteria", "gold_reference"),
    examples=(_ADHERENCE_HIGH, _ADHERENCE_LOW),
)


JUDGE_METRIC_SPECS: tuple[JudgeMetricSpec, ...] = (
    CODE_FAITHFULNESS,
    BUG_ACTIONABILITY,
    TECHNICAL_CORRECTNESS,
    EVIDENCE_SPECIFICITY,
    RUBRIC_ADHERENCE,
)

JUDGE_METRIC_NAMES: tuple[str, ...] = tuple(spec.name for spec in JUDGE_METRIC_SPECS)

SPEC_BY_NAME: dict[str, JudgeMetricSpec] = {spec.name: spec for spec in JUDGE_METRIC_SPECS}

# Rubrics that read the human gold reference as grading context. A sprint with no gold (the real
# sprints) can only be judged on the others: showing the judge a placeholder reference would bias
# exactly the scores it is meant to produce.
GOLD_DEPENDENT_METRICS: tuple[str, ...] = tuple(
    spec.name for spec in JUDGE_METRIC_SPECS if "gold_reference" in spec.grading_context_columns
)
GOLD_FREE_METRICS: tuple[str, ...] = tuple(
    name for name in JUDGE_METRIC_NAMES if name not in GOLD_DEPENDENT_METRICS
)


def selected_specs(only: Sequence[str] | None = None) -> tuple[JudgeMetricSpec, ...]:
    if not only:
        return JUDGE_METRIC_SPECS
    missing = set(only) - set(SPEC_BY_NAME)
    if missing:
        raise KeyError(f"Unknown judge metrics: {sorted(missing)}")
    return tuple(SPEC_BY_NAME[name] for name in only)


def build_genai_metrics(
    judge_uri: str,
    *,
    only: Sequence[str] | None = None,
    max_workers: int = 1,
    two_stage: bool = False,
) -> list[Any]:
    """Instantiate the GenAI metrics. ``only`` restricts to named metrics."""
    return [
        spec.build(judge_uri, max_workers=max_workers, two_stage=two_stage)
        for spec in selected_specs(only)
    ]
