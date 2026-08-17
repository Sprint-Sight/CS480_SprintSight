from enum import Enum

class ModelName(str, Enum):
    GEMMA4_12B = "gemma4:12b"
    QWEN3_6 = "qwen3.6:latest"
    LLAMA2_7B_CHAT = "llama2:7b-chat"
    LLAMA3_1 = "llama3.1"
    MISTRAL7B = "mistral:7b"