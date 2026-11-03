# -*- coding: utf-8 -*-
"""
《像素塔防》 —— 一个用 Pygame 编写的完整塔防游戏

功能:
  - 3 种防御塔: 箭塔(高速单体) / 炮塔(范围溅射) / 冰塔(减速)
  - 4 种敌人:   普通 / 疾行 / 重甲 / 最终 Boss
  - 12 波进攻, 血量随波次成长, 波间奖励
  - 金币经济: 击杀奖励、建塔、升级(3 级)、出售返还
  - 暂停 / 1-3 倍速 / 放置预览 / 血量条 / 粒子特效

操作:
  鼠标左键   选择塔 / 在空地建塔 / 点按钮
  鼠标右键   取消选择
  1 / 2 / 3  快速选择要建造的塔
  空格       开始下一波
  P          暂停
  R          游戏结束或胜利后重新开始

运行: pip install pygame  ->  python3 tower_defense.py
"""

import math
import os
import random
import sys

try:
    import pygame
    from pygame.math import Vector2
except ImportError:
    print("未安装 pygame, 请先运行: pip install pygame")
    sys.exit(1)

# ---------------------------------------------------------------- 常量

CELL = 40
COLS, ROWS = 20, 15
W, H = COLS * CELL, ROWS * CELL          # 游戏区 800x600
SIDEBAR = 220
WIN_W, WIN_H = W + SIDEBAR, H
FPS = 60
FINAL_WAVE = 12
MAX_LEVEL = 3

