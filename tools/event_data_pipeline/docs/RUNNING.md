# 运行说明

当前版本提供 data9 ZIP 到 Unified 中间层的流式转换。

```powershell
$env:PYTHONPATH = "src"
python -m event_pipeline convert-data9 `
  --input "D:\path\to\data9.zip" `
  --output "data\unified"
```

可选参数：

- `--event <event_id>`：只处理指定事件，可重复传入；
- `--start <ISO time>`：事件窗口起点，包含；
- `--end <ISO time>`：事件窗口终点，不包含；
- `--dedupe-text`：平台帖子 ID 去重后，额外执行同事件精确正文去重。

转换结果包括标准帖子、互动边、重复记录、拒绝记录及聚合质量报告。输出格式见 `UNIFIED_SCHEMA.md`。

运行测试：

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -v
```

