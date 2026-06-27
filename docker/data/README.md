# 本地 MILOCO_HOME（挂载到容器 `/data/miloco`）

推荐用**宿主机目录 bind mount**，而不是 Docker 匿名卷：

- 直接编辑 `config.json`、放 ONNX 模型
- `miloco-server` 与 `miloco-agent` 共享同一目录
- 可改为已有目录，例如 `~/.openclaw/miloco`

## 目录结构（运行后自动生成）

```
data/
├── config.json      # API Key、webhook、server token
├── models/          # det_4C.onnx、human_body_reid_v2.onnx 等
├── log/
├── storage/         # SQLite 等
└── trace/
```

## 模型

将 ONNX 放到 `models/`，或首次启动时由镜像内默认模型自动复制（`cp -n`）。

也可软链到仓库内模型目录：

```bash
ln -sf ../../backend/miloco/src/miloco/perception/models models
```
