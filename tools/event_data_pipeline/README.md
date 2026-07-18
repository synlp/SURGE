# Event Data Pipeline

一个独立于 SURGE 仓库的、多平台事件型社交媒体数据处理工程。

本工程负责把不同来源的原始采集数据转换为统一、可审计、可复现的数据中间层，并进一步生成兼容 SURGE 数据规范的分析产物。

## 项目边界

本工程负责：

- 接入 X、Reddit、Threads 及其他来源的原始数据；
- 统一帖子、回复、引用、转发和评论结构；
- 保存原始记录、来源和处理版本，保证可追溯；
- 去重、字段清洗、质量过滤与事件窗口裁剪；
- 生成帖子级情感记录；
- 按 6H、12H、1D 生成讨论量和情感时间序列；
- 生成代表文本视图、互动关系图和质量报告；
- 导出兼容 SURGE 的派生数据，但不修改 SURGE 仓库。

本工程暂不负责：

- SURGE 预测模型本身的训练和修改；
- 将用户认证信息写入代码或版本库；
- 绕过平台访问控制、验证码、robots.txt 或限流；
- 把受限原始正文直接作为公开发布数据。

## 三层数据组织

```text
Raw 原始层
  ↓ 平台适配与字段标准化
Unified 标准中间层
  ↓ 去重、过滤、情感、时间分箱、匿名化
Release/Analysis 派生层
```

建议目录：

```text
event_data_pipeline/
├── README.md
├── docs/
│   ├── PROJECT_SCOPE.md
│   └── SURGE_COMPATIBILITY.md
├── src/event_pipeline/
│   └── __init__.py
├── tests/
├── configs/
├── data/
│   ├── raw/
│   ├── unified/
│   ├── release/
│   └── reports/
└── .gitignore
```

## 目标数据流

```text
data9 / 新采集数据 / 其他成员原始数据
→ 平台适配器
→ UnifiedPost + UnifiedInteraction
→ 去重与质量过滤
→ 事件生命周期裁剪
→ SentimentRecord
→ 6H / 12H / 1D 聚合
→ SURGE 兼容发布文件与审计报告
```

## 第一阶段验收对象

先使用 data9 的 20 个事件验证完整转换过程：

- 全部事件能够解析，异常记录可追踪；
- 生成统一帖子与互动边；
- 明确主帖、回复、引用、评论等统计口径；
- 给出去重前后数量和字段完整性报告；
- 支持按指定的三周至一个月窗口裁剪；
- 生成可继续用于时间分箱和模型分析的标准中间数据。

