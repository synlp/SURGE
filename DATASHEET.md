# SURGE Datasheet

This file is a Markdown excerpt of the full datasheet
(Gebru et al., 2021) and partial Data Statement
(Bender & Friedman, 2018) included as an appendix in the SURGE
dataset paper. For all other questions, please consult the
corresponding paper appendix.

## Motivation

SURGE was created as a multi-event social media benchmark that pairs
event-level sentiment time series with bin-aligned text and
reply / repost interaction structure, in order to support
event-driven sentiment forecasting research that is currently
impeded by the absence of such a unified resource.

## Composition

Each instance is one (event, bin) record at a given temporal
granularity. A record contains per-bin numerical targets —
Discussion Intensity ($c_t$, post volume per bin) and Sentiment
Polarity ($\bar{s}_t$, mean of LLM-assigned per-post polarity scores
in the bin) — released in both raw and per-event z-score normalized
form (NaN preserved for empty bins).

The original paper collection contains 67 events covering 817,442 posts,
organized into 67 events at 6-hour granularity, 64 events at 12-hour
granularity, and 55 events at 1-day granularity. A later 35-event,
441,631-post ID-only extension brings the repository release to 102
events and 1,259,073 posts, with coverage of 102 / 99 / 90 events at
6H / 12H / 1D. The lower event
count at larger granularities reflects events whose active period is
too short to satisfy the paper's minimum-bin threshold.

The collection is sampled. From a raw collection of 1,256,816 posts
and 93 candidate events, SURGE retains 67 events and 817,442 posts
after the deduplication and quality filtering pipeline documented
in the paper's data-preprocessing appendix and the active-period
refinement step documented in the paper's time-series-construction
appendix.

The extension distributes derived numerical series, anonymous post IDs,
platform/URL lookup records, interaction edges, and ID-only sampled views.
It does not redistribute social-platform post text.

Bins that contain no posts are kept as missing (`NaN`) in the
released CSV files. The benchmark pipeline imputes them via
split-internal forward fill followed by backward fill within each
chronological 70 / 10 / 20 segment at load time, so no imputation
reference ever crosses a split boundary.

## Collection process

Posts were collected from public timelines of three major social
platforms during the active period of each event. The complete
collection protocol — including event seeding, query construction,
deduplication, language filtering, URL-spam filtering, and
within-event textual deduplication — is documented in the paper's
data-collection and data-preprocessing appendices.

## Preprocessing and labeling

Per-post sentiment polarity is assigned by Qwen3-32B under a
documented prompt. A stratified human verification study on 3,000
posts (200 per category-class cell across the five event categories
and three sentiment classes) is reported in the paper's sentiment
appendix.

The released sentiment series is treated as a reproducible
LLM-derived signal rather than a gold-standard human label.
Downstream users running conflict-related analyses are advised to
pair SURGE's bin-level Sentiment Polarity with stance-specific or
domain-tuned validators.

## Intended uses

SURGE supports public-opinion forecasting, crisis response analysis,
policy-impact assessment, and methods research on combining
numerical signals with text and interaction structure. Misuse for
surveillance, narrative manipulation, or targeted sentiment
intervention is acknowledged in the paper's ethics appendix.

## Licensing

Author-created derivative metadata (per-event time series at three
granularities, normalization statistics, and event metadata) is
released under CC BY 4.0. Benchmark code is released under the MIT
license.

Textual artifacts (`text_view.jsonl`, `edges.jsonl`, and
`post_id_lookup.jsonl`) are released for a subset of events during the
review phase. The full set of textual artifacts for all events will be
released upon paper acceptance.
