"""Which model judges. One definition, read by production and research alike.

`SPRINTSIGHT_JUDGE_MODEL` used to default to "sprintsight-judge-phi" in the production judge
and in the old single-call judge, but to "phi4:14b" in the judge study (evaluation/offline/judge_study/).
Same environment variable, two defaults, so a run with the variable unset judged with
different models depending on which entry point started it, and the resulting numbers were
not comparable.

"sprintsight-judge-phi" is phi4:14b built from models/Modelfile.phi (docker-compose.yaml,
hpc/ollama-entrypoint.sh and the README all create it), so it is the same weights with the
context size the judge code expects (it must be listed in schemas/modelname.MODEL_NUM_CTX).
"""

import os

JUDGE_MODEL_ENV = "SPRINTSIGHT_JUDGE_MODEL"
DEFAULT_JUDGE_MODEL = "sprintsight-judge-phi"


def configured_judge_model() -> str:
    """The judge model: the environment variable if set and non-empty, else the default."""
    return os.getenv(JUDGE_MODEL_ENV) or DEFAULT_JUDGE_MODEL
