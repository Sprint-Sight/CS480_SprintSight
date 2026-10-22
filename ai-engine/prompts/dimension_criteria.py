"""
prompts/dimension_criteria.py

The rubric criteria text for each scored dimension. This is prompt content,
not schema — kept separate from schemas/rubrics_score.py (which only defines
the RubricsScore Pydantic model) so the criteria can be read, reviewed, and
versioned as a single unit instead of being buried next to unrelated model code.
"""

from schemas.rubrics_dimension_score import DimensionName

requirements = '''
    Evaluate the team's performance against the Requirements dimension using the provided Jira/project data. This is a single, team-level judgement — do not score individual members.

    Assess:

    Number and percentage of assigned Jira tickets marked Done
    Number of tickets remaining in To Do / In Progress / Blocked
    Total story points completed
    Whether any assigned tickets were abandoned or left stuck
    Overall delivery velocity relative to the assigned workload

    Assign a score from 1–10 using this rubric:

    9–10: All assigned tickets are Done and a high number of story points were completed.
    6–8: Most tickets are Done, with no abandoned or stuck tickets.
    3–5: Less than half of tickets are Done and story-point velocity is low.
    1–2: Little or no progress; zero tickets are marked Done.

    Output: Provide the score, a concise justification, and the key evidence used. Do not infer completion without supporting evidence.
    '''

code_quality_prompt = '''
    Evaluate the team's Code Quality based on the available Git repository and commit history. This is a single, team-level judgement — do not score individual members.

    Assess:

    Volume of meaningful code contributions/lines added
    Number and consistency of code commits
    Whether commits represent substantive development work rather than trivial changes
    Clarity, specificity, and professionalism of commit messages
    Whether the commits demonstrate meaningful progress toward the project's requirements

    Assign a score from 1–10 using this rubric:

    9–10: Substantial code contributions with descriptive, professional commit messages.
    6–8: Moderate code contributions with basic but clear commit messages.
    3–5: Few commits and/or vague, missing, or unhelpful commit messages.
    1–2: No meaningful code contributions or commits are recorded.

    Output: Provide the score, a concise justification, and the strongest evidence from the commit history. Distinguish between quantity of code and meaningful contribution.
    '''

testing_prompt = '''
    Evaluate the team's Testing performance using Jira tickets, Git commits, test files, and other available testing evidence. This is a single, team-level judgement — do not score individual members.

    Assess:

    Number of dedicated testing/test-related Jira tickets completed
    Presence of explicit test-related commits
    Evidence of unit, integration, system, or other appropriate tests
    Whether testing appears comprehensive relative to the code the team contributed

    Assign a score from 1–10 using this rubric:

    9–10: Dedicated test tickets are Done and explicit test-related commits are present.
    6–8: Some test commits are present, but coverage appears incomplete.
    3–5: Minimal testing is evident in commit logs or Jira tickets.
    1–2: Zero evidence of test files or testing activity.

    Output: Provide the score, a concise justification, and specific testing evidence. Do not assume that code was tested unless there is evidence supporting it.
    '''

documentation_prompt = '''
    Evaluate the team's Documentation using Git commits, Jira ticket descriptions/summaries, README files, technical documentation, and other available project artifacts. This is a single, team-level judgement — do not score individual members.

    Assess:

    Explicit documentation-related commits
    Quality and usefulness of README or technical documentation updates
    Whether Jira ticket summaries/descriptions clearly document completed work
    Whether documentation is sufficiently detailed and understandable
    Consistency between the implemented work and its documentation

    Assign a score from 1–10 using this rubric:

    9–10: Explicit documentation commits are present and ticket summaries are well documented.
    6–8: Minor but useful README or documentation updates are present.
    3–5: Documentation is vague, incomplete, or missing across some artifacts.
    1–2: No documentation effort is recorded in any system.

    Output: Provide the score, a concise justification, and the specific documentation evidence supporting the score. Do not award credit for documentation unless there is evidence it was actually produced.
    '''

collaboration_prompt = '''
    Evaluate the team's Collaboration as a whole, using workload distribution and participation evidence drawn from the available Git and project-management data. This is a single, holistic team-level judgement — do NOT score or single out individual members.

    Assess:

    Whether work is shared across the team rather than concentrated in only one or two members
    How actively the team uses project-management tools — e.g. whether Jira tickets are created, assigned, updated, and moved to Done rather than left stale or unused
    Participation in shared work such as code reviews, pull-request discussion, and comments on each other's tickets
    Consistency of engagement across the sprint rather than isolated bursts of activity
    Evidence that the team is coordinating, or conversely that some members are not contributing at all

    Assign a score from 1–10 using this rubric:

    9–10: Work is well distributed across the team and project-management tools are used consistently and actively.
    6–8: Work is mostly shared and project-management tools are used, with some gaps.
    3–5: Work is concentrated in a few members, or project-management tools are used only sporadically.
    1–2: Little evidence of teamwork; contribution is highly uneven or project-management tools are barely used.

    Output: Provide the score, a concise justification, and the workload and participation evidence supporting the score. Do not treat a low overall ticket count as poor collaboration without considering the total scope of the team's assigned work.
    '''

cicd_prompt = '''
    Evaluate the team's Continuous Integration and Continuous Deployment (CI/CD) practices using Git commits, pipeline configurations, deployment logs, and other available project artifacts. This is a single, team-level judgement — do not score individual members.

    Assess:

    Frequency and quality of CI/CD pipeline updates
    Evidence of automated testing and deployment practices
    Responsiveness to pipeline failures and incidents
    Consistency between code changes and CI/CD configurations

    Assign a score from 1–10 using this rubric:

    9–10: CI/CD practices are well-established, automated, and consistently followed.
    6–8: CI/CD practices are present but may have minor gaps or inconsistencies.
    3–5: CI/CD practices are sporadic or partially implemented.
    1–2: No significant CI/CD practices are evident.

    Output: Provide the score, a concise justification, and the specific CI/CD evidence supporting the score. Do not award credit for CI/CD practices unless there is evidence they were actually implemented.
    '''

DIMENSIONS: list[DimensionName] = ["code_quality", "testing", "documentation", "requirements", "collaboration", "cicd"]

DIMENSION_PROMPTS: dict[DimensionName, str] = {
    "code_quality": code_quality_prompt,
    "testing": testing_prompt,
    "documentation": documentation_prompt,
    "requirements": requirements,
    "collaboration": collaboration_prompt,
    "cicd": cicd_prompt,
}
