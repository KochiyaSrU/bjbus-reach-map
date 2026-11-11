# 北京公交可达范围图 · 实现记录与踩坑

> 这是本项目的实现记录：每个问题都写清**现象 → 原因 → 具体怎么改 → 怎么验证**。
> 站点一律用类型表述（城区干道站、线路端点站、山区定班线……），换城市只换名字，坑的形状一样。

---

## 1. 目标与口径

给定一个公交站，在「最多换乘一次、总耗时 ≤ 60 分钟」约束下，算出所有可达站并出图。

```
总耗时 = 候车₁ + 乘车₁ + 换乘步行 + 候车₂ + 乘车₂ ≤ 3600 s
```

- 总图：等时面四档（0–15 / 15–30 / 30–45 / 45–60）+ 站点 + 片区名 + 大枢纽 + 边界站
- 核心区放大图：起点周边 `--core-km`（默认 4.6 km）方形窗口，逐站标注
- 数据：CSV / GeoJSON / Shapefile（WGS84 / CRS84）

---

## 2. 数据源与四个接口

公交实时数据服务（MCP over SSE，需自建客户端：先 GET 拿 endpoint，再 POST JSON-RPC，
响应从 SSE 流回来）。

| 接口 | 内容 | 用途 |
|---|---|---|
| `query_routes_at_stop` | 某站名经过的线路方向（含 `route_id`、`current_stop_number`） | 核对站名、起点展开 |
| `query_route_info_by_route_id` | 站名序列 + 经纬度 + `distance_from_previous_stop` | 坐标、距离 |
| `query_route_timetable` | 每班车到每站的时刻（TSV，**无日期**） | 分段乘车时间 |
| `query_schedules_by_route_id` | 首末站发车时刻 + **服务日期** | 班次数与发车间隔（唯一可靠来源） |

**关键**：`current_stop_number` 是 1-based，起点在该方向的下标 `origin_idx = current_stop_number - 1`。
起点若是终点站，`origin_idx = n-1`，下游 0 站——这条方向对可达集没有任何贡献。

---

## 3. 坐标：两个必须做的转换

### 3.1 GCJ-02 → WGS-84

数据是国内坐标系，底图（Esri/OSM）是国际坐标系。不转换，整片站点会偏移约 300–400 m。

**修法**：在 `model.parse_route_info()` 里对每个坐标调 `gcj.gcj2wgs()`。下游一律用转换后的坐标。
`gcj2wgs` 用迭代法（正算 wgs2gcj 后按残差回推，3–4 次收敛到米级）。

**验证**：`qa_offset.py` 把站点云整体平移，找使"站点落在道路亮像素"最多的位移。

```bash
cd work/<站名> && python qa_offset.py
# overview  n=xxx  best shift dx=+0 dy=+0 px  (0 m E, 0 m N)
```

- 未转换时该值是一个明显的非零偏移（本机上约 −79/+40 px）
- 转换后应为 `dx=0 dy=0`

**注意**：这个判据需要图像有对比度。乡村裁片几乎没有路网时亮度曲面是平的，
扫描会得到一个假偏移。`qa_offset.py` 现在的做法是：可测点少于 12 个就打印
`SKIPPED - NOT checked`，而不是给一个假的 OK。

### 3.2 同名站归并成 medoid

同一站名在数据里有 2–16 个坐标（港湾、上下行、历史版本），相差 50–270 m。直接画会散成一簇。

**修法**（`fix_coords.py`）：

1. 按 **260 m 单链接聚类**（`MERGE_R`），迭代到簇稳定；
2. 每簇取 **medoid**——簇内真实观测点里到其他点中位距离最小的那个；
3. **不要用质心**：质心会落在两个港湾之间的地块里，图上表现为"站点在马路上"。

---

## 4. 时间模型

### 4.1 缺失区段按距离补（`model.cumulative`）

滚动窗口里某班车只记录了部分站点，`seg[i] = None`。

**错误做法**：用该线路其他区段的中位数补。
反例：某条高速快线的 61 km 高速段没有时刻，用中位数补成 3 分钟 → 等效 179 km/h →
60 km 外的城市变成"半小时可达"。

**正确做法**：

```python
cumulative(seg, dists, v_missing=14.0)   # 缺失段 = 距离 / 14 m·s⁻¹ ≈ 50 km/h
```

调用时必须把站间距离传进去：`cumulative(seg, [s["dist"] for s in stops])`。
不传 `dists` 会退化到"全线中位数"，等于又踩一遍上面的坑。

### 4.2 单区段上限放到 2 小时

`parse_timetable` 里过滤异常时刻差：`if 20 <= d <= 7200`。

