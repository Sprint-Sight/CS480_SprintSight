"""
prompts/dimension_criteria.py

The rubric criteria text for each scored dimension. This is prompt content,
not schema — kept separate from schemas/rubrics_score.py (which only defines
the RubricsScore Pydantic model) so the criteria can be read, reviewed, and
versioned as a single unit instead of being buried next to unrelated model code.
"""

requirements = '''
    Evaluate the individual's performance against the Requirements dimension using the provided Jira/project data.

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
    Evaluate the individual's Code Quality based on the available Git repository and commit history.

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
    Evaluate the individual's Testing performance using Jira tickets, Git commits, test files, and other available testing evidence.

    Assess:

    Number of dedicated testing/test-related Jira tickets completed
    Presence of explicit test-related commits
    Evidence of unit, integration, system, or other appropriate tests
    Whether testing appears comprehensive relative to the code contributed
    Whether testing work is clearly attributable to the individual

    Assign a score from 1–10 using this rubric:

    9–10: Dedicated test tickets are Done and explicit test-related commits are present.
    6–8: Some test commits are present, but coverage appears incomplete.
    3–5: Minimal testing is evident in commit logs or Jira tickets.
    1–2: Zero evidence of test files or testing activity.

    Output: Provide the score, a concise justification, and specific testing evidence. Do not assume that code was tested unless there is evidence supporting it.
    '''

documentation_prompt = '''
    Evaluate the individual's contribution to Documentation using Git commits, Jira ticket descriptions/summaries, README files, technical documentation, and other available project artifacts.

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

    Output: Provide the score, a concise justification, and the specific documentation evidence supporting the score. Do not award credit for documentation that cannot be attributed to the individual.
    '''

collaboration_prompt = '''
    Evaluate the individual's Collaboration performance using peer ratings and workload distribution data.

    Assess:

    Average peer rating received
    Distribution of peer ratings, where available
    Number of tickets/story points handled relative to teammates
    Whether workload appears reasonably balanced
    Evidence of severe under-contribution or freeriding

    Assign a score from 1–10 using this rubric:

    9–10: Peer rating average is 4.5–5.0 and workload is evenly balanced.
    6–8: Peer rating average is 3.5–4.4 and workload is mostly balanced.
    3–5: Peer rating average is 2.5–3.4 and workload is highly imbalanced.
    1–2: Peer rating average is below 2.5 and there is strong evidence of freeriding.

    Output: Provide the score, a concise justification, the peer-rating evidence, and the workload evidence. Do not treat a low ticket count alone as evidence of poor collaboration without considering the individual's assigned workload.
    '''

cicd_prompt = '''
    Evaluate the individual's contribution to Continuous Integration and Continuous Deployment (CI/CD) using Git commits, pipeline configurations, deployment logs, and other available project artifacts.

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

    Output: Provide the score, a concise justification, and the specific CI/CD evidence supporting the score. Do not award credit for CI/CD practices that cannot be attributed to the individual.
    '''

DIMENSIONS = ["code_quality", "testing", "documentation", "requirements", "collaboration", "cicd"]

DIMENTION_PROMPTS = {
    "code_quality": code_quality_prompt,
    "testing": testing_prompt,
    "documentation": documentation_prompt,
    "requirements": requirements,
    "collaboration": collaboration_prompt,
    "cicd": cicd_prompt,
}
