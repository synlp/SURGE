from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Protocol


VALID_SENTIMENTS = {"negative": -1.0, "neutral": 0.0, "positive": 1.0}


@dataclass(frozen=True, slots=True)
class SentimentAnnotation:
    post_id: str
    event_id: str
    platform: str
    sentiment: str
    sentiment_score: float
    model_name: str
    model_version: str
    prompt_version: str
    processed_at: str
    schema_version: str = "1.0.0"

    def to_dict(self) -> dict:
        return asdict(self)


class SentimentProvider(Protocol):
    name: str

    def annotate(self, posts: Iterable[dict]) -> Iterable[SentimentAnnotation]: ...


def validate_annotation(value: dict) -> list[str]:
    errors: list[str] = []
    required = {
        "post_id", "event_id", "platform", "sentiment", "sentiment_score",
        "model_name", "model_version", "prompt_version", "processed_at", "schema_version",
    }
    missing = required - value.keys()
    if missing:
        errors.append(f"missing fields: {sorted(missing)}")
        return errors
    sentiment = str(value.get("sentiment") or "")
    if sentiment not in VALID_SENTIMENTS:
        errors.append(f"invalid sentiment: {sentiment}")
    try:
        score = float(value.get("sentiment_score"))
    except (TypeError, ValueError):
        errors.append("sentiment_score is not numeric")
    else:
        if sentiment in VALID_SENTIMENTS and score != VALID_SENTIMENTS[sentiment]:
            errors.append(f"score {score} does not match label {sentiment}")
    for field in ("post_id", "event_id", "platform", "model_name", "model_version", "prompt_version", "processed_at"):
        if not str(value.get(field) or "").strip():
            errors.append(f"blank field: {field}")
    return errors


def validate_sentiment_file(path: Path) -> dict:
    errors = []
    seen: set[tuple[str, str]] = set()
    counts = {label: 0 for label in VALID_SENTIMENTS}
    records = 0
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            records += 1
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                errors.append(f"line {line_number}: {exc.msg}")
                continue
            row_errors = validate_annotation(value)
            errors.extend(f"line {line_number}: {error}" for error in row_errors)
            key = (str(value.get("event_id") or ""), str(value.get("post_id") or ""))
            if key in seen:
                errors.append(f"line {line_number}: duplicate event/post key")
            seen.add(key)
            label = str(value.get("sentiment") or "")
            if label in counts:
                counts[label] += 1
    return {
        "valid": not errors,
        "records": records,
        "label_counts": counts,
        "error_count": len(errors),
        "errors": errors,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate model-produced sentiment annotations")
    parser.add_argument("annotations", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)
    report = validate_sentiment_file(args.annotations)
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(rendered, encoding="utf-8")
    print(rendered)
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