上限若是 1800 s（30 min），真实的高速段（1 小时以上）会被当异常丢弃，
又回到 4.1 的错误。实测那段是 3681 s。

### 4.3 发车间隔：必须用带日期的班次接口 + 平均间隔

这是踩得最深的一处，是三个坑叠加：

**坑 A — 多服务日混在一起。**
`query_route_timetable` 没有日期列，一条一天 2 班的山区线在窗口里看到 4 行，
实际是「2 班/天 × 2 天」。数行数 → 班次翻倍；用「首末班跨度 ÷（行数−1）」→ 间隔对半。

**坑 B — 同一趟车被记两次。**
滚动窗口在相邻区段重叠，同一班车在重叠站出现两行，两行相隔 10–15 分钟。
不合并，这些伪间隔会把平均间隔拉低一半以上。

**坑 C — 中位数掩盖午间空档。**
车都挤在早晚高峰时，中位数只反映"最密那一段"：某条线真实平均间隔 88 分钟，
中位数只有 15 分钟，相差近 6 倍。

**修法**（`model.headway_from_schedules` + `peak_only_from_schedules`）：

```python
# 1) 按服务日分组
by_day[depart_time[:10]].append(to_secs(depart_time[11:19]))

# 2) 同日内合并重复记录：班次少用 20 分钟容差，班次多用 2 分钟
tol = 1200 if len(raw) < 20 else 120
v = [t for t in sorted(raw) if not v or t - v[-1] > tol]

# 3) 取平均间隔（跨度 ÷ 有效班次），不用中位数
headway = (v[-1] - v[0]) / (len(v) - 1)

# 4) 只有 1 班 → headway 无定义 → 该线路剔除（service_ok 返回 False）
```

**验证**：某条线官方时刻表 9 班、平均 88 分钟，这套算法给出 90 分钟；
拿掉容差合并会得到 53 分钟，改用中位数会得到 15 分钟——两个都是错的。

### 4.4 候车分档（`model.wait_for`）

```python
PLANNED_FROM = 20 * 60      # 20 分钟

def wait_for(headway, default=480.0):
    if headway is None:            return default        # 无数据，按 8 分钟兜底
    if WAIT_MODE == "best":        return 0.0
    if WAIT_MODE == "worst":       return float(headway)
    if headway >= PLANNED_FROM:    return 0.0            # 班次疏：乘客看表坐车
    return headway / 2.0                                 # 密集：随到随走
```

| 线路 | 候车 | 依据 |
|---|---|---|
| 间隔 < 20 min | 间隔 ÷ 2 | 车随到随走，没人看时刻表 |
| 间隔 ≥ 20 min | 0（卡点） | 一天几班，乘客必然看时刻表去坐 |
| 高峰专线（10–15 点无车） | 整条剔除 | 中午没车，不能当全天可用 |
| 夜间线（`夜*`） | 剔除 | 口径是白天 |

**两条都用 `wait_for()`**：第一程在 `leg1.py`，第二程在 `leg2b.py`。
第二程若写成 `hw2 / 2`，≥20 min 的线路会被多算一半候车，而且 `--wait-mode` 对它静默失效。

### 4.5 高峰专线判定要按单个服务日

```python
mid = sum(v for h, v in day_hours.items() if 10 <= h <= 15)
am  = sum(v for h, v in day_hours.items() if 6  <= h <= 9)
pm  = sum(v for h, v in day_hours.items() if 16 <= h <= 19)
peak_only = (mid == 0 and am >= 2 and pm >= 2)
```

**必须先按服务日分组再判**。用多天汇总判，会把"早 1 班 + 晚 1 班 × 2 天"
读成"早 2 + 晚 2"，整条线被误判剔除。实测某郊区枢纽有 17 个方向吃过这个误判。

---

## 5. 抓取

逐跳展开：起点线路 → 候选换乘站 → 换乘站的其他线路。

- **并发**：`net.Limiter` 是共享令牌桶，起始 6 req/s，遇 503 减半、成功回升 5%；
  `leg1/leg2a/leg2b` 用 8 线程。**不要超过 10 线程**——被打到限流后吞吐反而更低。
- **兜底补漏**：`fill_gentle.py` 单线程 + 1.2 s 间隔重试失败项；`net.fetch_many` 失败重试 4 轮。
- **错误响应不能进缓存**（`q.py`）：

```python
if isinstance(out, dict) and str(out.get("_raw_text", "")).startswith("Error calling tool"):
    raise RuntimeError(...)          # 抛异常、不写缓存
```

不这么做，一次 503 的报错会被永久缓存，之后每次都命中同一条错误，而且和"这条线本来没数据"
在报告里长得一模一样（都是 `nruns=0`）。本机清理出过 121 条被污染的错误缓存。

