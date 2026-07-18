# Sentiment processing estimate for 35 events

## Measured workload

| Batch | Events | Records | Text characters | Mean characters |
|---|---:|---:|---:|---:|
| Existing data9 | 20 | 228,690 | 22,396,530 | 97.9 |
| New crawler backup | 15 | 212,941 | 31,951,680 | 150.0 |
| Total | 35 | 441,631 | 54,348,210 | 123.1 |

The server input consists of 45 JSONL shards totaling 125,011,872 bytes (119.22 MiB). English accounts for 354,892 records (80.4%); the remaining records include platform language codes and multilingual/undetermined content.

The estimate is for Qwen3-32B three-class sentiment labeling with a fixed prompt, thinking disabled, short structured output, continuous batching, checkpointed shards, validation, and retry of failed records.

## Known server inventory

The server was rechecked at 2026-07-18 12:59 China Standard Time. It has 8 NVIDIA A40 GPUs with 46,068 MiB VRAM each, 128 logical CPU threads, and about 1 TiB RAM. PyTorch 2.6.0/CUDA 12.6 detects all GPUs. GPU 0 was occupied by another user's process using about 10.1 GiB; GPUs 1–7 were idle. The data filesystem had about 249 GiB free and was 99% used.

The complete shared Qwen3-32B BF16 model is present at `/media/ubuntu/data/share/Qwen3-32B`: 17 safetensors shards totaling about 62 GiB, with tokenizer files present. vLLM, FlashAttention, and DeepSpeed are absent from the base environment; PyTorch, Transformers, and Accelerate are installed.

The GPUs form four NVLink-connected pairs: (0,1), (2,3), (4,5), and (6,7). With GPU 0 currently occupied, the safe preferred layout is three independent Qwen3-32B inference workers using pairs (2,3), (4,5), and (6,7), leaving GPU 1 unused rather than crossing a slow interconnect or interfering with GPU 0. If GPUs 0–1 later become fully available and assigned, a fourth worker can be added.

This layout must first be confirmed by a short calibration; do not install the project inference stack or start the long run without teacher approval and explicit user authorization.

## Hardware-independent throughput estimate

| Sustained end-to-end rate | Inference time | With 15% validation/retry reserve |
|---:|---:|---:|
| 2 posts/s | 61.3 h | 70.5 h |
| 5 posts/s | 24.5 h | 28.2 h |
| 10 posts/s | 12.3 h | 14.1 h |
| 20 posts/s | 6.1 h | 7.1 h |
| 30 posts/s | 4.1 h | 4.7 h |

## Estimate for the 8×A40 host

With the currently available three NVLink pairs and an approved project-specific vLLM environment, estimate **5–10 hours end to end**, and reserve **12 hours**. This assumes thinking is disabled, the model emits only the sentiment label while metadata is added deterministically, and failed/invalid records are retried from checkpoints.

If all four NVLink pairs become available and are assigned, estimate **4–8 hours**. If only two pairs are assigned, estimate **8–16 hours**. If vLLM cannot be installed and the job must use a less efficient Transformers loop, allow **15–40 hours**. The model is already local, so no weight download is required; project-environment setup should be budgeted separately at roughly 0.5–2 hours if dependency installation succeeds normally.

For reporting under the current occupancy snapshot, use: **about 5–10 hours on three assigned 2×A40 workers; request a 12-hour allocation, subject to a 5,000-record calibration.** Replace the estimate after calibration with `441631 / measured_posts_per_second × 1.15`.

This estimate excludes model download and first-time environment installation. It includes ordinary output validation and limited retries, but not a large human-label verification study. Strict SURGE methodology also calls for a stratified human review; that should be scheduled separately.

## Measured calibration on 2026-07-18

The isolated server environment uses vLLM 0.9.2, PyTorch 2.7.0+cu126, and three independent 2xA40 workers on GPU pairs (2,3), (4,5), and (6,7). Each worker has a separate vLLM, TorchInductor, and Triton cache to prevent first-run compilation races.

The initial 5,000-record performance calibration completed with zero generation or schema failures at a combined pure-inference rate of about 151.8 records/second. A second, event-stratified calibration covered all 35 events with 5,161 records and also completed with zero failures at about 139.7 records/second. Its aggregate labels were 1,445 positive, 2,201 neutral, and 1,515 negative.

The full 441,631-record run completed with the same fixed prompt and decoding configuration. It took approximately 42 minutes of inference, produced zero generation failures, and passed full key-set and schema validation. The public SURGE repository states that Qwen3-32B and a documented prompt were used, but does not include the prompt text in the checked-out repository; model and output-schema compatibility are confirmed, while word-for-word prompt identity cannot be claimed. See `SENTIMENT_35_EVENT_COMPLETION.md` for final artifacts and validation results.
