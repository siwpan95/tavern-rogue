# TavernRogue - 酒馆异闻录

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

### 安装依赖

```bash
pip install -r requirements.txt
```

### 运行游戏

```bash
python run_gui.py
```

## 项目结构

```
TavernRogue/
├── run_gui.py                  # 唯一入口，启动图形界面
├── requirements.txt
├── ui/                         # 图形界面层（MVC + Scene 架构）
│   ├── app.py                  # 应用外壳：pygame 初始化 + 主循环
│   ├── game_manager.py         # Model：中央状态管理
│   ├── renderer.py             # View：共享渲染（颜色/字体/按钮/卡片）
│   └── scenes/                 # Controller：12 个游戏场景
│       ├── base.py             #   场景基类 + SceneManager
│       ├── menu.py             #   主菜单 / 职业选择
│       ├── recruit.py          #   酒馆招募
│       ├── map_scene.py        #   地图探索
│       ├── battle.py           #   回合制战斗
│       ├── shop.py             #   商店
│       ├── camp.py             #   营地（训练 / 休息）
│       ├── event_scene.py      #   随机事件
│       ├── treasure.py         #   宝箱
│       ├── reward.py           #   战斗奖励
│       └── end_scenes.py       #   胜利 / 失败
├── game/                       # 游戏逻辑模块（与 UI 解耦）
│   ├── hero.py                 #   英雄职业系统
│   ├── engine.py               #   战斗引擎
│   ├── recruit.py              #   酒馆招募系统
│   ├── map_manager.py          #   地图管理
│   ├── node_handler.py         #   节点事件处理
│   ├── events.py               #   事件系统
│   ├── relics.py               #   宝物系统
│   └── rewards.py              #   奖励系统
└── data/                       # 游戏数据（JSON 驱动）
    ├── adventurers.json
    ├── relics.json
    ├── enemies.json
    ├── events.json
    └── map_templates.json
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

- [x] 核心战斗引擎（守卫、力场护盾、亡者遗赠、连击等关键词）
- [x] 英雄职业系统（5 个职业及技能）
- [x] 酒馆招募系统（购买、刷新、三连合成）
- [x] 地图生成系统（9 层地图，多种节点类型）
- [x] 宝物系统（7 种魔法物品）
- [x] 事件系统（随机事件）
- [x] 奖励系统（战斗奖励、发现机制）
- [x] pygame-ce 图形界面（12 个场景完整实现）
- [x] 铸币经济（回合收入、携带上限）
- [x] 营地训练（永久属性强化）

## 法律声明

本游戏使用 D&D SRD 5.1 中的开放游戏内容，遵循 OGL 许可。
所有名称均为 SRD 中的通用概念，文字描述、美术资源、代码实现均为原创。

## 规则内核接入判定（R2 · 2026-08-27）

勘查结论：本作战斗为百分比判定（闪避/暴击几率）与区间随机，英雄属性为自研
roguelite 数值体系——alloy.trpg（D&D 三宝书 + GURPS Basic Set）无同构原语可接；
按「只接同构原语、绝不破坏行为契约」原则**不接入**（记账声明）。
将来若引入 d20/3d6 检定：`from alloy.trpg import roll_3d6, gurps_success_chance`
（接入模式参照 running-group-simulator 的 `core/dice.py`）。