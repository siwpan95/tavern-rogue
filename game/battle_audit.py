"""战斗审计（旁路）：把结构化战斗事件另记一份，供回放/统计/平衡分析使用。

**不动 `battle_log`**：那份中文文案流是 UI 动画解析（ui/scenes/battle.py 的正则）的输入，
替换它等于同时改 UI 与平衡，属于破坏行为契约（SPEC-201）。

存储走自研引擎 allin_engine 的 WorldLog（确定性转储）；引擎缺失时退化为内存条目 +
JSONL 落盘，功能不失效。
"""
from __future__ import annotations

import io
import json
import sys

ENGINE_AVAILABLE = False
ENGINE_ERROR = ""

try:
    from allin_engine.core.world_log import WorldLog
    ENGINE_AVAILABLE = True
except ImportError as exc:
    WorldLog = None
    ENGINE_ERROR = str(exc)


class BattleAudit:
    """一场战斗的审计记录器。"""

    def __init__(self, source: str = "tavern-rogue", max_entries: int = 5000):
        self.source = source
        self.backend = "memory"
        self._world_log = None
        self._entries: list[dict] = []
        if WorldLog is not None:
            try:
                self._world_log = WorldLog(source=source, max_entries=max_entries)
                self.backend = "worldlog"
            except Exception as exc:  # noqa: BLE001 - 引擎异常不该让游戏崩
                print("[TavernRogue] WorldLog 初始化失败，审计退化为内存记录：%s" % exc,
                      file=sys.stderr)
                self._world_log = None

    def record(self, event_type: str, **payload) -> None:
        """记录一条事实（战斗开始/攻击/死亡/宝物触发…）。"""
        if self._world_log is not None:
            self._world_log.append(event_type, payload)
            return
        self._entries.append({"type": event_type, **payload})

    def entries(self) -> list[dict]:
        if self._world_log is not None:
            return self._world_log.entries()
        return list(self._entries)

    def summary(self) -> dict:
        """按事件类型计数 + 总条数，给平衡报告用。"""
        counts: dict[str, int] = {}
        for entry in self.entries():
            key = entry.get("type", entry.get("event_type", "unknown"))
            counts[key] = counts.get(key, 0) + 1
        return {"backend": self.backend, "total": len(self.entries()), "by_type": counts}

    def deterministic_dump(self) -> str:
        """不含时间戳的转储：同种子同输入应逐字节一致（对拍用）。"""
        if self._world_log is not None:
            return self._world_log.deterministic_dump()
        return json.dumps(self._entries, ensure_ascii=False, sort_keys=True)

    def write_jsonl(self, path) -> bool:
        try:
            with io.open(path, "w", encoding="utf-8", newline="\n") as handle:
                for entry in self.entries():
                    handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
            return True
        except OSError as exc:
            print("[TavernRogue] 审计落盘失败：%s" % exc, file=sys.stderr)
            return False
