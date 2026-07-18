# SURGE 兼容层

## 定位

SURGE 是本工程的一个导出目标，而不是运行时依赖。本工程的标准中间数据应当能够独立存在，也应允许未来增加其他发布范式或分析任务。

## 标准中间对象

### UnifiedPost

```text
post_id, platform, event, text, post_time, user_id,
like_count, reply_count, retweet_count, post_url, title,
source_file, source_record_id, crawl_run_id, is_main_post
```

### UnifiedInteraction

```text
source_post_id, target_post_id, interaction_type,
source_time, target_time, source_user_id, target_user_id
```

### SentimentRecord

```text
post_id, event, platform, sentiment, sentiment_score,
model_name, model_version, prompt_version, processed_at
```

## SURGE 导出目录

```text
data/release/surge/events/<event>_<granularity>/
├── comment_count.csv
├── comment_count_normalized.csv
├── sentiment_polarity.csv
├── sentiment_polarity_normalized.csv
├── normalization.json
└── text_view.jsonl

data/release/surge/events/<event>/
├── edges.jsonl
└── post_id_lookup.jsonl
```

## 兼容规则

- 事件 ID 使用小写 snake_case；
- 时间内部统一为 UTC；
- 支持 6H、12H、1D 时间箱；
- 空时间箱保留为 NaN；
- 标准化统计只使用训练时间段；
- 文本视图每箱最多 3 条主帖，每条最多 2 条回复；
- 互动类型为 reply、retweet、quote、comment；
- 公开导出不得包含直接用户身份字段；
- 每次导出必须附带配置、处理版本和质量报告。

