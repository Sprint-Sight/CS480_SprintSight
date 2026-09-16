from enum import Enum

class ModelName(str, Enum):
    SPRINTSIGHT_GRADER = "sprintsight-grader"
    SPRINTSIGHT_LLAMA = "sprintsight-llama"
    SPRINTSIGHT_QWEN = "sprintsight-qwen"
    SPRINTSIGHT_MISTRAL = "sprintsight-mistral"
    SPRINTSIGHT_GEMMA = "sprintsight-gemma"
    GEMMA4_12B = "gemma4:12b"
    QWEN3_6 = "qwen3.6:latest"
    LLAMA2_7B_CHAT = "llama2:7b-chat"
    LLAMA3_1 = "llama3.1"
    MISTRAL7B = "mistral:7b"

# Must match each model's `PARAMETER num_ctx` in models/Modelfile.* — kept here
# so llm_client.py never has to hardcode a single value for every model.
MODEL_NUM_CTX: dict[str, int] = {
    ModelName.SPRINTSIGHT_LLAMA.value: 49152,   # models/Modelfile.llama
    ModelName.SPRINTSIGHT_QWEN.value: 49152,     # models/Modelfile.qwen
    ModelName.SPRINTSIGHT_MISTRAL.value: 49152,  # models/Modelfile.mistral
    ModelName.SPRINTSIGHT_GEMMA.value: 49152,    # models/Modelfile.gemma
}