# Schema: Sampled bin-aligned text views

## Selection rule

For each (event, bin) pair in the released active period, the
construction pipeline keeps:

- the top `K_post = 3` main posts ranked by in-bin reply count (the
  number of replies to the same main post that also fall in the same
  bin), in descending order;
- for each retained main post, the earliest `K_reply = 2` replies in
  chronological order;
- when no main post exists in a bin (a fallback case), the three
  earliest posts in the bin are retained as singleton threads.

Posts with fewer than the threshold of replies are kept as-is. Text
content is truncated to 1,500 characters per post.

## File layout

```
data/events/<event_name>_<granularity>/text_view.jsonl
```

One JSON object per line, one line per bin. Bins outside the active
period are not present; bins inside the active period with zero
observed posts emit a record with empty `main_posts`.

## Per-bin record

```json
{
  "event": "<event_name>",
  "granularity": "<6H|12H|1D>",
  "bin_start": "2026-03-04T00:00:00",
  "bin_end":   "2026-03-04T06:00:00",
  "n_posts_in_bin": 217,
  "main_posts": [
    {
      "post_id": "<anonymized id>",
      "platform": "twitter",
      "post_time": "2026-03-04T01:14:30",
      "text": "...up to 1500 chars...",
      "like_count": 142,
      "reply_count": 19,
      "retweet_count": 5,
      "replies": [
        {
          "post_id": "<anonymized id>",
          "platform": "twitter",
          "post_time": "2026-03-04T01:18:09",
          "text": "...up to 1500 chars...",
          "like_count": 7,
          "reply_count": 2
        }
      ]
    }
  ]
}
```

`post_id` is a stable hash of the upstream post URL or, when no URL is
available, of the platform-namespaced (`platform`, `user_id`,
`post_time`, `text[:200]`) tuple. The hash carries no user-identifying
information by itself.

`n_posts_in_bin` is the number of posts in the bin before sampling.
The length of `main_posts` is at most `K_post = 3`.

## Two textual views derived from the same record

The benchmark consumes two textual views built on top of this record:

- **Flat text** — the selected main posts and replies linearized in
  chronological order, with each post prefixed by a `User<X>:` marker
  and separated by newlines.
- **Structured text** — each main post followed by its own replies
  indented under it, with explicit `said` / `replied` role markers,
  preserving reply-chain structure.

## Anonymization

`post_id` values are stable hashes that do not encode any
user-identifying information. Author handles, profile URLs, contact
details, and geolocation are not present in any released field.
