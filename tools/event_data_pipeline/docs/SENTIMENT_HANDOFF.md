# 情感标注服务器交接

## 当前状态

非情感处理已经完成。服务器只需读取 `data/sentiment/input/data9_20events_v1/` 下的 JSONL 分片并逐条返回情感标注；不得修改 `post_id`、`event_id` 或 `platform`。

输入字段固定为 `post_id,event_id,platform,text,lang,post_time`。输入包不含用户 ID、昵称、位置、Cookie 或认证头。分片数量、记录数量和 SHA-256 位于同目录 `manifest.json`。

## 输出契约

每条输出必须是一个 JSONL 对象，字段为：

`post_id,event_id,platform,sentiment,sentiment_score,model_name,model_version,prompt_version,processed_at,schema_version`

标签只允许 `negative=-1`、`neutral=0`、`positive=1`。每个 `(event_id, post_id)` 必须恰好出现一次。建议输出文件沿用输入分片编号，方便断点重跑和逐分片核验。

模型、权重版本、提示词版本和解码配置必须在整个批次固定。若要与 SURGE 原数据做严格横向比较，优先使用相同的 Qwen3-32B 标注配置；如果只要求格式兼容，可以更换模型，但必须记录版本并做人工分层抽检。

## 安全回收命令

```powershell
python -m event_pipeline.sentiment_finalize --unified data/unified --release data/release/surge/events --windows data/reports/event_window_analysis.json --input data/sentiment/input/data9_20events_v1 --annotations <服务器输出目录>
```

安全入口会先验证字段、标签分数、重复键，以及输入和输出集合的全量一致性。缺失或多出任何一条时都不会调用写入程序；完整时才生成 60 个目录中的 `sentiment_polarity.csv`、`sentiment_polarity_normalized.csv`，并更新 `normalization.json`。

## 边界说明

技术处理链已经只差情感标注。事件类别目前是 SURGE 五分类下的编辑映射，28 天窗口是自动最高密度窗口；二者仍建议项目负责人做语义审阅。14 个事件在所选窗口少于 10,000 条，这是数据规模问题，不是格式或处理管线缺项。
