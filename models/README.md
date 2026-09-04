# 本地模型文件

策略 checkpoint 放在本目录对应的子目录中，并由根目录 `.gitignore` 的 `*.pt` 规则忽略。
这样可以避免把数百 MB 的二进制权重写入 Git；迁移项目到新设备时，需要通过受控方式另行
复制经过审查的 `.pt` 文件：

- `go2w/model_700.pt`
- `go2wcr/model_1499.pt`
- `go2wwmp/model_5500.pt`（已通过 strict load 和短闭环）
- `go2wwmp/model_6000.pt`（当前 simulation pipeline 默认，已通过长闭环）

本地也可以保留 `model_1750.pt`、`model_3500.pt` 等其他已审查版本，运行时用
`--model` 显式选择；不要仅凭文件名假定训练配置相同。

代码默认路径已经基于项目根目录解析，不依赖当前终端所在目录。