- **换乘展开失败要当硬失败**（`make_map.py`）：`leg2a` 只把失败写进
  `out_leg2_stage_a.json` 的 `stop_route_errors` 就继续，`fill_gentle` 补的是另一份清单，
  结果可能少算几十个站而交付物看起来完全正常（实测少了一半：147 vs 315）。
  现在的做法是：失败数不为 0 就重跑 `leg2a`，仍不为 0 直接 `SystemExit`。

- **两套缓存互不相通**：查询脚本（`scripts/q.py`）的缓存目录和工程目录里 `q.py` 的 `CACHE`
  是两个位置。核对站名时用的缓存对管线无效，同一个 `route_id` 可能拿到两份不同快照。

---

## 6. 出图规则

### 6.1 标注（`render.Placer` + `prune_labels`）

| 规则 | 参数 | 起因 |
|---|---|---|
| 标签不压站点圆点 | `covers_dot(box, r=3.0)` + KDTree | 五个字的站名整块盖住自己的站点 |
| 标签离自己站点有上限 | `MAX_LABEL_OFFSET_PT = 11`（白框 17） | 密集区标签被越推越远，"飘到别的站头上" |
| 标签归属分级 | 中心到本站距离 / 到最近他站距离，比值 < 0.72 放弃 | 一刀切会误删本来能标的 |
| 不许上下叠列 | x 重叠 > 45% 且垂直缝 < 7 px → 删 | 上下紧贴读成一整块 |
| 离画框留边 | `m = 12 px` | 白描边（2 pt）会压到框线 |
| 引线 | 偏移 > 6 px 才画，`lw=0.4, alpha=0.75` | 引线多像蛛网 |
| 边界站空间稀释 | 相邻 < 1200 m 只留一个（按距起点排序） | 同一路口三个站各画一个红圈 |
| 最终去重 | 用 `get_window_extent()` 的**真实包围盒** | 估算字宽对中文永远不准 |

**单位陷阱**：`annotate` 的 `xytext` 是**点**（pt），碰撞检测是像素。两者差 `dpi/72`（200 dpi 时 2.78 倍）。
预留框必须换算到同一单位：

```python
k = self.fig.dpi / 72.0
tx, ty = px + dx * k, py + dy * k
```

混用会让预留框整体偏移，出现"判定通过、实际压上"。

### 6.2 版面（`render.draw`）

| 规则 | 参数 / 做法 | 起因 |
|---|---|---|
| 离散四色 + 离散图例 | 四档固定色，图例画色块 | 连续渐变图例与"图上只有 4 色"对不上 |
| 三层标注 | 片区名（灰大字）/ 大枢纽（白框，≥10 线）/ 边界站（红圈+红字） | 全标会糊 |
| 比例尺自动找空白区 | 网格搜索站点最少处，留 450 m 保护带 | 固定位置必然压某张图的内容 |
| 比例尺长度随图幅 | `cand*1000 <= span/4.2` 取最大候选 | 3×4 km 的图放 5 km 比例尺比图还宽 |
| 层级 | 底色 < 等时面 < 比例尺 < 站点 < 标注（z=4.5/4.6） | 放最上层盖站点，放最下层被标注盖 |
| 比例尺长度 | `km*1000*cos(lat)` | 墨卡托 40°N 放大 1.305 倍 |
| 页脚按英寸定位 | `1.0 - offset/H`，H 是画布高（英寸） | 按比例定位在窄画布上会重叠 |
| 页脚自动缩字号 | `fit_texts()`：量真实宽度，超宽则 `fs*0.93` 循环 8 次 | 长句被右边缘切掉（实测差 98 px） |
| 画布自适应 | `aspect >= 0.85` 用横版，`figw <= 19 in` | 狭长范围用竖版留大片空白 |
| 路网底纹 | 只画 ≤900 m 的相邻段，`alpha=0.15` | 跨区段直线像划痕 |
| 填内部空洞 | `binary_fill_holes` 只填被色块包围的洞 | 大居住区中间留白 |

### 6.3 起点标注（`render.origin_callout`）

```python
def origin_callout(ax, origin, text=u"起点  XXX", dx=26, dy=18, fs=12.5):
    k = ax.figure.dpi / 72.0
    w_px = (len(text) * fs * 1.05 + 18) * k
    if px + dx * k + w_px > bb.x1 - 6:      # 右边放不下
        dx, ha = -dx - w_px * 72.0 / dpi, "right"
    ...
```

调用方式：**先画标注，再量真实包围盒，登记进 `Placer.boxes`**，其他标签才会避让它。

