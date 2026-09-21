from mlflow.genai import load_prompt, register_prompt, set_prompt_alias

DIMENSION_PROMPT_TEMPLATE = """
    You are an expert software engineering professor. 
    Evaluate the individual's performance against the {dimension} dimension using the provided Jira/project data.

    Assess:
    {assess}

    Assign a score from 1–10 using this rubric:

    {scoring}

    Output: {output}

    CRITICAL INSTRUCTIONS:
        - Return a valid JSON object matching the RubricDimensionScore schema.
        - Score MUST be an integer between 1 and 10.
        - Provide justification for the score.
        - Identify strengths.
        - Identify areas for improvement.
    
    CRITICAL CITATION RULES:
    1. Every item in evidence_citations MUST be a plain text string.
    2. Do NOT wrap citations inside objects or key-value pairs.
    3. When citing code files or documents, cite as "filename:line" using the line numbers shown in the context.
"""

DIMENSION_PLACEHOLDERS = {
    "requirements": {
        "dimension": "requirements",
        "first_sentence": '''Evaluate the individual's performance against the Requirements 
        dimension using the provided Jira/project data.''',

        "assess": '''
            Number and percentage of assigned Jira tickets marked Done
            Number of tickets remaining in To Do / In Progress / Blocked
            Total story points completed
            Whether any assigned tickets were abandoned or left stuck
            Overall delivery velocity relative to the assigned workload
            ''',

        "scoring": '''
            9–10: All assigned tickets are Done and a high number of story points were completed.
            6–8: Most tickets are Done, with no abandoned or stuck tickets.
            3–5: Less than half of tickets are Done and story-point velocity is low.
            1–2: Little or no progress; zero tickets are marked Done.''',

        "output": '''Provide the score, a concise justification, and the key evidence used. 
        Do not infer completion without supporting evidence.
        ''',
    },

    "code_quality": {
        "dimension": "code_quality",
        "first_sentence": '''Evaluate the individual's Code Quality based on the actual submitted 
        source code files, Git repository, and commit history.''',

        "assess": '''
            The actual source code files submitted for readability, maintainability, and adherence to best practices.
            Presence of clear logical structure, proper naming conventions, and modularity in the code files.
            Volume of meaningful code contributions and lines added.
            Number and consistency of code commits.
            Whether commits represent substantive development work rather than trivial changes.
            ''',

        "scoring": '''
            9–10: Exceptional code quality in submitted files with clear structure, and meaningful, well-documented commits.
            6–8: Good code quality in most files, with consistent commits representing substantive work.
            3–5: Mediocre code quality, structural issues in the files, or commits lack clarity and substance.
            1–2: Poor code quality, messy or missing files, and trivial or missing commits.
            ''',

        "output": '''Provide the score, a concise justification, and the strongest evidence. 
        You MUST explicitly cite specific file names, line numbers, or code snippets from the submitted 
        artifacts to prove your assessment of the code quality.''',
    },

    "testing": {
        "dimension": "testing",
        "first_sentence": '''Evaluate the individual's Testing performance using Jira tickets, 
        Git commits, test files, and other available testing evidence.''',

        "assess": '''
            Number of dedicated testing/test-related Jira tickets completed
            Presence of explicit test-related commits
            Evidence of unit, integration, system, or other appropriate tests
            Whether testing appears comprehensive relative to the code contributed
            Whether testing work is clearly attributable to the individual
            ''',

        "scoring": '''
            9–10: Comprehensive testing with clear evidence of unit, integration, and system tests.
            6–8: Adequate testing with some evidence of test coverage.
            3–5: Minimal testing with limited evidence of test coverage.
            1–2: No meaningful testing or test evidence is recorded.''',

        "output": '''Provide the score, a concise justification, and the strongest evidence 
        from the testing artifacts. Distinguish between quantity of tests and meaningful coverage.''',
    },

    "documentation": {
        "dimension": "documentation",
        "first_sentence": '''Evaluate the individual's Documentation performance by directly reviewing 
        the submitted documentation files (e.g., READMEs, inline comments, API docs), along with related Jira tickets and Git commits.''',

        "assess": '''
            The actual content of the submitted documentation files for clarity, conciseness, and comprehensiveness.
            Quality and presence of inline code comments and API documentation within the source files.
            Number of dedicated documentation-related Jira tickets completed.
            Presence of explicit documentation-related commits.
            Whether the documentation accurately reflects the code contributed.
            ''',

        "scoring": '''
            9–10: Comprehensive, well-written documentation files (user guides, API docs) and excellent inline comments.
            6–8: Adequate documentation with clear files and some inline comments.
            3–5: Minimal documentation, lacking depth in files or comments.
            1–2: No meaningful documentation files or inline comments are provided.''',

        "output": '''Provide the score, a concise justification, and the strongest evidence. 
        You MUST explicitly cite specific file names, text paragraphs, or inline comments from the 
        submitted documentation artifacts to support your assessment.''',
    },

    "collaboration": {
        "dimension": "collaboration",
        "first_sentence": '''Evaluate the individual's Collaboration performance using Jira tickets,
        Git commits, peer evaluations, and other available collaboration evidence.''',

        "assess": '''
            Number of peer evaluations completed and received
            Quality and constructiveness of peer feedback provided
            Evidence of active participation in team discussions and decision-making
            Willingness to assist teammates and contribute to shared goals
            Overall impact on team cohesion and productivity
            ''',

        "scoring": '''
            9–10: Exceptional collaboration with clear evidence of active participation and positive impact on the team.
            6–8: Good collaboration with some evidence of contribution.
            3–5: Minimal collaboration with limited evidence of contribution.
            1–2: No meaningful collaboration or evidence is recorded.''',

        "output": '''Provide the score, a concise justification, and the strongest evidence 
        from the collaboration artifacts. Distinguish between quantity of collaboration and meaningful impact.''',
    },
}

