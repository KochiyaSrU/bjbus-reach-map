# bjbus-reach-map — 北京公交 60 分钟可达图

给任意一个北京公交站，生成"一小时、最多换乘一次"的可达范围地图。

- `SKILL.md` — 给 AI agent 读的技能说明（何时用、怎么调、坑在哪）
- `make_map.py` — 一条命令跑完全流程
- `scripts/` — 完整管线（抓取 / 时间模型 / 出图 / 导出）
- `poi.json` — 片区名与地标库（自动只画真正可达的）
- `reference/PROCESS.md` — 全流程与所有踩过的坑（改代码前必读）

## 快速开始

```bash
python make_map.py --origin "西苑" --out "D:\out\西苑60分钟可达" --shp xiyuan_60min
```

输出：总图 PNG、核心区放大 PNG、站点明细 CSV、GeoJSON、Shapefile（WGS84）。

## 换一台机器 / 交给别的 AI

1. 整个文件夹拷过去（脚本 + poi.json + reference 一起）
2. 依赖：Python 3 + numpy / scipy / matplotlib / Pillow；可选 arcpy 10.8（只影响 shapefile）
3. 能访问 `https://bjbus.jinzihao.me/sse`
4. 放进目标 agent 的 skills 目录（任意一个会被扫描的 `skills/` 路径），
   或直接把 `SKILL.md` 的内容作为系统提示，让它按里面的命令调用 `make_map.py`

## 首次运行注意

- 底图瓦片要现下（几百张，1–3 分钟）；之后的图复用缓存，很快
- 数据缓存默认在 `D:\Workspace\bjbus\cache`（`make_map.py` 里的 `engine` 常量），
  换机器要改这个路径，或者留空让它自建
- 抓取并发别超过 5，否则服务端会 503；`fill_gentle.py` 是单线程退避兜底

## 验证当前环境是否正常

```bash
python scripts/qa_offset.py     # 输出 dx=0, dy=0 说明坐标基准对齐
```

---

作者：极地东风谷（KochiyaSrU）