```python
ann = origin_callout(...)
fig.canvas.draw()
b2 = ann.get_window_extent(renderer=r)
pl.add_rect(b2.x0 - 5, b2.y0 - 5, b2.x1 + 5, b2.y1 + 5)
```

三个已知问题：跑出画框（上述翻转）、压住别的标签（上述登记）、压住站点圆点
（`alpha=0.72` 半透明）。

**坑**：整段替换这个函数时，容易把默认站名一起重置成硬编码的旧站名，
结果是所有图的起点都写错。改完要 grep 一遍 `起点` 确认。

---

## 7. 收尾与自检

一次出图必须按顺序跑完，**改完代码要全部重跑**：

```
站名核对 → leg1 → leg2a → fill_gentle → leg2b → fix_coords → export
        → basemap → tiles_core → render → deliver → make_shp → 拷交付
```

`make_map.py` 一条命令做完上面全部。**但重算可达后必须重取底图**（`basemap.py` + `tiles_core.py`），
否则范围变大后图边缘会出现空白条带。

**验收清单**（`scripts/selfcheck.py` 自动查前两条）：

1. 9 个文件齐全——shp/shx/dbf/prj/cpg 缺了不会报错，只打印一行 "arcpy not found - skipping"，
   exit code 仍是 0
2. CSV / GeoJSON / DBF / SHP 记录数一致
3. `qa_offset.py` 打印 `OK`（打印 `SKIPPED` 等于没验）
4. 图上：标签不互压、不压圆点、不被画框裁、比例尺不压内容、起点标注不遮挡
5. 页脚统计数字与表格分类计数一致（直达 + 步行 + 换乘一次 = 总数）

**测试纪律**：只重跑正在验证的那一个站。全量重跑一张城市图 2–5 分钟，十几张就是半小时。

---

## 8. 已覆盖的站点类型

用这套流程跑过 20 多个不同类型的起点，结果 0–2000+ 站：

| 类型 | 典型规模 | 会暴露的问题 | 已处理方式 |
|---|---|---|---|
| 城区干道站（密集线路） | 800–1300 站 | 标签密度、夜间线、候车÷2 | 标签规则 + 夜线剔除 |
| 郊区换乘枢纽 | 300–600 站 | 换乘步行、同名站归并 | 700 m 换乘、medoid |
| 线路端点站（远郊总站） | 几十–几百站 | 一半方向下游 0 站 | 按方向展开，空方向跳过 |
| 山区定班线沿线 | 0–40 站 | 间隔算错、候车吃满预算 | 带日期班次 + 平均间隔 |
| 高峰专线覆盖的站 | — | 中午没车却当全天可用 | 按单日判 peak_only 剔除 |
| 单线村庄站 | 0 站 | 无时刻表数据 | 写 `结果说明.md`，不出图 |

**通用结论**：

- 班次稀疏时 60 分钟预算基本被候车吃光，图上只剩零散几站——模型约定，不是 bug；
- 高速快线制造"跳跃式"可达，图上是孤立色斑，属真实情况；
- 站点很少时 IDW 插值会显得过大，读图要理解"色块是推断"。

---

## 9. 已知限制

- 时间是滚动窗口的常态中位数，不含突发拥堵；不区分工作日/周末、不区分出发时刻
- 只算公交 + 步行，不含地铁
- 等时面是站点时间的 IDW 插值（`k=9, power=2`，种子为起点 0 分钟）
- 同名站按 700 m 判定可换乘，可能把"同名不同路口"连上
- 步行只叠加起点 1.2 km 内的既有站点，不会因为"走过去更快"而新增站点

---

## 10. 文件地图

| 文件 | 作用 |
|---|---|
| `mcp_client.py` | MCP（SSE）客户端 |
| `q.py` / `net.py` / `fill_gentle.py` | 缓存、并发抓取（令牌桶）、补漏 |
| `model.py` | 时刻表解析、`headway_from_schedules`、`wait_for`、服务过滤 |
| `gcj.py` | GCJ-02 ↔ WGS-84 |
| `leg1.py` / `leg2a.py` / `leg2b.py` | 起点线路、展开换乘、两跳计算 |
| `fix_coords.py` | medoid 归并（260 m）、步行叠加（1.2 km）、起点剔除 |
| `export.py` / `deliver.py` / `make_shp.py` | 统计、CSV/GeoJSON、Shapefile |
| `render.py` | 出图：`build_field` / `Placer` / `prune_labels` / `scale_bar` / `origin_callout` |
| `basemap.py` / `tiles_core.py` | 底图瓦片（12 线程并行） |
| `make_map.py` | 一条命令跑完全流程 |
| `qa_offset.py` / `selfcheck.py` | 坐标自检、交付自检 |

---

作者：极地东风谷（KochiyaSrU）
