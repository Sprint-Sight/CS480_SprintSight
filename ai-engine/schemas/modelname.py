from enum import Enum


class ModelName(str, Enum):
    SPRINTSIGHT_GRADER = "sprintsight-grader"
    SPRINTSIGHT_QWEN = "sprintsight-qwen"
    SPRINTSIGHT_MISTRAL = "sprintsight-mistral"
    SPRINTSIGHT_GEMMA = "sprintsight-gemma"
    SPRINTSIGHT_JUDGE_PHI = "sprintsight-judge-phi"
    # --- Round-2 benchmark models (added alongside the originals for the
    # model-comparison study: larger / specialized, all within 24 GB VRAM). ---
    SPRINTSIGHT_LLAMA31 = "sprintsight-llama31"          # llama3.1:8b — speed/VRAM floor
    SPRINTSIGHT_QWEN25_32B = "sprintsight-qwen25-32b"    # qwen2.5:32b — general 32B
    SPRINTSIGHT_R1_32B = "sprintsight-r1-32b"            # deepseek-r1:32b — reasoning
    SPRINTSIGHT_CODER_32B = "sprintsight-coder-32b"      # qwen2.5-coder:32b — code specialist
    GEMMA4_12B = "gemma4:12b"
    QWEN3_6 = "qwen3.6:latest"
    LLAMA2_7B_CHAT = "llama2:7b-chat"
    LLAMA3_1 = "llama3.1"
    MISTRAL7B = "mistral:7b"

# Must match each model's `PARAMETER num_ctx` in models/Modelfile.* — kept here
# so llm_client.py never has to hardcode a single value for every model.
# Ollama caps num_ctx at the model's own maximum, so these must not exceed it:
# qwen3:8b supports 40960 and mistral:7b 32768 (both seen as `context_length`
# in Ollama's /api/ps; 49152 was configured before and silently capped).
MODEL_NUM_CTX: dict[str, int] = {
    ModelName.SPRINTSIGHT_QWEN.value: 40960,     # models/Modelfile.qwen (qwen3:8b maximum)
    ModelName.SPRINTSIGHT_MISTRAL.value: 32768,  # models/Modelfile.mistral (mistral:7b maximum)
    ModelName.SPRINTSIGHT_GEMMA.value: 49152,    # models/Modelfile.gemma
    ModelName.SPRINTSIGHT_JUDGE_PHI.value: 16384, # models/Modelfile.phi (phi4:14b's trained maximum; Ollama clamps higher values, 49152 ran at 16384)
    # Round-2 benchmark models. Real per-dimension grading prompts were measured
    # at up to ~11.5k tokens (after commit sampling), so 16384 is non-truncating
    # for the current sprints. The 32B models cap at 16384 (vs 49152) because at
    # Q4_K_M (~20 GB) they leave little of a 24 GB GPU for the KV cache — this
    # context needs OLLAMA_KV_CACHE_TYPE=q8_0/q4_0 (see ai-engine/hpc/README.md).
    ModelName.SPRINTSIGHT_LLAMA31.value: 49152,     # models/Modelfile.llama31 (8B, full ctx)
    ModelName.SPRINTSIGHT_QWEN25_32B.value: 16384,  # models/Modelfile.qwen25-32b
    ModelName.SPRINTSIGHT_R1_32B.value: 16384,      # models/Modelfile.deepseek-r1
    ModelName.SPRINTSIGHT_CODER_32B.value: 16384,   # models/Modelfile.qwen25-coder
}

# Characters per token of each model's tokenizer, measured on the same
# 60,000-character slice of a real grading prompt (2026-11-02). The evidence
# packer counts tokens as chars / LLM_CHARS_PER_TOKEN (3.0); a model whose
# tokenizer is denser than that turns a packed prompt into more real tokens,
# and Ollama silently drops the start of a prompt that overflows its context.
# The 32B models are assumed to match qwen (they use the Qwen2.5 tokenizer).
MODEL_CHARS_PER_TOKEN: dict[str, float] = {
    ModelName.SPRINTSIGHT_QWEN.value: 2.81,
    ModelName.SPRINTSIGHT_MISTRAL.value: 2.48,
    ModelName.SPRINTSIGHT_GEMMA.value: 2.69,
    ModelName.SPRINTSIGHT_LLAMA31.value: 3.28,
    ModelName.SPRINTSIGHT_QWEN25_32B.value: 2.81,
    ModelName.SPRINTSIGHT_R1_32B.value: 2.81,
    ModelName.SPRINTSIGHT_CODER_32B.value: 2.81,
}
