# Third-party reference implementations

## Vendored

The MM-TSFlib backbone is vendored here because the CMA reference probe
(`benchmark/cma/run_cma.py`) imports its Transformer encoder and
calendar-time-feature helper. The 36 MB demo `data/` directory in the
upstream copy has been stripped.

| Subdirectory | Upstream | License |
|---|---|---|
| `code/MM-TSFlib-main/` | https://github.com/AdityaLab/MM-TSFlib | MIT |

## Pointer-only baselines

| Baseline | Upstream repository |
|---|---|
| MM-TSF | https://github.com/AdityaLab/MM-TSFlib |
| CAMEF | https://github.com/yumoxu/CAMEF |
| GPT4MTS | https://github.com/microsoft/GPT4MTS |
| RAHE | https://github.com/Jingya-Wang/RAHE |
| GPT4TS | https://github.com/DAMO-DI-ML/NeurIPS2023-One-Fits-All |
| ConvTimeNet | https://github.com/Mingyue-Cheng/ConvTimeNet |
| TimesNet | https://github.com/thuml/Time-Series-Library |
| iTransformer | https://github.com/thuml/iTransformer |
| PatchTST | https://github.com/yuqinie98/PatchTST |
| DLinear | https://github.com/cure-lab/LTSF-Linear |
| TimeDiff | https://github.com/PaddlePaddle/PaddleSpatial/tree/main/research/D3VAE |
| NsDiff | https://github.com/wenhao-li-iup/NsDiff |
