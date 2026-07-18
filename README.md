# SURGE: Social-media Unified Reaction-Graph Event dataset

Project page: https://synlp.github.io/SURGE/

Companion repository for the dataset paper *SURGE: an event-centric
social media benchmark pairing sentiment time series with bin-aligned
text and reply / repost interaction structure*.

## Data layout

The dataset covers two paper targets — Discussion Intensity
($c_t = |\mathcal{P}_t|$) and Sentiment Polarity ($\bar{s}_t$) — at
three temporal granularities. Each event-granularity directory
contains four CSV variants and one normalization JSON:

```
data/events/<event_name>_<granularity>/
├── comment_count.csv                    # DI, raw (NaN for empty bins)
├── comment_count_normalized.csv         # DI, per-event z-score (NaN preserved)
├── sentiment_polarity.csv               # SP, raw
├── sentiment_polarity_normalized.csv    # SP, per-event z-score
├── normalization.json                   # train-split-only statistics
└── text_view.jsonl                      # per-bin top-3 main + earliest-2 replies (post-IDs)

data/events/<event_name>/
├── edges.jsonl                          # reply / repost edges (post-IDs, ISO times)
└── post_id_lookup.jsonl                 # post_id -> (platform, url) for hydration
```

Bins with zero observed posts are encoded as `NaN`. The benchmark
loader performs split-internal forward fill followed by backward fill
within each chronological 70 / 10 / 20 segment, so no imputation
reference crosses a split boundary. Field-level documentation lives
in `schema/`.

The release covers 67 events at `6H`, 64 events at `12H`, and 55
events at `1D`. The full event registry is
`data/events/event_metadata.json`, also exposed programmatically
through `event_config.py`.

## Quick start

```bash
pip install -r requirements.txt

# Inspect the registry
python -c "from event_config import get_real_events; print(len(get_real_events()))"
# 67

# Load a granularity into the standard pooled train / val / test loaders
python -c "
from benchmark.data_loader import create_dataloaders
train, val, test, meta = create_dataloaders(
    data_dir='data/events', interval='1D',
    variable='sentiment_polarity', seq_len=14, pred_len=7,
)
print('events:', len(meta['event_names']),
      'train/val/test windows:', len(train.dataset), len(val.dataset), len(test.dataset))
"
```

## Repository layout

```
.
├── README.md
├── LICENSE                  MIT for code; CC BY 4.0 for author-created data
├── DATASHEET.md             Datasheet excerpt
├── CHANGELOG.md
├── requirements.txt
├── event_config.py          EventConfig dataclass + 67-event registry loader
├── common/                  Shared schemas, IO and time utilities
├── benchmark/
│   ├── data_loader.py       Per-event dataloader with split-internal imputation
│   ├── train.py             Generic training loop
│   ├── evaluate.py          MAE / MSE / MAE_reply(k%) metrics
│   ├── mae_reply_utils.py   Reply-ratio computation from edges.jsonl
│   └── cma/                 CMA reference probe
│       ├── dataset.py
│       ├── blocks.py
│       └── run_cma.py
├── schema/                  Field-level documentation
├── references/
│   ├── README.md            Pointers to upstream baseline repositories
│   └── code/MM-TSFlib-main/ Vendored MM-TSFlib backbone (MIT)
└── data/
    ├── events/              Per-event released artifacts
    └── synthetic_examples/  Two synthetic mini-events demonstrating the schema
```

## Data processing tools

The independently runnable [`tools/event_data_pipeline/`](tools/event_data_pipeline/)
normalizes supported collected-event formats and builds validated
SURGE-compatible artifacts. Raw source data, model weights, credentials and
generated releases are intentionally excluded from the repository.

## License

See `LICENSE`. Code is MIT; author-created derivative data under
`data/` is CC BY 4.0.

## Citation

A BibTeX entry will be added at camera-ready time.
