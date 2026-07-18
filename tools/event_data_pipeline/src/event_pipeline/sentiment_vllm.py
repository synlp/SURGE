from __future__ import annotations

import argparse
import json
import os
import re
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


LABEL_SCORES = {"negative": -1.0, "neutral": 0.0, "positive": 1.0}
PROMPT_VERSION = "surge-sentiment-qwen3-v1"
SYSTEM_PROMPT = (
    "Classify the sentiment expressed in the social-media text. "
    "Use positive for favorable or supportive sentiment, negative for unfavorable, "
    "critical, hostile, fearful, or rejecting sentiment, and neutral for factual, "
    "unclear, mixed, or sentiment-free text. Return exactly one lowercase label: "
    "negative, neutral, or positive."
)


def iter_records(paths: Iterable[Path], worker_index: int, worker_count: int, limit: int | None):
    global_index = 0
    for path in sorted(paths):
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                if limit is not None and global_index >= limit:
                    return
                if global_index % worker_count == worker_index:
                    yield json.loads(line)
                global_index += 1


def normalize_label(text: str) -> str | None:
    match = re.search(r"\b(negative|neutral|positive)\b", text.strip().lower())
    return match.group(1) if match else None


def load_completed(path: Path) -> set[tuple[str, str]]:
    completed: set[tuple[str, str]] = set()
    if not path.exists():
        return completed
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            value = json.loads(line)
            completed.add((str(value["event_id"]), str(value["post_id"])))
    return completed


def write_status(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def render_prompt(tokenizer, text: str) -> str:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": text},
    ]
    return tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
        enable_thinking=False,
    )


def run(args: argparse.Namespace) -> dict:
    from transformers import AutoTokenizer
    from vllm import LLM, SamplingParams
    from vllm.sampling_params import GuidedDecodingParams

    input_files: list[Path] = []
    for input_dir in args.input_dir:
        input_files.extend(Path(input_dir).glob("posts-*.jsonl"))
    if not input_files:
        raise FileNotFoundError("no posts-*.jsonl input shards found")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    completed = load_completed(args.output)
    model_path = str(args.model)
    tokenizer = AutoTokenizer.from_pretrained(model_path, local_files_only=True)
    model = LLM(
        model=model_path,
        task="generate",
        tensor_parallel_size=args.tensor_parallel_size,
        dtype="bfloat16",
        max_model_len=args.max_model_len,
        gpu_memory_utilization=args.gpu_memory_utilization,
        trust_remote_code=False,
    )
    sampling = SamplingParams(
        temperature=0.0,
        max_tokens=4,
        guided_decoding=GuidedDecodingParams(choice=list(LABEL_SCORES)),
    )

    started = time.time()
    processed = 0
    failed = 0
    prompt_tokens = 0
    generated_tokens = 0
    label_counts: Counter[str] = Counter()
    batch: list[dict] = []

    def process_batch(rows: list[dict], output_handle) -> None:
        nonlocal processed, failed, prompt_tokens, generated_tokens
        if not rows:
            return
        prompts = [render_prompt(tokenizer, str(row.get("text") or "")) for row in rows]
        results = model.generate(prompts, sampling, use_tqdm=False)
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        for row, result in zip(rows, results, strict=True):
            text = result.outputs[0].text
            label = normalize_label(text)
            prompt_tokens += len(result.prompt_token_ids)
            generated_tokens += len(result.outputs[0].token_ids)
            if label is None:
                failed += 1
                continue
            annotation = {
                "post_id": str(row["post_id"]),
                "event_id": str(row["event_id"]),
                "platform": str(row["platform"]),
                "sentiment": label,
                "sentiment_score": LABEL_SCORES[label],
                "model_name": "Qwen3-32B",
                "model_version": "local-bf16",
                "prompt_version": PROMPT_VERSION,
                "processed_at": now,
                "schema_version": "1.0.0",
            }
            output_handle.write(json.dumps(annotation, ensure_ascii=False, separators=(",", ":")) + "\n")
            processed += 1
            label_counts[label] += 1
        output_handle.flush()
        os.fsync(output_handle.fileno())
        elapsed = max(time.time() - started, 0.001)
        write_status(args.status, {
            "state": "running",
            "worker_index": args.worker_index,
            "worker_count": args.worker_count,
            "processed_this_run": processed,
            "completed_before_resume": len(completed),
            "failed": failed,
            "elapsed_seconds": elapsed,
            "records_per_second": processed / elapsed,
            "prompt_tokens": prompt_tokens,
            "generated_tokens": generated_tokens,
            "label_counts": dict(label_counts),
            "updated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        })

    with args.output.open("a", encoding="utf-8", newline="\n") as output_handle:
        for row in iter_records(input_files, args.worker_index, args.worker_count, args.limit):
            key = (str(row["event_id"]), str(row["post_id"]))
            if key in completed:
                continue
            batch.append(row)
            if len(batch) >= args.batch_size:
                process_batch(batch, output_handle)
                batch.clear()
        process_batch(batch, output_handle)

    elapsed = max(time.time() - started, 0.001)
    final = {
        "state": "completed",
        "worker_index": args.worker_index,
        "worker_count": args.worker_count,
        "processed_this_run": processed,
        "completed_before_resume": len(completed),
        "failed": failed,
        "elapsed_seconds": elapsed,
        "records_per_second": processed / elapsed,
        "prompt_tokens": prompt_tokens,
        "generated_tokens": generated_tokens,
        "label_counts": dict(label_counts),
        "updated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    write_status(args.status, final)
    return final


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Checkpointed Qwen3/vLLM sentiment worker")
    parser.add_argument("--input-dir", action="append", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--status", required=True, type=Path)
    parser.add_argument("--model", required=True, type=Path)
    parser.add_argument("--worker-index", required=True, type=int)
    parser.add_argument("--worker-count", required=True, type=int)
    parser.add_argument("--tensor-parallel-size", type=int, default=2)
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--max-model-len", type=int, default=1024)
    parser.add_argument("--gpu-memory-utilization", type=float, default=0.90)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not 0 <= args.worker_index < args.worker_count:
        raise SystemExit("worker-index must be in [0, worker-count)")
    result = run(args)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["failed"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
