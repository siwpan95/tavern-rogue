"""图鉴（Collection）：记录"我见过什么"，把每局的遭遇接到局外进度上。

设计依据（调研）：Balatro 的 Collection 用**剪影 + 解锁条件**告诉玩家"我在追什么"；
对开发者来说它同时是**选取率数据源**（哪件宝物从没被拿过）。

存档落在 `ProgressManager.data['collection']`，与进度同一个文件，避免再多一份存档。
"""
from __future__ import annotations

KINDS = ("relics", "enemies", "events")


class Collection:
    """一个薄包装：真正的存储在 ProgressManager.data['collection'] 里。"""

    def __init__(self, progress_manager):
        self.progress = progress_manager
        data = self.progress.data.setdefault("collection", {})
        for kind in KINDS:
            data.setdefault(kind, [])
        self.data = data

    # ─── 记录 ─────────────────────────────────────────

    def mark(self, kind: str, entry_id) -> bool:
        """记录一次"见过"；返回是否是**首次**发现。"""
        if kind not in KINDS or not entry_id:
            return False
        bucket = self.data.setdefault(kind, [])
        if entry_id in bucket:
            return False
        bucket.append(entry_id)
        bucket.sort()
        self.progress.save()
        return True

    def mark_many(self, kind: str, entry_ids) -> int:
        return sum(1 for entry_id in (entry_ids or []) if self.mark(kind, entry_id))

    # ─── 查询 ─────────────────────────────────────────

    def discovered(self, kind: str) -> set:
        return set(self.data.get(kind, []))

    def is_discovered(self, kind: str, entry_id) -> bool:
        return entry_id in self.discovered(kind)

    def progress_of(self, kind: str, total: int) -> tuple:
        """返回 (已发现, 总数, 百分比)。"""
        found = len(self.discovered(kind))
        total = max(1, int(total))
        return found, total, min(100.0, found * 100.0 / total)

    def summary(self, totals: dict) -> list:
        """给 UI 用：每类的 (kind, 已发现, 总数, 百分比)。"""
        rows = []
        for kind in KINDS:
            found, total, pct = self.progress_of(kind, totals.get(kind, 0))
            rows.append((kind, found, total, pct))
        return rows


# ─── 中英文显示名（UI 用）─────────────────────────────────
KIND_LABELS = {
    "relics": "宝物",
    "enemies": "敌人",
    "events": "事件",
}
