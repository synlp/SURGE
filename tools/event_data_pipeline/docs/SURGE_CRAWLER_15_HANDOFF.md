# SURGE crawler 15-event processing handoff

## Immutable backup

- Backup root: `data/raw/surge_crawler_15_backup_20260718/`
- Selection policy: only the verified snapshot referenced by each event's `latest.json`
- Events: 15
- Verified snapshot bytes: 1,163,559,550
- Backup index: `backup_index.json`
- Per-file SHA-256 mismatches after copy: 0

The backup includes raw JSONL, SQLite checkpoints, Unified data, runtime/quality reports, and snapshot manifests. It is restricted source data and must not be used as the processing output directory.

## Processing copy and outputs

- Unified processing copy: `data/surge_crawler_15/unified/`
- Source event catalog: `data/surge_crawler_15/source_event_catalog.json`
- Window report: `data/surge_crawler_15/reports/event_window_analysis.json`
- SURGE output: `data/surge_crawler_15/release/surge/events/`
- Sentiment input: `data/surge_crawler_15/sentiment/input/v1/`
- Readiness report: `data/surge_crawler_15/reports/SENTIMENT_READINESS.json`

The 15 Unified events contain 213,552 posts and 141,386 accepted edges. The crawler-catalog `[since, until)` windows retain 212,941 posts and 140,795 edges. All 15 events and all 45 event-granularity directories pass the non-sentiment release validator.

The sentiment input contains 212,941 records in 22 shards. Shard hashes cover the exact on-disk bytes. Input fields are limited to `post_id,event_id,platform,text,lang,post_time`.

Three events are below 10,000 posts in the selected window: E003 (3,842), E057 (6,245), and E065 (8,700). Categories are provisional mappings into SURGE's five-category taxonomy and should receive project-owner review.

## Sentiment return

After complete server annotations are returned, run:

```powershell
python -m event_pipeline.sentiment_finalize --unified data/surge_crawler_15/unified --release data/surge_crawler_15/release/surge/events --windows data/surge_crawler_15/reports/event_window_analysis.json --input data/surge_crawler_15/sentiment/input/v1 --annotations <server-output-directory>
```

The safe finalizer refuses to write if any `(event_id, post_id)` is missing, duplicated, or unexpected.
