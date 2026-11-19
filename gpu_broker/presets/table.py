"""The preset table. Facts are from each program's own docs or source (linked), as of 2026-11-19;
`verified` ones were run against a broker on a 16 GB card. Pure data."""
from __future__ import annotations

from ..constants import Kind, Runner
from . import Preset

GH = "https://github.com/"

PRESETS: tuple[Preset, ...] = (
    # ---- LLM servers (runner llm_unit: the broker pools their calls itself) ----
    Preset("ollama", "Ollama", Runner.LLM_UNIT, 11434, health_path="/api/version", kind=Kind.LLM,
           words=("ollama",), verified=True,
           notes="One server for many models: give each model its own entry on the same unit.",
           sources=(GH + "ollama/ollama/blob/main/docs/faq.mdx", GH + "ollama/ollama/blob/main/docs/linux.mdx")),
    Preset("llama-cpp", "llama.cpp server", Runner.LLM_UNIT, 8080, kind=Kind.LLM,
           words=("llama-server", "llama.cpp", "llama-cpp"),
           notes="Current master defaults to port 9931 (older builds and the Docker examples use 8080): "
                 "pass --port to match. /health is 503 while the model loads.",
           sources=(GH + "ggml-org/llama.cpp/blob/master/tools/server/README.md",)),
    Preset("vllm", "vLLM", Runner.LLM_UNIT, 8000, kind=Kind.LLM, words=("vllm",),
           notes="Takes 92-100% of the card by default (gpu_memory_utilization), whatever the model: "
                 "set it lower, or expect it to need the whole card.",
           sources=(GH + "vllm-project/vllm/blob/main/docs/getting_started/quickstart.md",
                    GH + "vllm-project/vllm/blob/main/vllm/config/cache.py")),
    Preset("lm-studio", "LM Studio (headless)", Runner.LLM_UNIT, 1234, health_path="/v1/models", kind=Kind.LLM,
           words=("lmstudio", "lms"), notes="Has no health route; /v1/models answers once it is up.",
           sources=("https://lmstudio.ai/docs/developer/core/headless_llmster",)),

    # ---- image ----
    Preset("comfyui", "ComfyUI", Runner.COMFY, 8188, health_path="/system_stats", words=("comfyui", "comfy"),
           verified=True, notes="Set comfy.url in the config; this entry lends it the whole card in a session.",
           sources=(GH + "comfyanonymous/ComfyUI/blob/master/server.py",)),
    Preset("automatic1111", "Stable Diffusion WebUI (AUTOMATIC1111)", Runner.SERVICE, 7860,
           health_path="/internal/ping", busy_path="/sdapi/v1/progress", busy_fields=("state.job_count",),
           words=("stable-diffusion-webui", "sd-webui", "a1111"), needs="--api (or --nowebui)",
           sources=(GH + "AUTOMATIC1111/stable-diffusion-webui/blob/master/modules/api/api.py",
                    GH + "AUTOMATIC1111/stable-diffusion-webui/blob/master/modules/shared_state.py")),
    Preset("forge", "Stable Diffusion WebUI Forge", Runner.SERVICE, 7860,
           health_path="/internal/ping", busy_path="/sdapi/v1/progress", busy_fields=("state.job_count",),
           words=("forge", "stable-diffusion-webui-forge"), needs="--api (or --nowebui)",
           notes="Same API as AUTOMATIC1111; that its progress fields match is assumed, not checked.",
           sources=(GH + "lllyasviel/stable-diffusion-webui-forge/blob/main/modules/api/api.py",)),
    Preset("invokeai", "InvokeAI", Runner.SERVICE, 9090, health_path="/api/v1/app/version",
           busy_path="/api/v1/queue/default/status", busy_fields=("queue.pending", "queue.in_progress"),
           words=("invokeai", "invoke-ai"),
           sources=(GH + "invoke-ai/InvokeAI/blob/main/invokeai/app/api/routers/session_queue.py",)),
    Preset("fooocus", "Fooocus", Runner.SERVICE, 7865, health_path="/", words=("fooocus",),
           notes="Gradio only: no API, no busy signal, so a session lasts until it's ended or hits the cap. "
                 "In long-term support (bug fixes only).",
           sources=(GH + "lllyasviel/Fooocus/blob/main/launch.py",)),

    # ---- speech ----
    Preset("kokoro-fastapi", "Kokoro-FastAPI (TTS)", Runner.SERVICE, 8880, busy_path="/dev/model",
           busy_fields=("active_requests",), words=("kokoro",), needs="ALLOW_DEV_UNLOAD=true for the busy signal",
           notes="/health is always 200 (alive, not ready). Without the flag /dev/model is 403: no busy signal.",
           sources=(GH + "remsky/Kokoro-FastAPI/blob/master/api/src/routers/development.py",)),
    Preset("speaches", "Speaches (faster-whisper STT/TTS)", Runner.SERVICE, 8000, words=("speaches", "faster-whisper"),
           notes="No busy signal; /health is always 200. Clients should end their sessions.",
           sources=(GH + "speaches-ai/speaches/blob/master/src/speaches/routers/misc.py",)),
    Preset("whisper-cpp", "whisper.cpp server", Runner.SERVICE, 8080, words=("whisper-server", "whisper.cpp"),
           notes="Same default port as llama.cpp's older builds. /health is 503 while loading. No busy signal.",
           sources=(GH + "ggml-org/whisper.cpp/blob/master/examples/server/server.cpp",)),
    Preset("alltalk", "AllTalk TTS (XTTS and others)", Runner.SERVICE, 7851, health_path="/api/ready",
           words=("alltalk",), notes="No busy signal. Gradio UI on 7852.",
           sources=(GH + "erew123/alltalk_tts/blob/alltalkbeta/tts_server.py",)),

    # ---- music, embeddings, home ----
    Preset("acestep", "ACE-Step API (music)", Runner.SERVICE, 8001, busy_path="/v1/stats",
           busy_fields=("data.queue_size", "data.jobs.running"), words=("acestep", "ace-step"), verified=True,
           sources=(GH + "ace-step/ACE-Step-1.5/blob/main/docs/en/API.md",)),
    Preset("tei", "text-embeddings-inference", Runner.SERVICE, 3000, busy_path="/metrics",
           busy_metrics=("te_queue_size",), words=("text-embeddings-inference", "tei"),
           notes="The Docker image listens on 80 (usually mapped to 8080). te_queue_size counts waiting "
                 "requests, not the batch in flight.",
           sources=(GH + "huggingface/text-embeddings-inference/blob/main/router/src/http/server.rs",)),
    Preset("immich-ml", "Immich machine learning", Runner.SERVICE, 3003, health_path="/ping",
           words=("immich-machine-learning", "immich_machine_learning"),
           notes="No busy signal. It unloads idle models itself (MACHINE_LEARNING_MODEL_TTL, 300 s).",
           sources=(GH + "immich-app/immich/blob/main/machine-learning/immich_ml/main.py",)),
)
