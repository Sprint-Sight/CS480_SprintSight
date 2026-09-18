"""
prompts/templates.py

The wrapping instructions (JSON formatting, citation rules, evidence rules)
that get combined with a dimension's criteria text and the serialized
ArtifactBundle to form the full prompt sent to the model. Kept separate from
services/llm_client.py so the exact text sent to the model can be read and
reviewed as a single unit instead of being buried inside client/transport code.

To see what was ACTUALLY sent for a given run, read ai-engine/audit_logs/ —
these functions only control what's sent going forward.
"""


def render_dimension_prompt(dimension_name: str, dimension_criteria: str, bundle_data: str) -> str:
    return f"""
    You are an expert software engineering professor.
    Return exactly one rubric assessment object for the dimension: {dimension_name}.
    Do not summarize, transform, or repeat the student artifacts.
    Here are the rubric criteria for {dimension_name}:
    {dimension_criteria}

    INSTRUCTOR GUIDANCE:
    Student Artifacts below includes an `instructor_expectations` field written
    by the course instructor for this sprint. Treat it as authoritative
    context for how to grade {dimension_name}: if it calls out a specific
    focus, priority, exception, or deduction relevant to this dimension, weigh
    that guidance alongside the rubric criteria above. If it says nothing
    relevant to {dimension_name}, grade using the rubric criteria alone.

    CRITICAL INSTRUCTIONS:
    - Return a valid JSON object matching the RubricDimensionScore schema, and nothing else.
    - The `dimension` field MUST be exactly `{dimension_name}`.
    - Score MUST be an integer between 1 and 10.
    - Provide justification for the score.
    - Each score band spans multiple numbers (e.g. 6-8). Do NOT default to the
        top of the band. If your own justification names specific gaps,
        missing coverage, or deficiencies, score toward the LOWER end of that
        band. Only use the top of a band when there are no noted deficiencies
        at all.

    CRITICAL CITATION RULES:
    1. Every item in evidence_citations MUST be an object with EXACTLY two
        fields: `identifier` and `reason`. Do NOT invent your own field names
        for these two fields (e.g. do NOT write "verbatim identifier" or
        "one short sentence explaining why..." as field names — those are
        descriptions of what to put in `identifier` and `reason`, not the
        field names themselves).
    2. `identifier` MUST be copied verbatim from Student Artifacts: a commit
        SHA, Jira ticket ID, filename, or supplied metric value. Never use
        placeholders such as "commit 1", and never invent an identifier.
    3. `reason` MUST be ONE short sentence explaining why that specific
        identifier supports the score, referring to details that actually
        belong to THAT SPECIFIC record (its real commit message, its real
        file names, its real ticket status) — never a generic-sounding reason
        that could apply to any commit.
    4. Do NOT repeat benchmark, fixture, or example strings from prior prompts.
        Use only the actual Student Artifacts provided below.
    5. If a citation cannot be matched to the current bundle, do not include it.

    Evidence rules:
    - Use only evidence present in Student Artifacts.
    - Do not invent issue numbers, URLs, names, scores, statuses, or activity.
    - If evidence is missing, say so and score conservatively; still return the required rubric object.
    - Returning an EMPTY evidence_citations list together with a low score is a
        correct, expected answer when the bundle contains little or no relevant
        work for this dimension. Never fabricate a citation just to avoid an
        empty list — a fabricated citation is a worse failure than an empty one.

    Student Artifacts:
    {bundle_data}

    Final instruction: return one RubricDimensionScore for `{dimension_name}`.
    Set `dimension` to exactly `{dimension_name}`. Do not return `collaboration`
    or any other dimension unless the requested dimension is `collaboration`.
    """


def render_sprint_feedback_prompt(team_id: str, sprint_id: str, scores_data: str, instructor_expectations: str) -> str:
    return f"""
    You are an expert software engineering professor reviewing a complete sprint.
    Produce general project-level feedback, not feedback for individual rubric dimensions.

    Return exactly one JSON object matching the SprintFeedback schema:
    - strengths: general strengths of the sprint or team
    - weaknesses: general weaknesses of the sprint or team
    - recommendations: general actionable recommendations for the next sprint

    Use only the rubric results and evidence below. Do not invent facts, names,
    URLs, issue numbers, statuses, or activity. Avoid repeating the rubric
    justifications verbatim. Keep each item concise and specific.

    Instructor guidance for this sprint (weigh this alongside the rubric
    results; if it names a specific priority or concern, reflect that in the
    strengths/weaknesses/recommendations where relevant):
    {instructor_expectations}

    Sprint context:
    team_id={team_id!r} sprint_id={sprint_id!r}

    Rubric results:
    {scores_data}
    """
