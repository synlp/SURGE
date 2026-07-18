# data9 全量本地化与转换结果

日期：2026-07-13

## 原始文件

- 本地路径：`data/raw/data9/data9(1).zip`
- 文件大小：35,995,727 字节
- SHA-256：`60bee1d4a5075a6e9275dfeede3b27fde3a139372ac3fd1180bd0ffc734544c9`
- 事件数：20

原始 ZIP 保留不变，转换程序直接流式读取 ZIP，不要求解压为 20,024 个小文件。

## Unified 转换

| 指标 | 数量 |
|---|---:|
| 输入文本记录 | 248,704 |
| 接受的唯一帖子 | 248,471 |
| 同事件重复记录 | 233 |
| 拒绝记录 | 0 |
| 互动边 | 228,674 |

重复记录没有静默删除，其映射保存在各事件的 `duplicates.jsonl` 中。

## 一致性验证

- 验证事件：20；
- 验证帖子：248,471；
- 验证互动边：228,674；
- 缺失帖子引用：0；
- 重复帖子 ID：0；
- 重复互动边 ID：0；
- 自环边：0；
- 结构错误：0；
- 最终状态：通过。

## 本地位置

```text
data/raw/data9/data9(1).zip
data/unified/<event>/posts.jsonl
data/unified/<event>/interactions.jsonl
data/unified/<event>/duplicates.jsonl
data/unified/<event>/rejects.jsonl
data/reports/data9_quality.json
data/reports/data9_validation.json
```

Raw、Unified 和 Reports 目录均被 `.gitignore` 排除，不会误提交到代码仓库。

