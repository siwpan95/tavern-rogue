# TavernRogue - 酒馆异闻录

## 仓库角色定位（投资组合分级 ②）

> 本仓在 siwpan 投资组合（D:/projects/repos，共 133 仓）中定级为 **② 精选旗舰**，领域 **游戏作品**。
> **角色**：游戏旗舰。
> **维护策略**：② 旗舰 / 枢纽仓库打磨保留，作为能力展示或收敛点；② 保留类仓库低优先维持、不主动扩张。
> 投资组合统一分级索引（多机可查）：[组合分级决策索引 · allin 事实源](https://gitee.com/siwpan/allin/blob/master/docs/事实源/组合分级决策索引.md)。

基于 D&D SRD 的 Roguelike 自走棋游戏（pygame-ce 图形界面）

## 游戏简介

扮演一名奇幻职业者，在旅店招募冒险者组成战队，沿着随机地图讨伐怪物、搜刮宝物，最终击败盘踞在塔顶的远古巨龙！

## 核心玩法

- **招募阶段**：花费铸币招募冒险者、调整队伍站位、三连合成
- **地图探索**：选择节点进行战斗、购物、休息或遭遇事件
- **回合制战斗**：点击己方单位选择目标，点击敌人发起攻击；英雄技能辅助战局
- **成长系统**：通过战斗获得铸币和宝物，营地训练强化冒险者

## 游戏特色

- 5 个英雄职业（战士、游荡者、牧师、法师、术士），各有独特技能
- 6 个种族共鸣（人类、精灵、矮人、龙裔、半兽人、提夫林）
- 丰富的关键词系统（守卫、力场护盾、亡者遗赠、连击、剧毒等）
- 宝物系统（7 种魔法物品）
- 随机事件系统
- 9 层地图，最终决战远古红龙
- 铸币经济系统（每回合 +3 + 层数收入，上限 10）
- 营地训练系统（+1 ATK / +1 HP 永久强化）

## 快速开始

### 环境要求

- Python 3.10+
- pygame-ce
- （可选）allin-engine —— 未安装时自动降级，游戏照常可玩

### 安装依赖

```bash
pip install -r requirements.txt          # 运行时：pygame-ce + allin-engine
pip install -r requirements-dev.txt      # 验证：额外装 pytest
pip install -r requirements-assets.txt   # 可选：生成音频素材（bloodmusic，构建期用）
```

### 运行游戏

```bash
python run_gui.py
```

### 生成音频素材（可选）

音效 / BGM 由自研引擎 **bloodmusic** 离线生成，**不入库**；不生成也能玩（静音降级）。

```bash
python tools/gen_audio_assets.py            # 38 个音效 + 10 首 BGM
python tools/gen_audio_assets.py --check    # 只检查素材是否齐备
```

### 获取内置中文字体（可选）

手写体 `BaoCanMouHuiTingShouXieTi2.0-2.ttf` 有 50.5 MiB，**不入库**；缺失时自动回退系统
CJK 字体（微软雅黑/黑体/Noto）并出声提示，界面不会崩。

```bash
python tools/fetch_font.py            # 下载到 assets/fonts/（带 sha256 校验）
python tools/fetch_font.py --check    # 只检查是否就位
```

### 自定义规则（mutators）

8 条可自由组合的修饰符（`2^8` 种玩法），既当难度旋钮也当内容放大器：

```bash
python run_gui.py --list-mutators                 # 列出全部
python run_gui.py --mutator one_hp --mutator midas   # 一击必死 + 点金
```

### 测试

```bash
pip install -r requirements-dev.txt   # pytest + pyflakes + pytest-cov
python run_tests.py          # 四层：语法 → pyflakes 静态检查 → JSON 数据 → pytest
python run_tests.py --no-lint
python -m pytest tests -q    # 只跑用例
python -m pytest tests -q --cov=game --cov=ui   # 覆盖率（基线约 64%）
python tools/doctor.py --headless   # 环境/素材自检 + 无头启动冒烟
python tools/balance_report.py --runs 100 --ab   # 平衡对拍（无 UI 跑完整局，含死亡层数分布）
```

### 持续集成

CI 跑的就是本地那一条命令，避免"CI 与本地不一致"：

| 环境 | 配置 | 命令 |
| --- | --- | --- |
| GitHub | `.github/workflows/ci.yml`（ubuntu + windows × py3.12 / 3.14） | `python run_tests.py` + `python tools/doctor.py --headless` |
| Gitee Go | 流水线里加一个「执行命令」步骤 | 同上（本仓主仓在 Gitee；GitHub 工作流留作镜像/备份） |

## 项目结构

```
TavernRogue/
├── run_gui.py                  # 唯一入口，启动图形界面
├── run_tests.py                # 测试入口（语法 + pyflakes + 数据 + pytest 四层）
├── requirements*.txt           # 运行时 / 验证 / 素材生成 三类依赖
├── pytest.ini
├── tests/                      # pytest 套件（数据完整性 / 战斗 / 事件 / 宝物 / 存档 / 冒烟）
├── tools/                      # 构建期与验证工具（不入游戏运行时）
│   ├── gen_audio_assets.py     #   用 bloodmusic 离线生成音效与 BGM
│   └── balance_report.py       #   无 UI 批量模拟，出平衡报告
├── docs/                       # 平衡报告与内容设计稿
├── ui/                         # 图形界面层（MVC + Scene 架构）
│   ├── app.py                  # 应用外壳：pygame 初始化 + 主循环 + 音频
│   ├── game_manager.py         # Model：中央状态管理（含局内存档与图鉴）
│   ├── renderer.py             # View：共享渲染（颜色/字体/按钮/卡片）
│   └── scenes/                 # Controller：13 个游戏场景（含冒险图鉴）
├── game/                       # 游戏逻辑模块（与 UI 解耦，可独立测试）
│   ├── hero.py                 #   英雄职业系统（5 职业，被动 + 技能）
│   ├── engine.py               #   战斗引擎（事件队列，18 个关键词）
│   ├── ai_targeting.py         #   目标选择（自研引擎决策树 + 回退规则）
│   ├── event_effects.py        #   事件效果唯一实现
│   ├── relic_effects.py        #   宝物效果登记表 + 稀有度权重 + 战斗修正
│   ├── battle_audit.py         #   战斗审计（WorldLog 旁路）
│   ├── audio.py                #   音频播放（pygame.mixer；素材离线生成）
│   ├── mutators.py             #   自定义规则（8 条修饰符）
│   ├── collection.py           #   图鉴（发现记录）
│   ├── run_save.py             #   局内存档（SaveLoadManager）
│   ├── recruit.py / map_manager.py / node_handler.py / events.py / relics.py / rewards.py
│   └── persistence.py          #   局外成长存档（含进阶五级阶梯）
└── data/                       # 游戏数据（JSON 驱动）
```

## 架构说明

重构后采用 **MVC + Scene** 模式：

| 层级 | 职责 | 核心文件 |
|------|------|----------|
| **Model** | 中央状态、子系统协调 | `ui/game_manager.py` |
| **View** | 共享渲染、UI 组件 | `ui/renderer.py` |
| **Controller** | 场景调度、事件分发 | `ui/scenes/base.py` |

每个场景遵循统一生命周期：`enter()` → `handle_event/draw/update` × N → `leave()`，不再使用阻塞式 while 循环。

`game/` 目录下的纯逻辑模块与 UI 完全解耦，可独立测试。

## 已实现功能

- [x] 核心战斗引擎（守卫、力场护盾、亡者遗赠、连击、剧毒、闪避、横扫、过杀、血怒、神盾、荆棘、威吓、光环、战魂、殉道等 **18 个关键词**）
- [x] 英雄职业系统（5 个职业，各有**已实现的被动**与一次性技能）
- [x] 酒馆招募系统（购买、刷新、三连合成、术士生命分流）
- [x] 地图生成系统（9 层、层变体、精英/Boss 词缀、Boss 池、遭遇规模随层数成长）
- [x] 宝物系统（**36 件**魔法物品，效果全部接线；稀有度 60/30/10 加权；含 3 件"改变玩法"的史诗宝物）
- [x] 事件系统（**36 个**事件，21 种效果全部有实现，同局不重复）
- [x] 敌人与 Boss（**56 个敌人**，14 精英 / 12 Boss，6 个 Boss 带 `counter_tag`）
- [x] 奖励系统（战斗奖励、发现机制）
- [x] pygame-ce 图形界面（**14 个场景**完整实现）
- [x] 铸币经济（回合收入、携带上限、人类共鸣加成）
- [x] 营地训练（永久属性强化）
- [x] 局外成长（职业解锁链、**进阶 0-5 五级阶梯**、**冒险日志**：最佳阵容/最高伤害/最爱种族）
  · 实测通关率：进阶 0 = **57.6%**、进阶 2 = 28.5%、进阶 5 = **25.5%**（100 局/职业口径）
- [x] **冒险图鉴**（宝物/敌人/事件的发现进度）+ **游戏内帮助**（分页，随实现同步）
- [x] **自定义规则**（8 条 mutators，可自由组合）
- [x] 第 9 层**可选密室**（需要「密室钥匙」才能进入，否则显示锁定并跳过）
- [x] 局内存档（继续冒险，基于自研引擎 SaveLoadManager）
- [x] 音频（bloodmusic 离线生成的 38 音效 + 10 BGM，缺失静音降级）
- [x] 固定种子（`python run_gui.py --seed 12345`，结算屏显示种子）
- [x] 自动化验证（pytest **276** 用例 + `tools/balance_report.py` 平衡对拍 + `run_tests.py` 静态检查）

## 内容设计稿与平衡报告

- [`docs/内容设计稿-优先级.md`](docs/内容设计稿-优先级.md) —— 按**重复可玩性边际收益**排序的设计稿（含已落地/待办两档与验收阈值）
- [`docs/balance-report.md`](docs/balance-report.md) —— 200 局批量模拟结果（含目标选择 A/B 对照）

## 法律声明

本游戏使用 D&D SRD 5.1 中的开放游戏内容。SRD 5.1 由 Wizards of the Coast LLC 以
**Creative Commons Attribution 4.0 International（CC-BY-4.0）** 授权（2023 年 1 月起；
OGL 1.0a 亦仍可用，但官方推荐改用 CC-BY-4.0 署名）。本仓此前写的「遵循 OGL 许可」为过期表述，
于 2026-10-16 按官方许可页订正。

> This work includes material taken from the System Reference Document 5.1 ("SRD 5.1")
> by Wizards of the Coast LLC and available at
> https://dnd.wizards.com/resources/systems-reference-document.
> The SRD 5.1 is licensed under the Creative Commons Attribution 4.0 International License
> available at https://creativecommons.org/licenses/by/4.0/legalcode.

所有名称均为 SRD 中的通用概念；文字描述、美术资源、代码实现均为原创，
与 Wizards of the Coast 不存在隶属或背书关系。

## 自研引擎接入（记账 · SPEC-201）

| 引擎（PyPI: siwpan） | 判定 | 接了什么 | 为什么不接更多 |
| --- | --- | --- | --- |
| `allin-engine` | ✅ 运行时依赖 | 决策树（战斗目标选择）、WorldLog（战斗审计旁路）、SaveLoadManager（局内存档） | 不接 ECS 重写 / 卡牌战斗 / trpg 骰系：会破坏百分比战斗与 `battle.py` 的中文日志解析契约 |
| `bloodmusic` | ✅ 构建期依赖 | `tools/gen_audio_assets.py` 离线生成 38 音效 + 10 BGM；运行时只用 pygame.mixer 播放 | 不做运行时实时合成：会引入 numpy/scipy（约 140 MB）与 5 秒级冷启动 |
| `3dworld` | ❌ 不接入（记账） | — | 需 OpenGL + 显示设备；硬钉 `pyglet==2.1.16`（与本机 pyglet 1.5.31 冲突）；Windows 无 headless 记录；对 2D 自走棋无同构收益 |

**降级保证**：两个引擎缺失时都会**出声降级**（stderr 提示 + 仓内等价实现），游戏仍可正常运行；
`requirements.txt` 只装运行时依赖，`requirements-assets.txt` 才是音频生成依赖。

## 规则内核接入判定（R2 · 2026-08-27）

勘查结论：本作战斗为百分比判定（闪避/暴击几率）与区间随机，英雄属性为自研
roguelite 数值体系——alloy.trpg（D&D 三宝书 + GURPS Basic Set）无同构原语可接；
按「只接同构原语、绝不破坏行为契约」原则**不接入**（记账声明）。
将来若引入 d20/3d6 检定：`from alloy.trpg import roll_3d6, gurps_success_chance`
（接入模式参照 running-group-simulator 的 `core/dice.py`）。