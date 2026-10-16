# assets/fonts —— 表现层资产（不入库）

本目录存放**内置中文字体**：

```
BaoCanMouHuiTingShouXieTi2.0-2.ttf      # 50.5 MiB，笔刷手写体
```

## 为什么不入库

- 单文件 50.5 MiB，超过仓库卫生门禁的 5 MiB 阈值，也会让每次克隆都拖着它；
- 它只是表现层资产：缺失时 `ui/renderer.py` 会回退到系统 CJK 字体（微软雅黑 / 黑体 / Noto），
  两种情况都在 stderr **出声**提示，不会静默降级。

## 怎么拿到它

```bash
python tools/fetch_font.py            # 下载到本目录（默认取本仓 Gitee Release 附件）
python tools/fetch_font.py --check    # 只检查是否就位（不联网）
python tools/fetch_font.py --url <URL>   # 换来源；也支持环境变量 TAVERN_ROGUE_FONT_URL
```

指纹（与入库版本逐字节一致）：

```
size    52976164 字节
sha256  3d2f79b0a942fbc1b7f500ec0688549dcbc667da68e1f79661e3625540aee15f
```

脚本会校验指纹；不一致会丢弃文件并报错（避免"下了个坏文件却以为好了"）。
手工放置也可以：把同名字体直接拷进本目录即可。

## 换字体

查找顺序是「`assets/fonts/` → 仓根同名文件 → 系统 CJK 字体 → pygame 默认字体」。
想换字体就把文件放进本目录并改 `ui/renderer.py` 的 `FONT_FILENAME`。
