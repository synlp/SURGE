# Unified 标准中间层规范

版本：`1.0.0`

## 文件组织

```text
data/unified/<event_id>/
├── posts.jsonl
├── interactions.jsonl
├── duplicates.jsonl
└── rejects.jsonl

data/reports/<source_name>_quality.json
```

所有 JSONL 文件均为 UTF-8 编码，每行一个 JSON 对象。原始数据不会被修改。

## posts.jsonl

每行代表一个独立文本单元，包括主帖、回复或引用帖。

关键标识：

- `post_id`：管线生成的稳定内部 ID；
- `external_id`：平台原始帖子 ID；
- `event_id`：事件标识；
- `content_type`：`root`、`reply` 或 `quote`；
- `parent_id`：直接关联的父帖；
- `root_post_id`：所属根帖；
- `conversation_id`：对话标识。

内容与时间：

- `text`：规范空白后的正文；
- `post_time`：UTC ISO-8601 时间；
- `post_time_raw`：原始时间字符串；
- `lang` / `lang_raw`：规范语言值和原始语言值；
- `content_hash`：规范正文的稳定哈希。

互动快照：

- `like_count`、`reply_count`、`retweet_count`、`quote_count`；
- `view_count` / `view_count_raw`。

溯源：

- `source_adapter`、`source_file`、`source_record_id`；
- `schema_version`、`parse_warnings`。

## interactions.jsonl

每行表示一条有向互动边。`source_post_id` 是发起回复或引用的帖子，`target_post_id` 是被互动的帖子。当前 data9 支持 `reply` 和 `quote`。

## duplicates.jsonl

重复记录不进入 `posts.jsonl`，但保存重复记录、规范记录、匹配方式和来源位置。去重只在同一事件内部进行，同一个平台帖子可以同时属于不同事件。

## rejects.jsonl

当前拒绝原因包括空正文，以及不在指定事件窗口内或缺少有效时间。拒绝对象仍被保存，便于审计和重新处理。

## 隐私边界

Unified 层属于受控中间数据，可以保存用户 ID、昵称和位置快照以支持去重与研究审计，但这些字段不得直接进入公开发布层。SURGE 导出器必须执行匿名化或字段移除。