def get_dimension_prompt(dimension_name: str) -> str: # LOAD prompt only possible after 1st register
    prompt = DIMENSION_PROMPT_TEMPLATE.format(dimension=DIMENSION_PLACEHOLDERS[dimension_name]["dimension"],
                                              assess=DIMENSION_PLACEHOLDERS[dimension_name]["assess"],
                                              scoring=DIMENSION_PLACEHOLDERS[dimension_name]["scoring"],
                                              output=DIMENSION_PLACEHOLDERS[dimension_name]["output"])
    return prompt + "\nStudent Artifacts:\n{{ bundle_data }}\n"  # Append the bundle_data placeholder at the end
    # return DIMENSION_PROMPT_TEMPLATE + "\nStudent Artifacts:\n{{ bundle_data }}\n"

def register_dimension_prompt(dimension_name: str, model_name: str, bundle) -> None:
    try:
        # Register prompt in MLflow Prompt Registry for versioning and tracking
        prompt = register_prompt(
            name=f"Evaluate_{dimension_name}",
            template=get_dimension_prompt(dimension_name),
            commit_message=f"Prompt for dimension '{dimension_name}' evaluation",
            tags={
                "dimension": dimension_name,
                "model": model_name,
                "team_id": bundle.team_id,
                "sprint_id": bundle.sprint_id,
                "author": "SprintSight"
            }
        )
        prompt_alias = "production" # Set newly registered prompt as Production for now
        set_prompt_alias(f"Evaluate_{dimension_name}", prompt_alias, prompt.version)  # Set alias for the prompt version
    except Exception as e:
        raise RuntimeError(f"Failed to register prompt for dimension '{dimension_name}': {e}")

def load_dimension_prompt(dimension_name: str, alias: str = "production") -> str:
    try:
        return load_prompt(f"prompts:/Evaluate_{dimension_name}@{alias}")
    except Exception as e:
        print(f"Error loading prompt for dimension '{dimension_name}': {e}")
        return None  # Return None if prompt not found or any error occurs