WAYPOINT_CELLS = [(-1, 2), (14, 2), (14, 6), (3, 6), (3, 10), (16, 10), (16, 13), (20, 13)]
PATH_POINTS = [Vector2(c * CELL + CELL // 2, r * CELL + CELL // 2) for c, r in WAYPOINT_CELLS]

TOWER_TYPES = {
    "arrow":  {"name": "箭塔", "cost": 50,  "range": 115, "damage": 12, "rate": 2.2,
               "proj_speed": 360, "color": (90, 170, 255), "desc": "高速单体"},
    "cannon": {"name": "炮塔", "cost": 110, "range": 105, "damage": 32, "rate": 0.8,
               "proj_speed": 240, "splash": 62, "color": (255, 150, 60), "desc": "范围溅射"},
    "frost":  {"name": "冰塔", "cost": 80,  "range": 105, "damage": 6,  "rate": 1.3,
               "proj_speed": 300, "slow": 0.45, "slow_time": 2.2,
               "color": (130, 230, 255), "desc": "减速敌人"},
}
DAMAGE_MULT = 1.55   # 每级伤害倍率
RANGE_MULT = 1.10    # 每级射程倍率

ENEMY_TYPES = {
    "normal": {"hp": 60,   "speed": 55,  "reward": 7,   "radius": 12, "life": 1,  "color": (95, 205, 95)},
    "runner": {"hp": 36,   "speed": 105, "reward": 9,   "radius": 10, "life": 1,  "color": (240, 220, 90)},
    "tank":   {"hp": 230,  "speed": 33,  "reward": 22,  "radius": 15, "life": 2,  "color": (175, 95, 225)},
    "boss":   {"hp": 2800, "speed": 27,  "reward": 250, "radius": 21, "life": 10, "color": (240, 70, 70)},
}

BG_COLOR = (18, 22, 30)
PATH_COLOR = (74, 64, 52)
GRID_COLOR = (30, 36, 48)
PANEL_COLOR = (26, 30, 40)
TEXT_COLOR = (225, 230, 240)


def compute_path_cells():
    cells = set()
    for (c1, r1), (c2, r2) in zip(WAYPOINT_CELLS, WAYPOINT_CELLS[1:]):
        dc = (c2 > c1) - (c2 < c1)
        dr = (r2 > r1) - (r2 < r1)
        c, r = c1, r1
        cells.add((c, r))
        while (c, r) != (c2, r2):
            c += dc
            r += dr
            cells.add((c, r))
    return {(c, r) for (c, r) in cells if 0 <= c < COLS and 0 <= r < ROWS}


PATH_CELLS = compute_path_cells()

# ---------------------------------------------------------------- 字体(支持中文)

_font_cache = {}


def get_font(size):
    if size in _font_cache:
        return _font_cache[size]
    candidates = [
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
        "/Library/Fonts/Arial Unicode.ttf",
        "C:/Windows/Fonts/msyh.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    ]
    font = None
    for path in candidates:
        if os.path.exists(path):
            font = pygame.font.Font(path, size)
            break
    if font is None:
        font = pygame.font.SysFont("arial", size)
    _font_cache[size] = font
    return font


def draw_text(surf, text, pos, size=18, color=TEXT_COLOR, center=False):
    img = get_font(size).render(str(text), True, color)
    rect = img.get_rect()
    if center:
        rect.center = pos
    else:
        rect.topleft = pos
    surf.blit(img, rect)
    return rect


# ---------------------------------------------------------------- 粒子

class Particle:
    def __init__(self, pos, color):
        self.pos = Vector2(pos)
        ang = random.uniform(0, math.tau)
        spd = random.uniform(30, 130)
        self.vel = Vector2(math.cos(ang), math.sin(ang)) * spd
        self.life = self.max_life = random.uniform(0.25, 0.55)
        self.color = color
        self.size = random.uniform(2.0, 4.5)

    def update(self, dt):
        self.pos += self.vel * dt
        self.vel *= 0.90
        self.life -= dt

    def draw(self, surf):
        r = max(1, int(self.size * self.life / self.max_life))
        pygame.draw.circle(surf, self.color, (int(self.pos.x), int(self.pos.y)), r)


# ---------------------------------------------------------------- 敌人

class Enemy:
    def __init__(self, kind, hp_mult):
        cfg = ENEMY_TYPES[kind]
        self.kind = kind
        self.max_hp = cfg["hp"] if kind == "boss" else int(cfg["hp"] * hp_mult)
        self.hp = self.max_hp
        self.speed = cfg["speed"]
        self.reward = cfg["reward"]
        self.radius = cfg["radius"]
        self.life_damage = cfg["life"]
        self.color = cfg["color"]
        self.pos = Vector2(PATH_POINTS[0])
        self.wp_index = 1
        self.progress = 0.0
        self.alive = True
        self.escaped = False
        self.life_lost = False
        self.slow_factor = 1.0
        self.slow_timer = 0.0

    def apply_slow(self, factor, duration):
        if self.kind == "boss":                      # Boss 减速抗性
            factor = 1 - (1 - factor) * 0.5
        if self.slow_timer <= 0 or factor < self.slow_factor:
            self.slow_factor = factor
        self.slow_timer = max(self.slow_timer, duration)

    def take_damage(self, dmg):
        self.hp -= dmg
        if self.hp <= 0:
            self.alive = False

    def update(self, dt):
        if not self.alive or self.escaped:
            return
        if self.slow_timer > 0:
            self.slow_timer -= dt
            if self.slow_timer <= 0:
                self.slow_factor = 1.0
        move = self.speed * self.slow_factor * dt
        while move > 0 and self.wp_index < len(PATH_POINTS):
            target = PATH_POINTS[self.wp_index]
            d = target - self.pos
            dist = d.length()
            if dist <= move:
                self.pos = Vector2(target)
                self.progress += dist
                move -= dist
                self.wp_index += 1
            else:
                self.pos += d.normalize() * move
                self.progress += move
                move = 0
        if self.wp_index >= len(PATH_POINTS):
            self.escaped = True

    def draw(self, surf):
        x, y = int(self.pos.x), int(self.pos.y)
        pygame.draw.circle(surf, self.color, (x, y), self.radius)
        pygame.draw.circle(surf, (20, 20, 25), (x, y), self.radius, 2)
        if self.slow_timer > 0:
            pygame.draw.circle(surf, (140, 230, 255), (x, y), self.radius + 2, 2)
        if self.kind == "boss":
            pygame.draw.circle(surf, (255, 220, 120), (x, y), 5)
        # 血条
        w = self.radius * 2 + 4
        ratio = max(0.0, self.hp / self.max_hp)
        bx, by = x - w // 2, y - self.radius - 9
        pygame.draw.rect(surf, (70, 30, 30), (bx, by, w, 5))
        pygame.draw.rect(surf, (80, 220, 90), (bx, by, int(w * ratio), 5))


# ---------------------------------------------------------------- 防御塔

class Tower:
    def __init__(self, kind, cell):
        self.kind = kind
        self.cell = cell
        self.pos = Vector2(cell[0] * CELL + CELL // 2, cell[1] * CELL + CELL // 2)
        self.level = 1
        self.cooldown = 0.0
        self.angle = -90.0
        self.invested = TOWER_TYPES[kind]["cost"]

    def stat(self, key):
        base = TOWER_TYPES[self.kind][key]
        if key == "damage":
            return base * (DAMAGE_MULT ** (self.level - 1))
        if key == "range":
            return base * (RANGE_MULT ** (self.level - 1))
        return base

    def upgrade_cost(self):
        return int(TOWER_TYPES[self.kind]["cost"] * 0.8 * self.level)

    def acquire(self, enemies):
        rng = self.stat("range")
        best, best_progress = None, -1.0
        for e in enemies:
            if e.alive and not e.escaped and (e.pos - self.pos).length() <= rng:
                if e.progress > best_progress:
                    best, best_progress = e, e.progress
        return best

    def update(self, dt, enemies, projectiles):
        self.cooldown -= dt
        if self.cooldown > 0:
            return
        target = self.acquire(enemies)
        if target:
            self.cooldown = 1.0 / self.stat("rate")
            d = target.pos - self.pos
            self.angle = math.degrees(math.atan2(-d.y, d.x))
            projectiles.append(Projectile(self, target))

    def draw(self, surf):
        x, y = int(self.pos.x), int(self.pos.y)
        color = TOWER_TYPES[self.kind]["color"]
        pygame.draw.circle(surf, (45, 52, 68), (x, y), 17)
        pygame.draw.circle(surf, color, (x, y), 14)
        rad = math.radians(self.angle)
        dx, dy = math.cos(rad), -math.sin(rad)
        if self.kind == "arrow":
            tip = (x + dx * 15, y + dy * 15)
            left = (x - dy * 6, y + dx * 6)
            right = (x + dy * 6, y - dx * 6)
            pygame.draw.polygon(surf, (20, 24, 34), [tip, left, right])
        elif self.kind == "cannon":
            end = (x + dx * 18, y + dy * 18)
            pygame.draw.line(surf, (30, 30, 38), (x, y), end, 8)
            pygame.draw.circle(surf, (30, 30, 38), (x, y), 6)
        else:  # frost 菱形
            pts = [(x, y - 9), (x + 9, y), (x, y + 9), (x - 9, y)]
            pygame.draw.polygon(surf, (240, 255, 255), pts)
        for i in range(self.level):  # 等级点
            pygame.draw.circle(surf, (255, 235, 140), (x - 8 + i * 8, y + 21), 2)


# ---------------------------------------------------------------- 子弹

class Projectile:
    def __init__(self, tower, target):
        cfg = TOWER_TYPES[tower.kind]
        self.kind = tower.kind
        self.pos = Vector2(tower.pos)
        self.target = target
        self.speed = cfg["proj_speed"]
        self.damage = tower.stat("damage")
        self.splash = cfg.get("splash", 0)
        self.slow = cfg.get("slow", 0)
        self.slow_time = cfg.get("slow_time", 0)
        self.color = cfg["color"]
        self.radius = 6 if self.kind == "cannon" else 4
        self.dead = False

    def update(self, dt, game):
        t = self.target
        if not t.alive or t.escaped:
            self.dead = True
            return
        d = t.pos - self.pos
        dist = d.length()
        if dist <= self.speed * dt + t.radius:
            self.hit(game)
            self.dead = True
            return
        self.pos += d.normalize() * self.speed * dt

    def hit(self, game):
        if self.kind == "cannon":
            game.explode(self.target.pos, self.splash, self.damage, self.color)
        else:
            if self.slow:
                self.target.apply_slow(self.slow, self.slow_time)
            game.damage_enemy(self.target, self.damage)
            game.spawn_particles(self.target.pos, self.color, 5)

    def draw(self, surf):
        pygame.draw.circle(surf, self.color, (int(self.pos.x), int(self.pos.y)), self.radius)


# ---------------------------------------------------------------- 按钮

class Button:
    def __init__(self, rect, text, size=18):
        self.rect = pygame.Rect(rect)
        self.text = text
        self.size = size
        self.visible = True
        self.enabled = True
        self.highlight = False

    def draw(self, surf, mouse):
        if not self.visible:
            return
        hover = self.rect.collidepoint(mouse) and self.enabled
        base = (58, 68, 92) if self.enabled else (38, 42, 55)
        if hover:
            base = (74, 88, 118)
        if self.highlight:
            base = (86, 110, 150)
        pygame.draw.rect(surf, base, self.rect, border_radius=8)
        border = (255, 220, 120) if self.highlight else (110, 125, 155)
        pygame.draw.rect(surf, border, self.rect, 2, border_radius=8)
        color = TEXT_COLOR if self.enabled else (120, 126, 140)
        draw_text(surf, self.text, self.rect.center, self.size, color, center=True)

    def hit(self, pos):
        return self.visible and self.enabled and self.rect.collidepoint(pos)


# ---------------------------------------------------------------- 波次

def compose_wave(n):
    comp = ["normal"] * (6 + 2 * n)
    if n >= 3:
        comp += ["runner"] * (2 + n)
    if n >= 5:
        comp += ["tank"] * (n - 3)
    if n >= 9:
        comp += ["runner"] * n
    boss = n == FINAL_WAVE
    random.shuffle(comp)
    if boss:
        comp += ["tank"] * 4 + ["boss"]
    return comp


# ---------------------------------------------------------------- 游戏主体

class Game:
    def __init__(self, screen):
        self.screen = screen
        self.reset()
        bx = W + 12
        bw = SIDEBAR - 24
        self.btn_towers = {
            "arrow":  Button((bx, 180, bw, 44), "", 17),
            "cannon": Button((bx, 230, bw, 44), "", 17),
            "frost":  Button((bx, 280, bw, 44), "", 17),
        }
        self.btn_upgrade = Button((bx, 446, bw, 34), "", 16)
        self.btn_sell = Button((bx, 486, bw, 34), "", 16)
        self.btn_start = Button((bx, 528, bw, 38), "", 18)
        self.btn_pause = Button((bx, 572, bw // 2 - 4, 26), "暂停", 15)
        self.btn_speed = Button((bx + bw // 2 + 4, 572, bw // 2 - 4, 26), "", 15)
        self.btn_restart = Button((W // 2 - 90, H // 2 + 44, 180, 44), "重新开始", 20)

    def reset(self):
        self.gold = 220
        self.lives = 20
        self.score = 0
        self.kills = 0
        self.wave = 0
        self.hp_mult = 1.0
        self.wave_active = False
        self.spawn_queue = []
        self.spawn_timer = 0.0
        self.enemies = []
        self.towers = {}          # cell -> Tower
        self.projectiles = []
        self.particles = []
        self.placing = None       # 待建造的塔类型
        self.selected = None      # 已选中的塔
        self.paused = False
        self.speed = 1
        self.state = "playing"    # playing / gameover / victory
        self.msg = ""
        self.msg_t = 0.0
        self.mouse = (0, 0)

    # ---------------- 工具 ----------------

    def show_message(self, text, t=2.2):
        self.msg, self.msg_t = text, t

    def spawn_particles(self, pos, color, n):
        for _ in range(n):
            self.particles.append(Particle(pos, color))

    def damage_enemy(self, e, dmg):
        if not e.alive:
            return
        e.take_damage(dmg)
        if not e.alive:
            self.gold += e.reward
            self.score += e.reward * 10
            self.kills += 1
            self.spawn_particles(e.pos, e.color, 16)

    def explode(self, pos, radius, damage, color):
        self.spawn_particles(pos, color, 22)
        for e in list(self.enemies):
            if e.alive and (e.pos - pos).length() <= radius + e.radius:
                self.damage_enemy(e, damage)

    # ---------------- 操作 ----------------

    def try_build(self, cell, kind):
        cost = TOWER_TYPES[kind]["cost"]
        if cell in self.towers:
            self.show_message("这里已经有塔了")
            return False
        if cell in PATH_CELLS:
            self.show_message("不能建在道路上")
            return False
        if self.gold < cost:
            self.show_message("金币不足")
            return False
        self.gold -= cost
        self.towers[cell] = Tower(kind, cell)
        self.selected = self.towers[cell]
        return True

    def upgrade_selected(self):
        t = self.selected
        if not t or t.level >= MAX_LEVEL:
            return
        cost = t.upgrade_cost()
        if self.gold < cost:
            self.show_message("金币不足, 无法升级")
            return
        self.gold -= cost
        t.invested += cost
        t.level += 1
        self.spawn_particles(t.pos, (255, 235, 140), 14)

    def sell_selected(self):
        t = self.selected
        if not t:
            return
        self.gold += int(t.invested * 0.7)
        del self.towers[t.cell]
        self.selected = None

    def start_wave(self):
        if self.wave_active or self.state != "playing":
            return
        self.wave += 1
        self.hp_mult = 1 + 0.28 * (self.wave - 1)
        self.spawn_queue = compose_wave(self.wave)
        self.spawn_timer = 0.0
        self.wave_active = True
        self.show_message(f"第 {self.wave} 波来袭!")

    # ---------------- 事件 ----------------

    def handle_event(self, e):
        if e.type == pygame.KEYDOWN:
            self.on_key(e.key)
        elif e.type == pygame.MOUSEBUTTONDOWN:
            if e.button == 1:
                self.on_left_click(e.pos)
            elif e.button == 3:
                self.placing = None
                self.selected = None

    def on_key(self, key):
        if self.state in ("gameover", "victory"):
            if key == pygame.K_r:
                self.reset()
            return
        if key == pygame.K_1:
            self.placing, self.selected = "arrow", None
        elif key == pygame.K_2:
            self.placing, self.selected = "cannon", None
        elif key == pygame.K_3:
            self.placing, self.selected = "frost", None
        elif key == pygame.K_SPACE:
            self.start_wave()
        elif key == pygame.K_p:
            self.paused = not self.paused
        elif key == pygame.K_ESCAPE:
            self.placing = None
            self.selected = None

    def on_left_click(self, pos):
        if self.state in ("gameover", "victory"):
            if self.btn_restart.hit(pos):
                self.reset()
            return
        x, y = pos
        if x >= W:  # 侧边栏
            for kind, btn in self.btn_towers.items():
                if btn.hit(pos):
                    self.placing, self.selected = kind, None
                    return
            if self.btn_upgrade.hit(pos) and self.selected:
                self.upgrade_selected()
                return
            if self.btn_sell.hit(pos) and self.selected:
                self.sell_selected()
                return
            if self.btn_start.hit(pos):
                self.start_wave()
                return
            if self.btn_pause.hit(pos):
                self.paused = not self.paused
                return
            if self.btn_speed.hit(pos):
                self.speed = self.speed % 3 + 1
                return
            return
        cell = (x // CELL, y // CELL)
        if self.placing:
            self.try_build(cell, self.placing)
        elif cell in self.towers:
            self.selected = self.towers[cell]
        else:
            self.selected = None

    # ---------------- 更新 ----------------

    def update(self, dt):
        if self.state != "playing" or self.paused:
            return
        if self.msg_t > 0:
            self.msg_t -= dt

        # 出怪
        if self.wave_active and self.spawn_queue:
            self.spawn_timer -= dt
            if self.spawn_timer <= 0:
                kind = self.spawn_queue.pop(0)
                self.enemies.append(Enemy(kind, self.hp_mult))
                self.spawn_timer = max(0.35, 0.9 - 0.04 * self.wave)

        for e in self.enemies:
            e.update(dt)
        for e in self.enemies:
            if e.escaped and not e.life_lost:
                e.life_lost = True
                self.lives -= e.life_damage
                self.show_message(f"有敌人突破了防线! 生命 -{e.life_damage}")
        self.enemies = [e for e in self.enemies if e.alive and not e.escaped]

        for t in self.towers.values():
            t.update(dt, self.enemies, self.projectiles)
        for p in self.projectiles:
            p.update(dt, self)
        self.projectiles = [p for p in self.projectiles if not p.dead]

        for pt in self.particles:
            pt.update(dt)
        self.particles = [pt for pt in self.particles if pt.life > 0]

        # 波次结束
        if self.wave_active and not self.spawn_queue and not self.enemies:
            self.wave_active = False
            if self.wave >= FINAL_WAVE:
                self.state = "victory"
            else:
                bonus = 20 + 6 * self.wave
                self.gold += bonus
                self.show_message(f"第 {self.wave} 波已清空! 奖励 {bonus} 金币", 3.0)

        if self.lives <= 0:
            self.lives = 0
            self.state = "gameover"

    # ---------------- 绘制 ----------------

    def draw(self):
        s = self.screen
        s.fill(BG_COLOR)
        # 道路
        pygame.draw.lines(s, PATH_COLOR, False, PATH_POINTS, CELL - 8)
        for p in PATH_POINTS[1:-1]:
            pygame.draw.circle(s, PATH_COLOR, (int(p.x), int(p.y)), (CELL - 8) // 2)
        pygame.draw.circle(s, (200, 70, 70), (int(PATH_POINTS[0].x), int(PATH_POINTS[0].y)), 12)
        pygame.draw.circle(s, (90, 200, 255), (int(PATH_POINTS[-1].x), int(PATH_POINTS[-1].y)), 12)
        # 网格
        for c in range(COLS + 1):
            pygame.draw.line(s, GRID_COLOR, (c * CELL, 0), (c * CELL, H))
        for r in range(ROWS + 1):
            pygame.draw.line(s, GRID_COLOR, (0, r * CELL), (W, r * CELL))

        for e in self.enemies:
            e.draw(s)
        for t in self.towers.values():
            t.draw(s)
        for p in self.projectiles:
            p.draw(s)
        for pt in self.particles:
            pt.draw(s)

        self.draw_ghost(s)
        self.draw_sidebar(s)

        if self.msg_t > 0 and self.msg:
            img = get_font(18).render(self.msg, True, (255, 230, 150))
            rect = img.get_rect(center=(W // 2, H - 24))
            bg = rect.inflate(24, 10)
            pygame.draw.rect(s, (0, 0, 0), bg, border_radius=6)
            s.blit(img, rect)

        # 开局引导提示
        if self.state == "playing" and self.wave == 0 and not self.wave_active and not self.paused:
            lines = [
                "点击右侧按钮 (或按 1/2/3) 选择防御塔，再点击地图空地建造",
                "建好后按 空格 或点击右下「开始第 1 波」按钮出怪",
            ]
            imgs = [get_font(20).render(t, True, (255, 230, 150)) for t in lines]
            bw = max(i.get_width() for i in imgs) + 36
            bh = len(imgs) * 34 + 20
            box = pygame.Surface((bw, bh), pygame.SRCALPHA)
            box.fill((0, 0, 0, 170))
            s.blit(box, (W // 2 - bw // 2, H // 2 - bh // 2))
            for i, img in enumerate(imgs):
                s.blit(img, (W // 2 - img.get_width() // 2, H // 2 - bh // 2 + 12 + i * 34))

        if self.paused and self.state == "playing":
            self.draw_overlay(s, "已暂停", "按 P 继续")
        elif self.state == "gameover":
            self.draw_overlay(s, "游戏结束", f"得分 {self.score} · 击杀 {self.kills} · 坚持到第 {self.wave} 波")
        elif self.state == "victory":
            self.draw_overlay(s, "胜利! 你守住了所有波次", f"得分 {self.score} · 击杀 {self.kills} · 剩余生命 {self.lives}")

    def draw_ghost(self, s):
        x, y = self.mouse
        if x >= W:
            return
        cell = (x // CELL, y // CELL)
        if self.placing:
            ok = cell not in PATH_CELLS and cell not in self.towers and self.gold >= TOWER_TYPES[self.placing]["cost"]
            cfg = TOWER_TYPES[self.placing]
            cx, cy = cell[0] * CELL + CELL // 2, cell[1] * CELL + CELL // 2
            ghost = pygame.Surface((W, H), pygame.SRCALPHA)
            col = (120, 255, 120) if ok else (255, 90, 90)
            pygame.draw.circle(ghost, (*col, 60), (cx, cy), int(cfg["range"]))
            pygame.draw.circle(ghost, (*col, 160), (cx, cy), 15)
            s.blit(ghost, (0, 0))
            pygame.draw.rect(s, col, (cell[0] * CELL, cell[1] * CELL, CELL, CELL), 2)
        elif self.selected:
            rng = int(self.selected.stat("range"))
            cx, cy = int(self.selected.pos.x), int(self.selected.pos.y)
            ghost = pygame.Surface((W, H), pygame.SRCALPHA)
            pygame.draw.circle(ghost, (255, 255, 255, 45), (cx, cy), rng)
            pygame.draw.circle(ghost, (255, 255, 255, 120), (cx, cy), rng, 1)
            s.blit(ghost, (0, 0))

    def draw_sidebar(self, s):
        pygame.draw.rect(s, PANEL_COLOR, (W, 0, SIDEBAR, H))
        pygame.draw.line(s, (70, 80, 100), (W, 0), (W, H), 2)
        draw_text(s, "像素塔防", (W + 14, 12), 26, (255, 220, 120))

        draw_text(s, f"金币  {self.gold}", (W + 14, 54), 19, (255, 215, 90))
        draw_text(s, f"生命  {self.lives}", (W + 14, 80), 19, (255, 120, 120))
        wave_txt = f"波次  {self.wave}/{FINAL_WAVE}" if self.wave else f"波次  -/{FINAL_WAVE}"
        draw_text(s, wave_txt, (W + 14, 106), 19)
        draw_text(s, f"击杀  {self.kills}", (W + 14, 132), 19)

        draw_text(s, "—— 建造 ——", (W + 14, 156), 15, (150, 160, 180))
        for i, (kind, btn) in enumerate(self.btn_towers.items()):
            cfg = TOWER_TYPES[kind]
            btn.text = f"{i+1} {cfg['name']}  ${cfg['cost']}"
            btn.highlight = self.placing == kind
            btn.enabled = self.gold >= cfg["cost"]
            btn.draw(s, self.mouse)
            draw_text(s, cfg["desc"], (btn.rect.right - 62, btn.rect.bottom - 18), 12, (170, 178, 195))

        # 选中塔信息
        t = self.selected
        if t:
            cfg = TOWER_TYPES[t.kind]
            draw_text(s, f"{cfg['name']}  Lv.{t.level}", (W + 14, 350), 18, (255, 220, 120))
            draw_text(s, f"伤害 {t.stat('damage'):.0f}   射程 {t.stat('range'):.0f}", (W + 14, 376), 15)
            draw_text(s, f"攻速 {t.stat('rate'):.1f}/s", (W + 14, 398), 15)
            if t.level < MAX_LEVEL:
                self.btn_upgrade.text = f"升级 ${t.upgrade_cost()}"
                self.btn_upgrade.enabled = self.gold >= t.upgrade_cost()
            else:
                self.btn_upgrade.text = "已满级"
                self.btn_upgrade.enabled = False
            self.btn_sell.text = f"出售 +${int(t.invested * 0.7)}"
        else:
            draw_text(s, "点击已建的塔可升级/出售", (W + 14, 350), 14, (140, 148, 165))
        self.btn_upgrade.visible = self.btn_sell.visible = t is not None
        self.btn_upgrade.draw(s, self.mouse)
        self.btn_sell.draw(s, self.mouse)

        if self.wave_active:
            remain = len(self.enemies) + len(self.spawn_queue)
            self.btn_start.text = f"战斗中… 敌人 {remain}"
            self.btn_start.enabled = False
        else:
            self.btn_start.text = f"开始第 {self.wave + 1} 波"
            self.btn_start.enabled = True
        self.btn_start.draw(s, self.mouse)

        self.btn_pause.text = "继续" if self.paused else "暂停"
        self.btn_pause.draw(s, self.mouse)
        self.btn_speed.text = f"速度 x{self.speed}"
        self.btn_speed.draw(s, self.mouse)

    def draw_overlay(self, s, title, subtitle):
        ov = pygame.Surface((W, H), pygame.SRCALPHA)
        ov.fill((0, 0, 0, 175))
        s.blit(ov, (0, 0))
        draw_text(s, title, (W // 2, H // 2 - 30), 40, (255, 220, 120), center=True)
        draw_text(s, subtitle, (W // 2, H // 2 + 12), 18, center=True)
        if self.state in ("gameover", "victory"):
            self.btn_restart.draw(s, self.mouse)
            draw_text(s, "或按 R 键", (W // 2, H // 2 + 100), 14, (170, 178, 195), center=True)


# ---------------------------------------------------------------- 入口

def main():
    pygame.init()
    pygame.display.set_caption("像素塔防 - Pixel Tower Defense")
    screen = pygame.display.set_mode((WIN_W, WIN_H))
    game = Game(screen)
    clock = pygame.time.Clock()
    running = True
    while running:
        dt = clock.tick(FPS) / 1000.0
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            else:
                game.handle_event(event)
        game.mouse = pygame.mouse.get_pos()
        for _ in range(game.speed):
            game.update(dt)
        game.draw()
        pygame.display.flip()
    pygame.quit()


if __name__ == "__main__":
    main()
