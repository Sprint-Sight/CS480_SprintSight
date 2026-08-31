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