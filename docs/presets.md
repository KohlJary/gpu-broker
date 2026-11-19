# Presets

Catalog entries for the programs that most often share a home GPU. Each preset knows the program's
default port, a health path, where it reports being busy, and the words its units and containers
carry. Print one, check it, paste it into your catalog:

```sh
gpu-broker preset                                   # list them
gpu-broker preset acestep --unit acestep.service    # a service
gpu-broker preset ollama --unit ollama.service --served-name llama3.1:8b --key llama31
```

The printed entry has already passed the catalog's own checks. `--port` overrides the default port.
LLM servers need `--served-name`: the model the server loads.

**Verified** means it has been run against a broker on a real card (a 16 GB NVIDIA card shared by
Ollama, ComfyUI and ACE-Step). Everything else comes from the program's own docs and source,
linked below, and hasn't been run against a broker yet. If you run one, open an issue or PR saying
how it went.

A program with no busy signal still works: its session lasts until the client ends it
(`POST /v1/sessions/end`) or it reaches `session_max_s`. Services that only count work in
Prometheus format use `busy_metrics` (see [catalog.md](catalog.md#services)).

| preset | program | runner | port | busy signal | verified | needs / notes |
|---|---|---|---|---|---|---|
| `ollama` | Ollama | llm_unit | 11434 | none | **yes** | One server for many models: give each model its own entry on the same unit. [source](https://github.com/ollama/ollama/blob/main/docs/faq.mdx) [source](https://github.com/ollama/ollama/blob/main/docs/linux.mdx) |
| `llama-cpp` | llama.cpp server | llm_unit | 8080 | none | no | Current master defaults to port 9931 (older builds and the Docker examples use 8080): pass --port to match. /health is 503 while the model loads. [source](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md) |
| `vllm` | vLLM | llm_unit | 8000 | none | no | Takes 92-100% of the card by default (gpu_memory_utilization), whatever the model: set it lower, or expect it to need the whole card. [source](https://github.com/vllm-project/vllm/blob/main/docs/getting_started/quickstart.md) [source](https://github.com/vllm-project/vllm/blob/main/vllm/config/cache.py) |
| `lm-studio` | LM Studio (headless) | llm_unit | 1234 | none | no | Has no health route; /v1/models answers once it is up. [source](https://lmstudio.ai/docs/developer/core/headless_llmster) |
| `comfyui` | ComfyUI | comfy | 8188 | none | **yes** | Set comfy.url in the config; this entry lends it the whole card in a session. [source](https://github.com/comfyanonymous/ComfyUI/blob/master/server.py) |
| `automatic1111` | Stable Diffusion WebUI (AUTOMATIC1111) | service | 7860 | `/sdapi/v1/progress` `state.job_count` | no | needs --api (or --nowebui) [source](https://github.com/AUTOMATIC1111/stable-diffusion-webui/blob/master/modules/api/api.py) [source](https://github.com/AUTOMATIC1111/stable-diffusion-webui/blob/master/modules/shared_state.py) |
| `forge` | Stable Diffusion WebUI Forge | service | 7860 | `/sdapi/v1/progress` `state.job_count` | no | needs --api (or --nowebui); Same API as AUTOMATIC1111; that its progress fields match is assumed, not checked. [source](https://github.com/lllyasviel/stable-diffusion-webui-forge/blob/main/modules/api/api.py) |
| `invokeai` | InvokeAI | service | 9090 | `/api/v1/queue/default/status` `queue.pending`, `queue.in_progress` | no |  [source](https://github.com/invoke-ai/InvokeAI/blob/main/invokeai/app/api/routers/session_queue.py) |
| `fooocus` | Fooocus | service | 7865 | none | no | Gradio only: no API, no busy signal, so a session lasts until it's ended or hits the cap. In long-term support (bug fixes only). [source](https://github.com/lllyasviel/Fooocus/blob/main/launch.py) |
| `kokoro-fastapi` | Kokoro-FastAPI (TTS) | service | 8880 | `/dev/model` `active_requests` | no | needs ALLOW_DEV_UNLOAD=true for the busy signal; /health is always 200 (alive, not ready). Without the flag /dev/model is 403: no busy signal. [source](https://github.com/remsky/Kokoro-FastAPI/blob/master/api/src/routers/development.py) |
| `speaches` | Speaches (faster-whisper STT/TTS) | service | 8000 | none | no | No busy signal; /health is always 200. Clients should end their sessions. [source](https://github.com/speaches-ai/speaches/blob/master/src/speaches/routers/misc.py) |
| `whisper-cpp` | whisper.cpp server | service | 8080 | none | no | Same default port as llama.cpp's older builds. /health is 503 while loading. No busy signal. [source](https://github.com/ggml-org/whisper.cpp/blob/master/examples/server/server.cpp) |
| `alltalk` | AllTalk TTS (XTTS and others) | service | 7851 | none | no | No busy signal. Gradio UI on 7852. [source](https://github.com/erew123/alltalk_tts/blob/alltalkbeta/tts_server.py) |
| `acestep` | ACE-Step API (music) | service | 8001 | `/v1/stats` `data.queue_size`, `data.jobs.running` | **yes** |  [source](https://github.com/ace-step/ACE-Step-1.5/blob/main/docs/en/API.md) |
| `tei` | text-embeddings-inference | service | 3000 | metrics: `te_queue_size` | no | The Docker image listens on 80 (usually mapped to 8080). te_queue_size counts waiting requests, not the batch in flight. [source](https://github.com/huggingface/text-embeddings-inference/blob/main/router/src/http/server.rs) |
| `immich-ml` | Immich machine learning | service | 3003 | none | no | No busy signal. It unloads idle models itself (MACHINE_LEARNING_MODEL_TTL, 300 s). [source](https://github.com/immich-app/immich/blob/main/machine-learning/immich_ml/main.py) |

Facts as of 2026-11-19. Programs change their defaults (llama.cpp's port did); when one differs on
your machine, override it rather than trusting the table.
