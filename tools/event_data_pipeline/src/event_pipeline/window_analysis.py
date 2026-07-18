from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _densest_window(day_counts: Counter[date], days: int) -> dict:
    first = min(day_counts)
    last = max(day_counts)
    cursor = first
    rolling = 0
    for offset in range(days):
        rolling += day_counts[cursor + timedelta(days=offset)]
    best_start = first
    best_count = rolling
    while cursor < last:
        next_start = cursor + timedelta(days=1)
        rolling -= day_counts[cursor]
        rolling += day_counts[next_start + timedelta(days=days - 1)]
        cursor = next_start
        if rolling > best_count:
            best_start = cursor
            best_count = rolling
    return {
        "days": days,
        "start": datetime.combine(best_start, datetime.min.time(), timezone.utc).isoformat().replace("+00:00", "Z"),
        "end": datetime.combine(best_start + timedelta(days=days), datetime.min.time(), timezone.utc).isoformat().replace("+00:00", "Z"),
        "post_count": best_count,
    }


def analyze_event(event_dir: Path, target_posts: int = 50_000) -> dict:
    posts_path = event_dir / "posts.jsonl"
    content_types: Counter[str] = Counter()
    day_counts: Counter[date] = Counter()
    timestamps: list[datetime] = []
    with posts_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            post = json.loads(line)
            when = str(post.get("post_time") or "")
            if not when:
                continue
            instant = _parse_time(when)
            timestamps.append(instant)
            day_counts[instant.date()] += 1
            content_types[str(post.get("content_type") or "unknown")] += 1
    if not timestamps:
        return {"event_id": event_dir.name, "error": "no valid timestamps"}

    total = len(timestamps)
    first = min(timestamps)
    last = max(timestamps)
    peak_day, peak_count = max(day_counts.items(), key=lambda item: (item[1], -item[0].toordinal()))
    windows = {str(days): _densest_window(day_counts, days) for days in (21, 28, 31)}
    recommended = windows["28"]
    recommended["retained_fraction"] = recommended["post_count"] / total
    return {
        "event_id": event_dir.name,
        "total_posts": total,
        "content_types": dict(content_types),
        "first_time": first.isoformat().replace("+00:00", "Z"),
        "last_time": last.isoformat().replace("+00:00", "Z"),
        "calendar_days": (last.date() - first.date()).days + 1,
        "active_days": len(day_counts),
        "peak_day": peak_day.isoformat(),
        "peak_day_posts": peak_count,
        "windows": windows,
        "recommended_window": recommended,
        "target_posts": target_posts,
        "meets_target_full": total >= target_posts,
        "meets_target_28d": recommended["post_count"] >= target_posts,
        "target_gap_28d": max(0, target_posts - recommended["post_count"]),
    }


def analyze_corpus(unified_root: Path, target_posts: int = 50_000) -> dict:
    events = [
        analyze_event(path, target_posts)
        for path in sorted(candidate for candidate in unified_root.iterdir() if candidate.is_dir())
        if (path / "posts.jsonl").exists()
    ]
    valid = [event for event in events if "error" not in event]
    return {
        "event_count": len(events),
        "target_posts": target_posts,
        "events_meeting_target_full": sum(event["meets_target_full"] for event in valid),
        "events_meeting_target_28d": sum(event["meets_target_28d"] for event in valid),
        "total_posts": sum(event["total_posts"] for event in valid),
        "events": events,
    }


def render_markdown(report: dict) -> str:
    lines = [
        "# 事件时间窗口分析",
        "",
        f"- 事件数：{report['event_count']}",
        f"- 标准帖子总量：{report['total_posts']:,}",
        f"- 全周期达到目标：{report['events_meeting_target_full']}",
        f"- 28天窗口达到目标：{report['events_meeting_target_28d']}",
        "",
        "| 事件 | 全量 | 覆盖天数 | 峰值日 | 峰值量 | 最密28天 | 保留率 | 距目标缺口 |",
        "|---|---:|---:|---|---:|---:|---:|---:|",
    ]
    for event in report["events"]:
        if "error" in event:
            lines.append(f"| {event['event_id']} | - | - | - | - | - | - | - |")
            continue
        window = event["recommended_window"]
        lines.append(
            f"| {event['event_id']} | {event['total_posts']:,} | {event['calendar_days']} | "
            f"{event['peak_day']} | {event['peak_day_posts']:,} | {window['post_count']:,} | "
            f"{window['retained_fraction']:.1%} | {event['target_gap_28d']:,} |"
        )
    lines.extend([
        "",
        "说明：推荐窗口是帖子量最高的连续28个UTC自然日，仅作为自动候选；最终事件窗口仍应结合事件发生时间和研究口径确认。",
        "",
    ])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Analyze event coverage and densest time windows")
    parser.add_argument("unified_root", type=Path)
    parser.add_argument("--target-posts", type=int, default=50_000)
    parser.add_argument("--json", dest="json_path", type=Path)
    parser.add_argument("--markdown", type=Path)
    args = parser.parse_args(argv)
    report = analyze_corpus(args.unified_root, args.target_posts)
    if args.json_path:
        args.json_path.parent.mkdir(parents=True, exist_ok=True)
        args.json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.markdown:
        args.markdown.parent.mkdir(parents=True, exist_ok=True)
        args.markdown.write_text(render_markdown(report), encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "events"}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

