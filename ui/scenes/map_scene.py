"""
map_scene.py — 地图探索场景
"""
import pygame
from ui.scenes.base import Scene
from ui.renderer import fill_bg, draw_status_bar, fonts, COLORS, WIDTH


class MapScene(Scene):
    """地图探索"""

    def enter(self, **kwargs):
        super().enter(**kwargs)
        self.gm.ensure_map()
        # 同步层数显示
        if self.gm.map_manager.current_layer != self.gm.floor:
            self.gm.floor = self.gm.map_manager.current_layer

    def draw(self):
        fill_bg(self.screen)
        draw_status_bar(self.screen, self.gm)

        layer = self.gm.get_current_layer()
        if not layer:
            self.switch_to('victory')
            return

        name = layer.get('name', '')
        t = fonts.get('large').render(
            f"第 {self.gm.floor} 层 - {name}", True, COLORS['text_primary'])
        self.screen.blit(t, t.get_rect(center=(WIDTH // 2, 50)))

        # 层进入条件（规格 §6：第 9 层宝藏密室需要密室钥匙）—— 锁住时**说出原因**
        lock_reason = self.gm.layer_lock_reason(layer['layer'])
        if lock_reason:
            warn = fonts.get('medium').render(
                "🔒 本层无法进入：%s（本层为可选层，将被跳过）" % lock_reason,
                True, COLORS['warning'] if 'warning' in COLORS else COLORS['text_secondary'])
            self.screen.blit(warn, warn.get_rect(center=(WIDTH // 2, 92)))
            self.buttons.clear()
            self.buttons.add(450, 420, 300, 50, "跳过本层", self._skip_locked_layer)
            self.buttons.draw_all(self.screen)
            return

        self.buttons.clear()
        nodes = layer.get('nodes', [])
        for i, node in enumerate(nodes):
            x = 80 + i * 220
            y = 180
            w, h = 190, 130

            # 颜色
            if node['completed']:
                color = COLORS['success']
            elif node['revealed']:
                color = self.gm.get_node_color(node['type'])
            else:
                color = COLORS['bg_card']

            rect = pygame.Rect(x, y, w, h)
            pygame.draw.rect(self.screen, color, rect)
            pygame.draw.rect(self.screen, COLORS['accent'], rect, 2)

            icon = self.gm.get_node_icon(node['type'])
            isurf = fonts.get('xlarge').render(icon, True, COLORS['text_secondary'])
            self.screen.blit(isurf, isurf.get_rect(center=(x + w // 2, y + 25)))

            nsurf = fonts.get('medium').render(node['name'], True, COLORS['text_secondary'])
            self.screen.blit(nsurf, nsurf.get_rect(center=(x + w // 2, y + 65)))

            if node['completed']:
                status = "✓ 已完成"
            elif node['revealed']:
                status = "→ 可进入"
            else:
                status = "? 未探索"

            ssurf = fonts.get('small').render(status, True, COLORS['text_secondary'])
            self.screen.blit(ssurf, ssurf.get_rect(center=(x + w // 2, y + 100)))

            if not node['completed']:
                self.buttons.add(x, y, w, h, '', lambda n=node: self._select(n))

        self.buttons.draw_all(self.screen)

    def _skip_locked_layer(self):
        """可选层进不去时，标记为完成并推进（不卡死）。"""
        layer = self.gm.get_current_layer()
        if not layer:
            return
        for node in layer.get('nodes', []):
            node['completed'] = True
        layer['completed'] = True
        completed = self.gm.map_manager.map_data.setdefault('completed_layers', [])
        if layer['layer'] not in completed:
            completed.append(layer['layer'])
        self.gm.map_manager.current_layer = self.gm.map_manager._accessible_next_layer(
            layer['layer'], self.gm.relic_ids())
        self.gm.floor = self.gm.map_manager.current_layer
        print("[TavernRogue] 跳过第 %d 层（%s）" % (layer['layer'], self.gm.layer_lock_reason(layer['layer'])))

    def _select(self, node):
        selected = self.gm.select_map_node(node['id'])
        if not selected:
            print("[TavernRogue] 无法进入该节点！")
            return

        self.gm.current_node = selected
        ntype = selected['type']

        if ntype in ('monster', 'elite', 'boss'):
            self.switch_to('battle', node=selected)
        elif ntype == 'camp':
            self.switch_to('camp')
        elif ntype == 'event':
            self.switch_to('event', node=selected)
        elif ntype == 'shop':
            self.switch_to('shop')
        elif ntype == 'treasure':
            self.switch_to('treasure')
