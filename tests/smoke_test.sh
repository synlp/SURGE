#!/bin/bash
# Repository smoke test.
#
# Run from the repository root:
#   bash tests/smoke_test.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

echo "=== 1. Event registry ==="
python -c "
from event_config import get_real_events, get_synthetic_events, get_events_by_category, PAPER_CATEGORIES
real = get_real_events()
synth = get_synthetic_events()
assert len(real) == 102, f'expected 102 real events, got {len(real)}'
assert len(synth) == 2, f'expected 2 synthetic events, got {len(synth)}'
counts = {c: len(get_events_by_category(c)) for c in PAPER_CATEGORIES}
expected = {
    'natural_disaster': 17, 'political': 31, 'social_movement': 13,
    'technology': 21, 'sports_entertainment': 20,
}
assert counts == expected, f'category counts {counts} != expected {expected}'
g6  = sum('6H'  in e.available_granularities for e in real)
g12 = sum('12H' in e.available_granularities for e in real)
g1  = sum('1D'  in e.available_granularities for e in real)
assert (g6, g12, g1) == (102, 99, 90), f'coverage {(g6, g12, g1)} != (102, 99, 90)'
print('  registry: 102 / 99 / 90 OK')
"

echo "=== 2. 35-event ID-only extension ==="
python -c "
import hashlib, json, os
from pathlib import Path
manifest = json.load(open('data/events/extension_35_manifest.json'))
assert manifest['event_count'] == 35
assert manifest['lookup_posts'] == 441631
assert manifest['edges'] == 349770
assert manifest['contains_text'] is False
for event in manifest['events']:
    name = event['name']
    assert os.path.isdir(f'data/events/{name}')
    roots = [Path(f'data/events/{name}')]
    for g in ('6H', '12H', '1D'):
        assert os.path.isdir(f'data/events/{name}_{g}')
        roots.append(Path(f'data/events/{name}_{g}'))
    digest = hashlib.sha256()
    for root in roots:
        for path in sorted(p for p in root.rglob('*') if p.is_file()):
            digest.update(path.relative_to('data/events').as_posix().encode())
            digest.update(path.read_bytes().replace(b'\r\n', b'\n'))
    assert digest.hexdigest() == event['release_sha256'], f'hash mismatch: {name}'
print('  extension: 35 events / 441,631 posts / ID-only OK')
"

echo "=== 3. Synthetic demo schema ==="
python -c "
import os
for ev in ['synthetic_tech_keynote', 'synthetic_storm_alert']:
    for g in ['6H', '12H', '1D']:
        d = f'data/synthetic_examples/events/{ev}_{g}'
        assert os.path.isdir(d), f'missing {d}'
        for f in ('comment_count.csv', 'comment_count_normalized.csv',
                  'sentiment_polarity.csv', 'sentiment_polarity_normalized.csv',
                  'normalization.json'):
            assert os.path.exists(os.path.join(d, f)), f'missing {d}/{f}'
    edges = f'data/synthetic_examples/events/{ev}/edges.jsonl'
    assert os.path.exists(edges), f'missing {edges}'
print('  synthetic schema OK')
"

echo "=== 4. Dataloader ==="
python -c "
import numpy as np
from benchmark.data_loader import _impute_split_internal, create_dataloaders

x = np.array([np.nan, 1.0, np.nan, 3.0, np.nan, np.nan, 6.0, np.nan])
y = _impute_split_internal(x)
assert (y == np.array([1, 1, 1, 3, 3, 3, 6, 6])).all(), f'unexpected: {y}'

loaders = create_dataloaders(
    data_dir='data/synthetic_examples/events',
    interval='1D', variable='sentiment_polarity',
    seq_len=4, pred_len=2, batch_size=4,
)
train_l, val_l, test_l, meta = loaders
assert len(meta['event_names']) > 0
xb, yb = next(iter(train_l))
assert not np.isnan(xb.numpy()).any()
assert not np.isnan(yb.numpy()).any()
print('  dataloader OK')
"

echo "=== 5. MAE_reply k thresholds ==="
python -c "
from benchmark.evaluate import MAE_REPLY_K_PERCENTS
assert MAE_REPLY_K_PERCENTS == (5, 10, 20, 50), f'unexpected: {MAE_REPLY_K_PERCENTS}'
print('  k thresholds OK')
"

echo "=== 6. CMA module imports ==="
python -c "
from benchmark.cma.dataset import CMADataset, build_datasets, MAX_TOKENS_PER_BIN
from benchmark.cma.blocks import IntraBinEncoder, TextAuxHead
from benchmark.cma.run_cma import CMAModel, HistoricalFusion
assert MAX_TOKENS_PER_BIN == 9
print('  CMA imports OK')
"

echo "=== 7. Dataloader unit tests ==="
python tests/test_data_loader.py | tail -1

echo "=== 8. Phase D textual artifacts ==="
python -c "
import json, os
selected = json.load(open('tests/phase_d_events.json'))['events']
md = json.load(open('data/events/event_metadata.json'))['events']
gran_map = {e['name']: e['available_granularities'] for e in md}
missing = []
for ev in selected:
    for art in ('edges.jsonl', 'post_id_lookup.jsonl'):
        p = f'data/events/{ev}/{art}'
        if not os.path.exists(p):
            missing.append(p)
    for g in gran_map.get(ev, []):
        p = f'data/events/{ev}_{g}/text_view.jsonl'
        if not os.path.exists(p):
            missing.append(p)
assert not missing, f'missing {len(missing)} artifacts: {missing[:5]}'
print(f'  all {len(selected)} events have textual artifacts')
"

echo
echo "All smoke tests passed."
