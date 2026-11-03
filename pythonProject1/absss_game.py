# -*- coding: utf-8 -*-
"""
深渊争霸 (Abyss Conquest) —— 类魔兽争霸即时战略游戏 (单文件, pygame)

操作说明:
  鼠标左键      : 选择单位 / 拖拽框选 / 点击命令按钮 / 点击小地图移动镜头
  鼠标右键      : 移动 / 攻击 / 采集 / 放置建筑(选中农民后) / 取消放置
  WASD/方向键    : 移动镜头 (鼠标移到屏幕边缘也可滚动)
  A + 左键      : 攻击移动
  S             : 停止
  空格          : 镜头回到主城
  ESC           : 取消选择 / 取消放置

玩法:
  采集金矿与木材 -> 建造农场(人口)/兵营/箭塔 -> 训练军队 -> 摧毁右下角兽人大厅
  兽人会定期发动波次进攻，主城被摧毁则失败。
"""
import sys
import os
import math
import random
import heapq

import pygame

# ---------------------------------------------------------------- 配置 ----
SCREEN_W, SCREEN_H = 1280, 720
UI_TOP = 30
UI_BOTTOM = 150
MINIMAP = 138
TILE = 32
MAP_W = MAP_H = 64
WORLD_W = WORLD_H = MAP_W * TILE
FPS = 60

# ---------------------------------------------------------------- 颜色 ----
C_BG = (12, 12, 16)
C_PANEL = (34, 34, 46)
C_PANEL_HI = (52, 52, 70)
C_BORDER = (90, 90, 110)
C_TEXT = (235, 235, 235)
C_GOLD = (255, 205, 60)
C_WOOD = (190, 140, 70)
C_FOOD = (120, 220, 120)
C_SEL = (90, 240, 120)
C_HP = (90, 220, 90)
C_HPBAD = (220, 70, 60)

# ---------------------------------------------------------------- 字体 ----
_FONTS = {}


def _load_font(size):
    for name in ("pingfangsc", "pingfang", "hiraginosansgb", "heiti tc",
                 "stheiti", "arialunicodems", "microsoftyahei", "simsun"):
        path = pygame.font.match_font(name)
        if path:
            return pygame.font.Font(path, size)
    return pygame.font.Font(None, size + 4)


def font(size):
    f = _FONTS.get(size)
    if f is None:
        f = _load_font(size)
        _FONTS[size] = f
    return f


def draw_text(scr, text, size, x, y, color=C_TEXT, anchor="tl", shadow=True):
    s = font(size).render(text, True, color)
    r = s.get_rect()
    if anchor == "tl":
        r.topleft = (x, y)
    elif anchor == "center":
        r.center = (x, y)
    elif anchor == "tr":
        r.topright = (x, y)
    elif anchor == "ml":
        r.midleft = (x, y)
    elif anchor == "mc":
        r.center = (x, y)
    if shadow:
        sh = font(size).render(text, True, (0, 0, 0))
        scr.blit(sh, (r.x + 1, r.y + 1))
    scr.blit(s, r)
    return r


# ---------------------------------------------------------------- 音效 ----
_SOUNDS = {}
_SFX_READY = False
_LAST_SFX = {}


def init_sounds():
    global _SFX_READY
    try:
        import numpy as np
        pygame.mixer.init(22050, -16, 2, 512)
        sr = 22050

        def env(t, a=0.01, dur=None):
            e = np.minimum(1.0, t / max(a, 1e-4))
            if dur:
                e *= np.clip(1.0 - (t / dur), 0, 1) ** 1.5
            return e

        def tone(f0, f1, dur, wave="sine", vol=0.30):
            t = np.linspace(0, dur, int(sr * dur), endpoint=False)
            freq = f0 + (f1 - f0) * (t / dur)
            ph = 2 * np.pi * np.cumsum(freq) / sr
            if wave == "saw":
                w = 2 * ((ph / (2 * np.pi)) % 1.0) - 1
            elif wave == "square":
                w = np.sign(np.sin(ph))
            else:
                w = np.sin(ph)
            return (w * env(t, dur=dur) * vol).astype(np.float32)

        def noise(dur, vol=0.25, lp=0.4):
            t = np.linspace(0, dur, int(sr * dur), endpoint=False)
            n = np.random.RandomState(7).uniform(-1, 1, len(t))
            for _ in range(3):
                n = np.convolve(n, [lp, 1 - lp], "same")
            return (n * env(t, dur=dur) * vol).astype(np.float32)

        def mk(*parts):
            x = np.concatenate(parts)
            m = max(1e-6, float(np.max(np.abs(x))))
            x = np.clip(x / m, -1, 1)
            st = np.column_stack([x, x])
            return pygame.sndarray.make_sound((st * 32000).astype(np.int16))

        _SOUNDS["click"] = mk(tone(900, 700, 0.06, vol=0.2))
        _SOUNDS["move"] = mk(tone(520, 640, 0.07, vol=0.16))
        _SOUNDS["hit"] = mk(noise(0.09, 0.5), tone(160, 90, 0.09, vol=0.5))
        _SOUNDS["arrow"] = mk(noise(0.14, 0.35, 0.2))
        _SOUNDS["die"] = mk(tone(300, 70, 0.35, "saw", 0.4))
        _SOUNDS["coin"] = mk(tone(1200, 1200, 0.07, vol=0.25), tone(1600, 1600, 0.10, vol=0.25))
        _SOUNDS["chop"] = mk(tone(240, 200, 0.05, "square", 0.3), noise(0.05, 0.3))
        _SOUNDS["done"] = mk(tone(660, 660, 0.10, vol=0.3), tone(880, 880, 0.16, vol=0.3))
        _SOUNDS["build"] = mk(tone(220, 200, 0.06, "square", 0.35))
        _SOUNDS["wave"] = mk(tone(110, 100, 0.7, "saw", 0.5), tone(165, 150, 0.7, vol=0.3))
        _SOUNDS["crash"] = mk(noise(0.4, 0.7, 0.6), tone(120, 50, 0.4, vol=0.6))
        _SFX_READY = True
    except Exception:
        _SFX_READY = False


def sfx(name):
    if not _SFX_READY:
        return
    now = pygame.time.get_ticks()
    gap = 90 if name in ("hit", "chop", "build") else 0
    if gap and now - _LAST_SFX.get(name, -9999) < gap:
        return
    _LAST_SFX[name] = now
    s = _SOUNDS.get(name)
    if s:
        try:
            s.play()
        except Exception:
            pass


# ------------------------------------------------------------- 寻路 A* ----
def nearest_free_tile(tx, ty, blocked, max_r=14):
    if 0 <= tx < MAP_W and 0 <= ty < MAP_H and not blocked[tx][ty]:
        return (tx, ty)
    for r in range(1, max_r + 1):
        cands = []
        for dx in range(-r, r + 1):
            for dy in range(-r, r + 1):
                if max(abs(dx), abs(dy)) != r:
                    continue
                nx, ny = tx + dx, ty + dy
                if 0 <= nx < MAP_W and 0 <= ny < MAP_H and not blocked[nx][ny]:
                    cands.append((dx * dx + dy * dy, nx, ny))
        if cands:
            cands.sort()
            return (cands[0][1], cands[0][2])
    return None


def astar(start, goal, blocked):
    if start == goal:
        return []
    goal = nearest_free_tile(goal[0], goal[1], blocked)
    if goal is None:
        return None
    if start == goal:
        return [goal]
    open_h = [(0.0, start)]
    came = {start: None}
    g = {start: 0.0}
    it = 0
    while open_h and it < 8000:
        it += 1
        _, cur = heapq.heappop(open_h)
        if cur == goal:
            path = []
            while cur and cur != start:
                path.append(cur)
                cur = came[cur]
            path.reverse()
            return path
        x, y = cur
        gc = g[cur]
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if dx == 0 and dy == 0:
                    continue
                nx, ny = x + dx, y + dy
                if not (0 <= nx < MAP_W and 0 <= ny < MAP_H):
                    continue
                if blocked[nx][ny]:
                    continue
                if dx and dy and (blocked[x + dx][y] or blocked[x][y + dy]):
                    continue
                npos = (nx, ny)
                ng = gc + (1.414 if dx and dy else 1.0)
                if ng < g.get(npos, 1e18):
                    g[npos] = ng
                    came[npos] = cur
                    ax, ay = abs(nx - goal[0]), abs(ny - goal[1])
                    h = max(ax, ay) + 0.414 * min(ax, ay)
                    heapq.heappush(open_h, (ng + h, npos))
    return None


# --------------------------------------------------------------- 数据 ----
UNIT_TYPES = {
    "worker": dict(name="农民", hp=60, dmg=5, range_=16, speed=95, cd=1.0,
                   cost_g=50, cost_w=0, food=1, bt=9, r=8, aggro=0),
    "footman": dict(name="步兵", hp=150, dmg=13, range_=20, speed=82, cd=0.9,
                    cost_g=90, cost_w=0, food=1, bt=12, r=9, aggro=190),
    "archer": dict(name="弓箭手", hp=95, dmg=11, range_=150, speed=86, cd=1.2,
                   cost_g=100, cost_w=30, food=1, bt=13, r=8, aggro=200, ranged=True),
    "knight": dict(name="骑士", hp=290, dmg=22, range_=22, speed=112, cd=0.9,
                   cost_g=180, cost_w=40, food=2, bt=18, r=10, aggro=210),
    "grunt": dict(name="兽人步兵", hp=155, dmg=14, range_=20, speed=82, cd=0.9,
                  cost_g=0, cost_w=0, food=0, bt=10, r=9, aggro=220),
    "troll": dict(name="巨魔猎手", hp=110, dmg=12, range_=145, speed=80, cd=1.3,
                  cost_g=0, cost_w=0, food=0, bt=12, r=8, aggro=220, ranged=True),
    "ogre": dict(name="食人魔", hp=470, dmg=34, range_=26, speed=68, cd=1.4,
                 cost_g=0, cost_w=0, food=0, bt=14, r=12, aggro=150),
}
BUILDING_TYPES = {
    "hall": dict(name="主城", hp=900, w=3, h=3, trains=["worker"], food=6,
                 bt=30, cost_g=300, cost_w=150, deposit=True),
    "barracks": dict(name="兵营", hp=600, w=2, h=2, trains=["footman", "archer", "knight"],
                     food=0, bt=20, cost_g=150, cost_w=60),
    "farm": dict(name="农场", hp=320, w=2, h=2, food=8, bt=12, cost_g=80, cost_w=20),
    "tower": dict(name="箭塔", hp=430, w=2, h=2, dmg=15, range_=195, cd=1.0,
                  food=0, bt=15, cost_g=110, cost_w=70),
    "ehall": dict(name="兽人大厅", hp=1300, w=3, h=3, food=0, bt=1, cost_g=0, cost_w=0),
}

SPREAD = []
for _ring in range(6):
    _n = _ring * 6 if _ring > 0 else 1
    for _k in range(_n):
        _a = _k * 2 * math.pi / _n + _ring * 0.6
        SPREAD.append((math.cos(_a) * _ring * 26, math.sin(_a) * _ring * 26))


def lerp_color(c, d, t):
    return tuple(int(a + (b - a) * t) for a, b in zip(c, d))


# --------------------------------------------------------------- 实体 ----
class Tree:
    def __init__(self, tx, ty, variant):
        self.team = -1  # 中立，不可选
        self.tx, self.ty = tx, ty
        self.x = tx * TILE + TILE / 2
        self.y = ty * TILE + TILE / 2
        self.kind = "wood"
        self.r = 9
        self.amount = 100
        self.variant = variant
        self.dead = False


class GoldMine:
    def __init__(self, tx, ty):
        self.team = -1  # 中立，不可选
        self.tx, self.ty = tx, ty  # 2x2 左上
        self.x = tx * TILE + TILE
        self.y = ty * TILE + TILE
        self.kind = "gold"
        self.r = 30
        self.amount = 8000
        self.dead = False


class Projectile:
    def __init__(self, x, y, target, dmg, team):
        self.x, self.y = x, y
        self.target = target
        self.tx, self.ty = target.x, target.y
        self.dmg = dmg
        self.team = team
        self.speed = 330
        self.dead = False

    def update(self, dt, game):
        t = self.target
        if t is not None and not t.dead:
            self.tx, self.ty = t.x, t.y
        dx, dy = self.tx - self.x, self.ty - self.y
        d = math.hypot(dx, dy)
        step = self.speed * dt
        if d <= max(step, 8):
            self.dead = True
            if t is not None and not t.dead:
                game.damage(t, self.dmg)
        else:
            self.x += dx / d * step
            self.y += dy / d * step


class Particle:
    def __init__(self, x, y, color, life=0.5, size=3, vx=0.0, vy=0.0, grav=0.0):
        self.x, self.y = x, y
        self.color = color
        self.life = life
        self.max_life = life
        self.size = size
        self.vx, self.vy = vx, vy
        self.grav = grav

    def update(self, dt):
        self.life -= dt
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.vy += self.grav * dt

    @property
    def dead(self):
        return self.life <= 0


class FloatText:
    def __init__(self, x, y, text, color):
        self.x, self.y = x, y
        self.text = text
        self.color = color
        self.t = 1.2

    @property
    def dead(self):
        return self.t <= 0


class Unit:
    def __init__(self, type_, team, x, y):
        t = UNIT_TYPES[type_]
        self.type = type_
        self.team = team
        self.x, self.y = float(x), float(y)
        self.hp = self.max_hp = t["hp"]
        self.r = t["r"]
        self.speed = t["speed"]
        self.dmg = t["dmg"]
        self.range = t["range_"]
        self.cd_max = t["cd"]
        self.cd = 0.0
        self.aggro = t["aggro"]
        self.ranged = t.get("ranged", False)
        self.food = t["food"]
        self.name = t["name"]
        self.state = "idle"
        self.path = []
        self.move_to = None
        self.target = None
        self.order_dest = None
        self.carry = 0
        self.carry_kind = None
        self.res_target = None
        self.gather_t = 0.0
        self.build_target = None
        self.repath = 0.0
        self.flash = 0.0
        self.swing = 0.0
        self.face = random.random() * math.tau
        self.moving = False
        self.scan_t = random.random() * 0.3
        self.hammer_t = 0.0
        self.phase = random.random() * math.tau
        self.dead = False

    # ---- 命令 ----
    def stop(self):
        self.state = "idle"
        self.path = []
        self.move_to = None
        self.target = None
        self.order_dest = None

    def set_dest(self, wx, wy, game):
        self.state = "move"
        self.target = None
        self.order_dest = None
        self._do_move(wx, wy, game)

    def order_attack_move(self, wx, wy, game):
        self.state = "attack_move"
        self.order_dest = (wx, wy)
        self._do_move(wx, wy, game)

    def order_attack(self, target, game):
        self.state = "attack"
        self.target = target
        self.order_dest = None
        self.path = []
        self.repath = 0.0

    def order_harvest(self, res, game):
        if self.type != "worker":
            self.set_dest(res.x, res.y, game)
            return
        self.res_target = res
        self.carry_kind = res.kind
        self.state = "to_res"
        self.path = []
        self.move_to = None
        self._do_move(res.x, res.y, game)

    def order_build(self, site, game):
        if self.type != "worker" or site.dead:
            return
        self.build_target = site
        self.state = "to_build"
        self.path = []
        self.move_to = None
        self._do_move(site.x, site.y, game)

    def _do_move(self, wx, wy, game):
        wx = max(TILE, min(WORLD_W - TILE, wx))
        wy = max(TILE, min(WORLD_H - TILE, wy))
        sx, sy = int(self.x // TILE), int(self.y // TILE)
        tx, ty = int(wx // TILE), int(wy // TILE)
        t = game.nearest_free(tx, ty)
        if t is None:
            self.path = []
            self.move_to = (wx, wy)
            return
        if (sx, sy) == t:
            self.path = []
            self.move_to = (wx, wy) if game.walkable_px(wx, wy) else None
            return
        path = astar((sx, sy), t, game.blocked)
        if not path:
            self.path = []
            self.move_to = (wx, wy)
            return
        self.path = [(p[0] * TILE + TILE / 2, p[1] * TILE + TILE / 2) for p in path]
        if path[-1] == (tx, ty) and game.walkable_px(wx, wy):
            self.path[-1] = (wx, wy)
        self.move_to = None

    # ---- 移动 ----
    def _step(self, dx, dy, game):
        if dx:
            nx = max(TILE, min(WORLD_W - TILE, self.x + dx))
            if game.walkable_px(nx, self.y):
                self.x = nx
        if dy:
            ny = max(TILE, min(WORLD_H - TILE, self.y + dy))
            if game.walkable_px(self.x, ny):
                self.y = ny

    def follow(self, dt, game):
        if self.path:
            wx, wy = self.path[0]
            dx, dy = wx - self.x, wy - self.y
            d = math.hypot(dx, dy)
            if d < 8:
                self.path.pop(0)
                return False
            self.face = math.atan2(dy, dx)
            self._step(dx / d * self.speed * dt, dy / d * self.speed * dt, game)
            self.moving = True
            return False
        if self.move_to:
            dx, dy = self.move_to[0] - self.x, self.move_to[1] - self.y
            d = math.hypot(dx, dy)
            if d < 6:
                self.move_to = None
                return True
            self.face = math.atan2(dy, dx)
            self._step(dx / d * self.speed * dt, dy / d * self.speed * dt, game)
            self.moving = True
            return False
        return True

    # ---- 状态机 ----
    def update(self, dt, game):
        self.cd = max(0.0, self.cd - dt)
        self.flash = max(0.0, self.flash - dt)
        self.swing = max(0.0, self.swing - dt)
        self.moving = False
        st = self.state
        if st == "idle":
            self._idle(dt, game)
        elif st == "move":
            if self.follow(dt, game):
                self.state = "idle"
        elif st == "attack_move":
            self._attack_move(dt, game)
        elif st == "attack":
            self._attack(dt, game)
        elif st == "to_res":
            self._to_res(dt, game)
        elif st == "gather":
            self._gather(dt, game)
        elif st == "to_base":
            self._to_base(dt, game)
        elif st == "to_build":
            self._to_build(dt, game)
        elif st == "building":
            self._building(dt, game)

    def _idle(self, dt, game):
        if self.aggro <= 0:
            return
        self.scan_t -= dt
        if self.scan_t <= 0:
            self.scan_t = 0.35
            e = game.find_enemy(self.x, self.y, self.aggro, self.team)
            if e:
                self.order_attack(e, game)

    def _attack_move(self, dt, game):
        self.scan_t -= dt
        if self.scan_t <= 0:
            self.scan_t = 0.35
            e = game.find_enemy(self.x, self.y, self.aggro, self.team)
            if e:
                self.order_attack(e, game)
                return
        if self.order_dest is None:
            self.state = "idle"
            return
        if self.follow(dt, game):
            self.state = "idle"
            self.order_dest = None

    def _attack(self, dt, game):
        t = self.target
        if t is None or t.dead:
            if self.order_dest:
                self.state = "attack_move"
                self.target = None
                self._do_move(*self.order_dest, game)
            else:
                self.state = "idle"
            return
        d = game.edge_dist(self, t)
        if d <= self.range:
            self.path = []
            self.move_to = None
            self.face = math.atan2(t.y - self.y, t.x - self.x)
            if self.cd <= 0:
                self.cd = self.cd_max
                self.swing = 0.25
                if self.ranged:
                    game.projectiles.append(
                        Projectile(self.x, self.y - 12, t, self.dmg, self.team))
                    sfx("arrow")
                else:
                    game.damage(t, self.dmg)
        else:
            self.repath -= dt
            if d < 90:
                self.path = []
                self.move_to = None
                dx, dy = t.x - self.x, t.y - self.y
                dd = math.hypot(dx, dy) or 1.0
                self.face = math.atan2(dy, dx)
                self._step(dx / dd * self.speed * dt, dy / dd * self.speed * dt, game)
                self.moving = True
            else:
                if self.repath <= 0:
                    self.repath = 0.45
                    self._do_move(t.x, t.y, game)
                self.follow(dt, game)

    def _to_res(self, dt, game):
        res = self.res_target
        if res is None or res.dead:
            if not self._find_next_res(game):
                self.state = "idle"
            return
        reach = 60 if res.kind == "gold" else 46
        if game.edge_dist(self, res) <= reach:
            self.path = []
            self.move_to = None
            self.state = "gather"
            self.gather_t = 3.0
            self.face = math.atan2(res.y - self.y, res.x - self.x)
        else:
            self.repath -= dt
            if not self.path and not self.move_to and self.repath <= 0:
                self.repath = 0.5
                self._do_move(res.x, res.y, game)
            if self.follow(dt, game):
                self._do_move(res.x, res.y, game)

    def _gather(self, dt, game):
        res = self.res_target
        if res is None or res.dead:
            if not self._find_next_res(game):
                self.state = "to_base" if self.carry else "idle"
            return
        self.face = math.atan2(res.y - self.y, res.x - self.x)
        self.hammer_t -= dt
        if self.hammer_t <= 0:
            self.hammer_t = 0.5
            self.swing = 0.25
            sfx("chop")
            col = (255, 215, 90) if res.kind == "gold" else (150, 110, 60)
            game.particles.append(Particle(
                res.x + random.uniform(-8, 8), res.y - 10,
                col, 0.4, 2.5, random.uniform(-30, 30), -40, 120))
        self.gather_t -= dt
        if self.gather_t <= 0:
            self.carry = 10
            if res.kind == "gold":
                res.amount -= 10
                if res.amount <= 0:
                    res.dead = True
                    game.unblock_rect(res.tx, res.ty, 2, 2)
                    game.mm_dirty = True
            else:
                res.amount -= 10
                if res.amount <= 0:
                    res.dead = True
                    game.unblock_rect(res.tx, res.ty, 1, 1)
                    game.mm_dirty = True
            self.state = "to_base"
            self.path = []
            self.move_to = None

    def _find_next_res(self, game):
        kind = self.carry_kind or "wood"
        best, bd = None, 1e18
        pool = game.mines if kind == "gold" else game.trees
        for r in pool:
            if r.dead:
                continue
            d = math.hypot(r.x - self.x, r.y - self.y)
            if d < bd:
                best, bd = r, d
        if best and bd < 320:
            self.res_target = best
            self.state = "to_res"
            self.repath = 0.0
            return True
        self.res_target = None
        return False

    def _to_base(self, dt, game):
        hall = game.nearest_hall(self.x, self.y)
        if hall is None:
            self.state = "idle"
            return
        if game.edge_dist(self, hall) <= 75:
            if self.carry:
                if self.carry_kind == "gold":
                    game.gold += self.carry
                else:
                    game.wood += self.carry
                game.texts.append(FloatText(hall.x, hall.y - 30, "+%d %s" % (
                    self.carry, "黄金" if self.carry_kind == "gold" else "木材"),
                    C_GOLD if self.carry_kind == "gold" else C_WOOD))
                sfx("coin")
                self.carry = 0
            if self.res_target and not self.res_target.dead:
                self.state = "to_res"
                self.repath = 0.0
            elif not self._find_next_res(game):
                self.state = "idle"
        else:
            self.repath -= dt
            if not self.path and not self.move_to and self.repath <= 0:
                self.repath = 0.5
                self._do_move(hall.x, hall.y, game)
            if self.follow(dt, game):
                self._do_move(hall.x, hall.y, game)

    def _to_build(self, dt, game):
        site = self.build_target
        if site is None or site.dead or not site.under_construction:
            self.state = "idle"
            return
        if game.edge_dist(self, site) <= site.r + self.r + 20:
            self.path = []
            self.move_to = None
            self.state = "building"
            self.face = math.atan2(site.y - self.y, site.x - self.x)
        else:
            self.repath -= dt
            if not self.path and not self.move_to and self.repath <= 0:
                self.repath = 0.5
                self._do_move(site.x, site.y, game)
            if self.follow(dt, game):
                self._do_move(site.x, site.y, game)

    def _building(self, dt, game):
        site = self.build_target
        if site is None or site.dead or not site.under_construction:
            sfx("done")
            self.state = "idle"
            return
        site.progress = min(100.0, site.progress + dt * 100.0 / BUILDING_TYPES[site.type]["bt"])
        self.hammer_t -= dt
        if self.hammer_t <= 0:
            self.hammer_t = 0.55
            self.swing = 0.25
            sfx("build")
            game.particles.append(Particle(
                site.x + random.uniform(-14, 14), site.y - 6,
                (200, 200, 200), 0.35, 2.5, random.uniform(-40, 40), -50, 150))
        if site.progress >= 100:
            site.under_construction = False
            site.hp = site.max_hp
            sfx("done")
            game.announce("%s建造完成" % BUILDING_TYPES[site.type]["name"])
            game.mm_dirty = True
            self.state = "idle"


class Building:
    def __init__(self, type_, team, tx, ty, construct=False):
        t = BUILDING_TYPES[type_]
        self.type = type_
        self.team = team
        self.tx, self.ty = tx, ty
        self.w, self.h = t["w"], t["h"]
        self.x = tx * TILE + self.w * TILE / 2
        self.y = ty * TILE + self.h * TILE / 2
        self.r = max(self.w, self.h) * TILE * 0.45
        self.max_hp = t["hp"]
        self.under_construction = construct
        self.progress = 0.0 if construct else 100.0
        self.hp = self.max_hp * 0.3 if construct else self.max_hp
        self.queue = []
        self.prod_t = 0.0
        self.range = t.get("range_", 0)
        self.dmg = t.get("dmg", 0)
        self.cd = 0.0
        self.swing = 0.0
        self.name = t["name"]
        self.rally = None
        self.dead = False

    def update(self, dt, game):
        if self.under_construction:
            return
        if self.queue:
            self.prod_t += dt
            need = UNIT_TYPES[self.queue[0]]["bt"]
            if self.prod_t >= need:
                it = self.queue.pop(0)
                self.prod_t = 0.0
                pos = game.find_free_adjacent(self)
                u = Unit(it, self.team, pos[0], pos[1])
                game.units.append(u)
                sfx("done")
                if self.rally:
                    u.set_dest(self.rally[0], self.rally[1], game)
                elif self.team == 1:
                    ph = game.player_hall
                    if ph and not ph.dead:
                        u.order_attack_move(ph.x, ph.y, game)
        if self.type == "tower":
            self.cd = max(0.0, self.cd - dt)
            self.swing = max(0.0, self.swing - dt)
            if self.cd <= 0:
                e = game.find_enemy(self.x, self.y, self.range, self.team)
                if e:
                    self.cd = BUILDING_TYPES["tower"]["cd"]
                    self.swing = 0.2
                    game.projectiles.append(Projectile(self.x, self.y - 40, e, self.dmg, self.team))
                    sfx("arrow")


# --------------------------------------------------------------- 游戏 ----
class Game:
    def __init__(self):
        self.rng = random.Random()
        self.blocked = [[False] * MAP_H for _ in range(MAP_W)]
        self.trees = []
        self.mines = []
        self.buildings = []
        self.units = []
        self.projectiles = []
        self.particles = []
        self.texts = []
        self.announces = []
        self.gold = 400
        self.wood = 200
        self.wave_timer = 100.0
        self.wave_n = 0
        self.ehall_timer = 25.0
        self.time = 0.0
        self.state = "play"
        self.cam_x = 0.0
        self.cam_y = 0.0
        self.selection = []
        self.placing = None
        self.atk_move = False
        self.drag_start = None
        self.drag_minimap = False
        self.cmd_buttons = []
        self.mouse_pos = (SCREEN_W // 2, SCREEN_H // 2)
        self.mm_dirty = True
        self.mm_base = None
        self._ghost_cache = {}
        self._gen_map()
        self._build_terrain()
        self.mm_dirty = True
        self.food_limit = sum(BUILDING_TYPES[b.type].get("food", 0)
                              for b in self.buildings if b.team == 0)
        ph = self.player_hall
        self.cam_x = ph.x - SCREEN_W / 2
        self.cam_y = ph.y - SCREEN_H / 2
        self._clamp_cam()
        self.announce("欢迎来到深渊争霸！", 6)
        self.announce("左键选择 / 框选，右键移动、攻击、采集", 6)
        self.announce("目标：摧毁右下角的兽人大厅！", 6)

    # ---- 地图 ----
    def _gen_map(self):
        b = self.blocked
        for i in range(MAP_W):
            for j in (0, 1, MAP_H - 1, MAP_H - 2):
                b[i][j] = True
        for j in range(MAP_H):
            for i in (0, 1, MAP_W - 1, MAP_W - 2):
                b[i][j] = True
        # 主城与兽人大厅
        self.player_hall = Building("hall", 0, 10, 10)
        self.ehall = Building("ehall", 1, 48, 48)
        self.buildings += [self.player_hall, self.ehall]
        self.block_rect(self.player_hall.tx, self.player_hall.ty, 3, 3)
        self.block_rect(self.ehall.tx, self.ehall.ty, 3, 3)
        # 金矿
        for tx, ty in ((6, 17), (17, 6), (44, 54), (54, 44), (30, 10), (10, 30), (30, 30)):
            m = GoldMine(tx, ty)
            self.mines.append(m)
            self.block_rect(tx, ty, 2, 2)
        # 树木
        def far_from_base(tx, ty):
            for bx, by in ((10, 10), (48, 48)):
                if math.hypot(tx - bx, ty - by) < 9:
                    return False
            for m in self.mines:
                if abs(tx - (m.tx + 1)) < 3 and abs(ty - (m.ty + 1)) < 3:
                    return False
            return True
        rng = self.rng
        for _ in range(60):
            cx, cy = rng.randint(4, MAP_W - 5), rng.randint(4, MAP_H - 5)
            for _ in range(rng.randint(6, 13)):
                tx, ty = cx + rng.randint(-3, 3), cy + rng.randint(-3, 3)
                if 2 <= tx < MAP_W - 2 and 2 <= ty < MAP_H - 2 and \
                        not b[tx][ty] and far_from_base(tx, ty):
                    t = Tree(tx, ty, rng.randint(0, 2))
                    self.trees.append(t)
                    b[tx][ty] = True
        # 初始单位
        for _ in range(4):
            self._spawn_near("worker", 0, self.player_hall)
        for _ in range(2):
            self._spawn_near("footman", 0, self.player_hall)
        for _ in range(4):
            self._spawn_near("grunt", 1, self.ehall)
        for _ in range(2):
            self._spawn_near("troll", 1, self.ehall)
        # 中立食人魔守中央金矿
        center = self.mines[-1]
        for _ in range(3):
            pos = self.find_free_adjacent_rect(center.tx, center.ty, 2, 2)
            self.units.append(Unit("ogre", 2, pos[0], pos[1]))

    def _spawn_near(self, type_, team, bld):
        pos = self.find_free_adjacent(bld)
        self.units.append(Unit(type_, team, pos[0], pos[1]))

    def block_rect(self, tx, ty, w, h):
        for i in range(tx, tx + w):
            for j in range(ty, ty + h):
                if 0 <= i < MAP_W and 0 <= j < MAP_H:
                    self.blocked[i][j] = True

    def unblock_rect(self, tx, ty, w, h):
        for i in range(tx, tx + w):
            for j in range(ty, ty + h):
                if 0 <= i < MAP_W and 0 <= j < MAP_H:
                    self.blocked[i][j] = False

    def nearest_free(self, tx, ty):
        return nearest_free_tile(tx, ty, self.blocked)

    def walkable_px(self, x, y):
        tx, ty = int(x // TILE), int(y // TILE)
        return 0 <= tx < MAP_W and 0 <= ty < MAP_H and not self.blocked[tx][ty]

    def find_free_adjacent_rect(self, tx, ty, w, h):
        for r in range(1, 10):
            cands = []
            for dx in range(-r, w + r):
                for dy in range(-r, h + r):
                    nx, ny = tx + dx, ty + dy
                    edge = not (0 <= dx < w and 0 <= dy < h)
                    if not edge:
                        continue
                    if not (0 <= nx < MAP_W and 0 <= ny < MAP_H):
                        continue
                    if max(abs(min(dx, 0)), abs(max(dx, w - 1))) > r and False:
                        continue
                    if not self.blocked[nx][ny]:
                        cands.append((dx, dy, nx, ny))
            if cands:
                dx, dy, nx, ny = cands[len(cands) // 2]
                return (nx * TILE + TILE / 2, ny * TILE + TILE / 2)
        return (tx * TILE + w * TILE / 2, (ty + h) * TILE + TILE)

    def find_free_adjacent(self, b):
        return self.find_free_adjacent_rect(b.tx, b.ty, b.w, b.h)

    def edge_dist(self, a, b):
        return math.hypot(a.x - b.x, a.y - b.y) - a.r - b.r

    def find_enemy(self, x, y, radius, team):
        best, bd = None, radius
        for u in self.units:
            if u.team == team or u.dead:
                continue
            d = math.hypot(u.x - x, u.y - y) - u.r
            if d < bd:
                best, bd = u, d
        for b in self.buildings:
            if b.team == team or b.dead:
                continue
            d = math.hypot(b.x - x, b.y - y) - b.r
            if d < bd:
                best, bd = b, d
        return best

    def nearest_hall(self, x, y):
        best, bd = None, 1e18
        for b in self.buildings:
            if b.dead or b.team != 0 or b.type != "hall":
                continue
            d = math.hypot(b.x - x, b.y - y)
            if d < bd:
                best, bd = b, d
        return best

    def entity_at(self, wx, wy):
        for u in self.units:
            if math.hypot(u.x - wx, u.y - wy) <= u.r + 5:
                return u
        for b in self.buildings:
            if b.tx * TILE <= wx < (b.tx + b.w) * TILE and \
                    b.ty * TILE <= wy < (b.ty + b.h) * TILE:
                return b
        for t in self.trees:
            if not t.dead and math.hypot(t.x - wx, t.y - wy) <= 15:
                return t
        for m in self.mines:
            if not m.dead and m.tx * TILE <= wx < (m.tx + 2) * TILE and \
                    m.ty * TILE <= wy < (m.ty + 2) * TILE:
                return m
        return None

    # ---- 资源/伤害 ----
    def food_used(self):
        used = sum(u.food for u in self.units if u.team == 0 and not u.dead)
        for b in self.buildings:
            if b.team == 0 and not b.dead:
                for it in b.queue:
                    used += UNIT_TYPES[it]["food"]
        return used

    def add_res(self, kind, amount):
        if kind == "gold":
            self.gold += amount
        else:
            self.wood += amount

    def damage(self, t, dmg):
        if t.dead:
            return
        t.hp -= dmg
        t.flash = 0.15
        sfx("hit")
        for _ in range(3):
            self.particles.append(Particle(
                t.x + random.uniform(-6, 6), t.y - 10 + random.uniform(-6, 6),
                (200, 40, 40), 0.35, 2.5, random.uniform(-60, 60), random.uniform(-80, 20), 200))
        if t.hp <= 0:
            self.kill(t)

    def kill(self, t):
        t.dead = True
        sfx("die" if isinstance(t, Unit) else "crash")
        for _ in range(12):
            self.particles.append(Particle(
                t.x + random.uniform(-8, 8), t.y - 8 + random.uniform(-8, 8),
                random.choice([(180, 40, 40), (90, 70, 60), (60, 60, 60)]),
                0.6, 3, random.uniform(-90, 90), random.uniform(-120, 20), 260))
        if isinstance(t, Building):
            self.unblock_rect(t.tx, t.ty, t.w, t.h)
            self.mm_dirty = True
            if t.team == 0:
                self.announce("%s被摧毁了！" % t.name, 4)
            else:
                self.announce("摧毁了敌方的%s！" % t.name, 4)

    def announce(self, text, dur=4):
        self.announces.append([text, dur])
        if len(self.announces) > 3:
            self.announces.pop(0)

    # ---- 波次 ----
    def _spawn_wave(self):
        self.wave_n += 1
        self.wave_timer = 80.0
        n = self.wave_n
        comp = [("grunt", 1 + n), ("troll", max(0, n - 1)), ("ogre", min(2, (n - 3) // 2 if n >= 4 else 0))]
        ph = self.player_hall
        dest = (ph.x, ph.y) if ph and not ph.dead else (640, 640)
        total = sum(c for _, c in comp)
        self.announce("第 %d 波兽人进攻！共有 %d 个敌人" % (n, total), 5)
        sfx("wave")
        for utype, cnt in comp:
            for _ in range(cnt):
                pos = self.find_free_adjacent(self.ehall)
                u = Unit(utype, 1, pos[0], pos[1])
                u.order_attack_move(dest[0], dest[1], self)
                self.units.append(u)

    # ---- 更新 ----
    def update(self, dt):
        self.time += dt
        if self.state != "play":
            for p in self.particles:
                p.update(dt)
            self.particles = [p for p in self.particles if not p.dead]
            return
        # 波次
        self.wave_timer -= dt
        if self.wave_timer <= 0:
            self._spawn_wave()
        # 兽人大厅持续补兵
        if not self.ehall.dead:
            self.ehall_timer -= dt
            if self.ehall_timer <= 0:
                self.ehall_timer = 22.0
                if sum(1 for u in self.units if u.team == 1) < 14:
                    pos = self.find_free_adjacent(self.ehall)
                    u = Unit("grunt", 1, pos[0], pos[1])
                    ph = self.player_hall
                    if ph and not ph.dead:
                        u.order_attack_move(ph.x, ph.y, self)
                    self.units.append(u)
        # 实体
        for u in self.units:
            u.update(dt, self)
        self.units = [u for u in self.units if not u.dead]
        self.selection = [s for s in self.selection if not s.dead]
        for b in self.buildings:
            b.update(dt, self)
        self.buildings = [b for b in self.buildings if not b.dead]
        # 投射物
        for pr in self.projectiles:
            pr.update(dt, self)
        self.projectiles = [p for p in self.projectiles if not p.dead]
        # 粒子/浮字/公告
        for p in self.particles:
            p.update(dt)
        self.particles = [p for p in self.particles if not p.dead]
        for t in self.texts:
            t.t -= dt
            t.y -= 24 * dt
        self.texts = [t for t in self.texts if not t.dead]
        for a in self.announces:
            a[1] -= dt
        self.announces = [a for a in self.announces if a[1] > 0]
        # 分离
        self._separate()
        # 食物上限
        self.food_limit = sum(BUILDING_TYPES[b.type].get("food", 0)
                              for b in self.buildings
                              if b.team == 0 and not b.dead and not b.under_construction)
        self.food_limit = min(60, self.food_limit)
        # 胜负
        if self.ehall.dead:
            self.state = "win"
            sfx("done")
        elif all(b.dead or b.team != 0 or b.type != "hall" for b in self.buildings):
            self.state = "lose"

    def _separate(self):
        us = self.units
        n = len(us)
        if n > 160:
            return
        for i in range(n):
            a = us[i]
            for j in range(i + 1, n):
                b_ = us[j]
                dx, dy = b_.x - a.x, b_.y - a.y
                d2 = dx * dx + dy * dy
                rr = (a.r + b_.r) * 0.85
                if d2 < rr * rr and d2 > 0.0001:
                    d = math.sqrt(d2)
                    push = (rr - d) / 2
                    ux, uy = dx / d, dy / d
                    a._step(-ux * push, -uy * push, self)
                    b_._step(ux * push, uy * push, self)

    def _clamp_cam(self):
        self.cam_x = max(0.0, min(WORLD_W - SCREEN_W, self.cam_x))
        self.cam_y = max(0.0, min(WORLD_H - SCREEN_H, self.cam_y))

    def _camera(self, dt):
        keys = pygame.key.get_pressed()
        spd = 640 * dt
        if keys[pygame.K_w] or keys[pygame.K_UP]:
            self.cam_y -= spd
        if keys[pygame.K_s] or keys[pygame.K_DOWN]:
            self.cam_y += spd
        if keys[pygame.K_a] or keys[pygame.K_LEFT]:
            self.cam_x -= spd
        if keys[pygame.K_d] or keys[pygame.K_RIGHT]:
            self.cam_x += spd
        mx, my = self.mouse_pos
        edge = 14
        espd = 560 * dt
        if mx < edge:
            self.cam_x -= espd
        elif mx > SCREEN_W - edge:
            self.cam_x += espd
        if my < edge:
            self.cam_y -= espd
        elif my > SCREEN_H - edge:
            self.cam_y += espd
        self._clamp_cam()

    # ---- 输入 ----
    def handle_event(self, e):
        if e.type == pygame.MOUSEMOTION:
            self.mouse_pos = e.pos
            if self.drag_minimap:
                self._minimap_jump(e.pos)
            return None
        if e.type == pygame.MOUSEBUTTONDOWN:
            mx, my = e.pos
            if e.button == 1:
                if self._over_minimap(mx, my):
                    self.drag_minimap = True
                    self._minimap_jump((mx, my))
                    return None
                if my > SCREEN_H - UI_BOTTOM or my < UI_TOP:
                    self._click_ui((mx, my))
                    return None
                if self.state != "play":
                    return "restart"
                if self.placing:
                    self._try_place(mx, my)
                    return None
                if self.atk_move:
                    wx, wy = self._world((mx, my))
                    for u in [s for s in self.selection if isinstance(s, Unit) and s.team == 0]:
                        u.order_attack_move(wx, wy, self)
                    sfx("move")
                    self.atk_move = False
                    return None
                self.drag_start = (mx, my)
                return None
            if e.button == 3:
                if self.placing:
                    self.placing = None
                    return None
                if self.atk_move:
                    self.atk_move = False
                    return None
                if my > SCREEN_H - UI_BOTTOM or my < UI_TOP:
                    return None
                if self.state != "play":
                    return None
                wx, wy = self._world((mx, my))
                sel = self.selection
                if len(sel) == 1 and isinstance(sel[0], Building) and sel[0].team == 0:
                    sel[0].rally = (wx, wy)
                    sfx("click")
                    return None
                self.command_right(wx, wy)
                return None
        if e.type == pygame.MOUSEBUTTONUP and e.button == 1:
            if self.drag_minimap:
                self.drag_minimap = False
                return None
            if self.drag_start:
                self._finish_drag(e.pos)
                return None
        if e.type == pygame.KEYDOWN:
            if e.key == pygame.K_ESCAPE:
                if self.placing:
                    self.placing = None
                elif self.atk_move:
                    self.atk_move = False
                else:
                    self.selection = []
            elif e.key in (pygame.K_a,):
                if any(isinstance(s, Unit) and s.team == 0 for s in self.selection):
                    self.atk_move = True
            elif e.key == pygame.K_s:
                for s in self.selection:
                    if isinstance(s, Unit):
                        s.stop()
                sfx("click")
            elif e.key == pygame.K_SPACE:
                ph = self.player_hall
                if ph and not ph.dead:
                    self.cam_x = ph.x - SCREEN_W / 2
                    self.cam_y = ph.y - SCREEN_H / 2
                    self._clamp_cam()
            elif e.key == pygame.K_r and self.state != "play":
                return "restart"
        return None

    def _world(self, pos):
        return (pos[0] + self.cam_x, pos[1] + self.cam_y)

    def _over_minimap(self, mx, my):
        x0 = SCREEN_W - MINIMAP - 10
        y0 = SCREEN_H - MINIMAP - 8
        return x0 <= mx < x0 + MINIMAP and y0 <= my < y0 + MINIMAP

    def _minimap_jump(self, pos):
        x0 = SCREEN_W - MINIMAP - 10
        y0 = SCREEN_H - MINIMAP - 8
        fx = (pos[0] - x0) / MINIMAP
        fy = (pos[1] - y0) / MINIMAP
        self.cam_x = fx * WORLD_W - SCREEN_W / 2
        self.cam_y = fy * WORLD_H - SCREEN_H / 2
        self._clamp_cam()

    def _finish_drag(self, pos):
        x0, y0 = self.drag_start
        self.drag_start = None
        mx, my = pos
        if math.hypot(mx - x0, my - y0) < 7:
            wx, wy = self._world((mx, my))
            self.select_at(wx, wy)
            return
        ax0, ax1 = sorted((x0, mx))
        ay0, ay1 = sorted((y0, my))
        ax0 += self.cam_x
        ax1 += self.cam_x
        ay0 += self.cam_y
        ay1 += self.cam_y
        sel = [u for u in self.units
               if u.team == 0 and ax0 <= u.x <= ax1 and ay0 <= u.y <= ay1]
        if sel:
            self.selection = sel
            sfx("click")
        else:
            self.selection = []

    def select_at(self, wx, wy):
        e = self.entity_at(wx, wy)
        if e is not None and e.team == 0:
            self.selection = [e]
            sfx("click")
        else:
            self.selection = []

    def command_right(self, wx, wy):
        us = [s for s in self.selection if isinstance(s, Unit) and s.team == 0]
        if not us:
            return
        tgt = self.entity_at(wx, wy)
        i = 0
        for u in us:
            if tgt is None:
                ox, oy = SPREAD[i % len(SPREAD)]
                i += 1
                u.set_dest(wx + ox, wy + oy, self)
            elif isinstance(tgt, (Tree, GoldMine)):
                if u.type == "worker":
                    u.order_harvest(tgt, self)
                else:
                    ox, oy = SPREAD[i % len(SPREAD)]
                    i += 1
                    u.set_dest(tgt.x + ox, tgt.y + oy, self)
            elif isinstance(tgt, Building) and tgt.team == 0:
                if tgt.under_construction and u.type == "worker":
                    u.order_build(tgt, self)
                else:
                    ox, oy = SPREAD[i % len(SPREAD)]
                    i += 1
                    u.set_dest(tgt.x + ox, tgt.y + oy, self)
            elif tgt.team != u.team:
                u.order_attack(tgt, self)
            else:
                u.set_dest(wx, wy, self)
        sfx("move")

    # ---- 命令按钮 ----
    def current_commands(self):
        if self.state != "play":
            return []
        sel = self.selection
        if not sel:
            return []
        if len(sel) == 1 and isinstance(sel[0], Building) and sel[0].team == 0 \
                and not sel[0].under_construction:
            return [("train", ut) for ut in BUILDING_TYPES[sel[0].type].get("trains", [])]
        us = [s for s in sel if isinstance(s, Unit) and s.team == 0]
        if not us:
            return []
        if any(u.type == "worker" for u in us):
            return [("build", "farm"), ("build", "barracks"), ("build", "tower"),
                    ("build", "hall"), ("stop", None)]
        return [("stop", None)]

    @staticmethod
    def _cmd_info(cmd):
        kind, key = cmd
        if kind == "train":
            t = UNIT_TYPES[key]
            return t["name"], t["cost_g"], t["cost_w"], t["food"]
        if kind == "build":
            t = BUILDING_TYPES[key]
            return t["name"], t["cost_g"], t["cost_w"], 0
        return "停止", 0, 0, 0

    def _can_afford(self, cg, cw, cf):
        return self.gold >= cg and self.wood >= cw and self.food_used() + cf <= self.food_limit

    def _click_ui(self, pos):
        mx, my = pos
        for rect, cmd in self.cmd_buttons:
            if rect.collidepoint(mx, my):
                self.do_command(cmd)
                return
        if self._over_minimap(mx, my):
            self._minimap_jump(pos)

    def do_command(self, cmd):
        kind, key = cmd
        if kind == "stop":
            for s in self.selection:
                if isinstance(s, Unit):
                    s.stop()
            sfx("click")
            return
        name, cg, cw, cf = self._cmd_info(cmd)
        if not self._can_afford(cg, cw, cf):
            sfx("click")
            return
        if kind == "train":
            if self.selection and isinstance(self.selection[0], Building):
                b = self.selection[0]
                if len(b.queue) < 5:
                    self.gold -= cg
                    self.wood -= cw
                    b.queue.append(key)
                    sfx("click")
        elif kind == "build":
            self.placing = key
            self.selection = []
            sfx("click")

    def _area_free(self, tx, ty, w, h):
        if tx < 2 or ty < 2 or tx + w > MAP_W - 2 or ty + h > MAP_H - 2:
            return False
        for i in range(tx, tx + w):
            for j in range(ty, ty + h):
                if self.blocked[i][j]:
                    return False
        px0, py0 = tx * TILE, ty * TILE
        px1, py1 = px0 + w * TILE, py0 + h * TILE
        for u in self.units:
            if px0 - 6 <= u.x <= px1 + 6 and py0 - 6 <= u.y <= py1 + 6:
                return False
        return True

    def _try_place(self, mx, my):
        t = BUILDING_TYPES[self.placing]
        tw, th = t["w"], t["h"]
        wx, wy = self._world((mx, my))
        ptx = int(wx // TILE - tw / 2)
        pty = int(wy // TILE - th / 2)
        if not self._area_free(ptx, pty, tw, th):
            sfx("click")
            return
        if not self._can_afford(t["cost_g"], t["cost_w"], 0):
            sfx("click")
            return
        self.gold -= t["cost_g"]
        self.wood -= t["cost_w"]
        b = Building(self.placing, 0, ptx, pty, construct=True)
        self.buildings.append(b)
        self.block_rect(ptx, pty, tw, th)
        self.mm_dirty = True
        workers = [s for s in self.selection if isinstance(s, Unit) and s.type == "worker"]
        for w in workers:
            w.order_build(b, self)
        sfx("click")
        self.placing = None

    # ---- 地形绘制缓存 ----
    def _build_terrain(self):
        rng = random.Random(20261018)
        surf = pygame.Surface((WORLD_W, WORLD_H))
        for i in range(MAP_W):
            for j in range(MAP_H):
                base = 44 + rng.randint(-5, 5)
                col = (base * 0.7, base + 18, base * 0.62)
                if i in (0, 1, MAP_W - 1, MAP_W - 2) or j in (0, 1, MAP_H - 1, MAP_H - 2):
                    g = 70 + rng.randint(-8, 8)
                    col = (g, g, g + 6)
                pygame.draw.rect(surf, col, (i * TILE, j * TILE, TILE, TILE))
                if rng.random() < 0.06:
                    pygame.draw.circle(surf, (base * 0.55, base + 26, base * 0.5),
                                       (i * TILE + rng.randint(4, 28), j * TILE + rng.randint(4, 28)), 2)
        self.terrain = surf

    def _rebuild_minimap(self):
        mm = pygame.Surface((MAP_W, MAP_H))
        mm.fill((26, 46, 26))
        for i in range(MAP_W):
            for j in (0, 1, MAP_H - 1, MAP_H - 2):
                mm.set_at((i, j), (90, 90, 96))
        for j in range(MAP_H):
            for i in (0, 1, MAP_W - 1, MAP_W - 2):
                mm.set_at((i, j), (90, 90, 96))
        for t in self.trees:
            if not t.dead:
                mm.set_at((t.tx, t.ty), (52, 110, 52))
        for m in self.mines:
            if not m.dead:
                for i in range(2):
                    for j in range(2):
                        mm.set_at((m.tx + i, m.ty + j), (210, 180, 60))
        for b in self.buildings:
            if b.dead:
                continue
            col = (110, 160, 255) if b.team == 0 else (255, 90, 70)
            for i in range(b.w):
                for j in range(b.h):
                    if 0 <= b.tx + i < MAP_W and 0 <= b.ty + j < MAP_H:
                        mm.set_at((b.tx + i, b.ty + j), col)
        self.mm_base = pygame.transform.scale(mm, (MINIMAP, MINIMAP))
        self.mm_dirty = False

    # ---------------------------------------------------------- 绘制 ----
    def draw(self, scr):
        scr.fill(C_BG)
        cx, cy = int(self.cam_x), int(self.cam_y)
        area = pygame.Rect(max(0, cx), max(0, cy),
                           min(SCREEN_W, WORLD_W), min(SCREEN_H, WORLD_H))
        area.right = min(area.right, WORLD_W)
        area.bottom = min(area.bottom, WORLD_H)
        scr.blit(self.terrain, (0, 0), area)
        # 地形上方实体
        ents = []
        vx0, vy0 = cx - 64, cy - 64
        vx1, vy1 = cx + SCREEN_W + 64, cy + SCREEN_H + 64
        for t in self.trees:
            if not t.dead and vx0 < t.x < vx1 and vy0 < t.y < vy1:
                ents.append((t.y, "tree", t))
        for m in self.mines:
            if not m.dead and vx0 < m.x < vx1 and vy0 < m.y < vy1:
                ents.append((m.y + 20, "mine", m))
        for b in self.buildings:
            if not b.dead and vx0 < b.x < vx1 and vy0 < b.y < vy1:
                ents.append(((b.ty + b.h) * TILE, "bld", b))
        for u in self.units:
            if vx0 < u.x < vx1 and vy0 < u.y < vy1:
                ents.append((u.y + u.r, "unit", u))
        ents.sort(key=lambda e: e[0])
        for _, kind, obj in ents:
            if kind == "tree":
                self._draw_tree(scr, obj, cx, cy)
            elif kind == "mine":
                self._draw_mine(scr, obj, cx, cy)
            elif kind == "bld":
                self._draw_building(scr, obj, cx, cy)
            else:
                self._draw_unit(scr, obj, cx, cy)
        # 投射物
        for p in self.projectiles:
            x, y = p.x - cx, p.y - cy
            ang = math.atan2(p.ty - p.y, p.tx - p.x)
            dx, dy = math.cos(ang) * 6, math.sin(ang) * 6
            pygame.draw.line(scr, (230, 210, 160), (x - dx, y - dy), (x + dx, y + dy), 2)
        # 粒子
        for p in self.particles:
            a = max(0.2, p.life / p.max_life)
            pygame.draw.circle(scr, lerp_color((40, 40, 40), p.color, a),
                               (int(p.x - cx), int(p.y - cy)), max(1, int(p.size * a)))
        # 浮动文字
        for t in self.texts:
            alpha = max(0, min(255, int(t.t * 200)))
            s = font(16).render(t.text, True, t.color)
            s.set_alpha(alpha)
            scr.blit(s, (t.x - cx - s.get_width() / 2, t.y - cy))
        # 集结点
        if len(self.selection) == 1 and isinstance(self.selection[0], Building) \
                and self.selection[0].rally:
            rx, ry = self.selection[0].rally
            pygame.draw.line(scr, C_SEL, (self.selection[0].x - cx, self.selection[0].y - cy),
                             (rx - cx, ry - cy), 1)
            pygame.draw.circle(scr, C_SEL, (int(rx - cx), int(ry - cy)), 5, 2)
        # 框选
        if self.drag_start:
            x0, y0 = self.drag_start
            mx, my = self.mouse_pos
            r = pygame.Rect(min(x0, mx), min(y0, my), abs(mx - x0), abs(my - y0))
            pygame.draw.rect(scr, (140, 240, 140), r, 1)
            s = pygame.Surface(r.size, pygame.SRCALPHA)
            s.fill((140, 240, 140, 40))
            scr.blit(s, r.topleft)
        # 放置虚影
        if self.placing and self.state == "play":
            self._draw_ghost(scr)
        if self.atk_move:
            draw_text(scr, "攻击移动: 左键点击目标区域", 18, SCREEN_W / 2, 44,
                      (255, 220, 120), "center")
        # UI
        self._draw_top(scr)
        self._draw_bottom(scr)
        self._draw_announces(scr)
        if self.state != "play":
            self._draw_end(scr)

    # 实体绘制
    _tree_surfs = None

    def _draw_tree(self, scr, t, cx, cy):
        if Game._tree_surfs is None:
            surfs = []
            for v in range(3):
                s = pygame.Surface((28, 36), pygame.SRCALPHA)
                pygame.draw.rect(s, (96, 66, 40), (12, 26, 4, 8))
                c = [(40, 110, 50), (52, 122, 44), (34, 96, 58)][v]
                cd = lerp_color(c, (0, 0, 0), 0.3)
                pygame.draw.polygon(s, cd, [(14, 0), (25, 16), (3, 16)])
                pygame.draw.polygon(s, c, [(14, 8), (26, 24), (2, 24)])
                surfs.append(s)
            Game._tree_surfs = surfs
        s = Game._tree_surfs[t.variant]
        if t.amount < 40:
            s = pygame.transform.scale(s, (22, 28))
        scr.blit(s, (t.x - cx - s.get_width() / 2, t.y - cy - s.get_height() + 12))

    def _draw_mine(self, scr, m, cx, cy):
        x, y = m.x - cx, m.y - cy
        pygame.draw.polygon(scr, (110, 108, 104),
                            [(x - 30, y + 24), (x - 16, y - 14), (x, y - 26),
                             (x + 16, y - 12), (x + 30, y + 24)])
        pygame.draw.polygon(scr, (84, 82, 80),
                            [(x - 30, y + 24), (x, y - 26), (x + 30, y + 24), (x + 30, y + 26),
                             (x - 30, y + 26)])
        frac = m.amount / 8000
        dots = max(2, int(8 * frac))
        for i in range(dots):
            a = i / dots * math.tau
            pygame.draw.circle(scr, (255, 210, 60),
                               (int(x + math.cos(a) * 14), int(y + math.sin(a) * 8 + 4)), 2)

    def _draw_building(self, scr, b, cx, cy):
        x = b.tx * TILE - cx
        y = b.ty * TILE - cy
        w, h = b.w * TILE, b.h * TILE
        rect = pygame.Rect(x, y, w, h)
        if b.under_construction:
            pygame.draw.rect(scr, (120, 100, 78), rect, border_radius=4)
            pygame.draw.rect(scr, (88, 70, 52), rect, 3, border_radius=4)
            for i in range(1, b.w):
                pygame.draw.line(scr, (150, 122, 84), (x + i * TILE, y), (x + i * TILE, y + h), 2)
            for j in range(1, b.h):
                pygame.draw.line(scr, (150, 122, 84), (x, y + j * TILE), (x + w, y + j * TILE), 2)
            pygame.draw.rect(scr, (30, 30, 30), (x + 4, y + h - 10, w - 8, 6))
            pygame.draw.rect(scr, (250, 190, 60),
                             (x + 4, y + h - 10, int((w - 8) * b.progress / 100), 6))
            draw_text(scr, "%d%%" % int(b.progress), 13, x + w / 2, y + h - 26, C_TEXT, "center")
            return
        selected = b in self.selection
        if selected:
            pygame.draw.rect(scr, C_SEL, rect.inflate(6, 6), 2, border_radius=6)
        body = (150, 132, 108) if b.team == 0 else (128, 96, 88)
        roof = (86, 120, 180) if b.team == 0 else (150, 62, 54)
        if b.type == "tower":
            tw = int(w * 0.44)
            pygame.draw.rect(scr, (120, 118, 112), (x + (w - tw) // 2, y - 14, tw, h + 14))
            pygame.draw.rect(scr, (80, 78, 74), (x + (w - tw) // 2, y - 14, tw, h + 14), 2)
            for k in range(3):
                bx = x + (w - tw) // 2 + k * tw // 2
                pygame.draw.rect(scr, (120, 118, 112), (bx, y - 20, tw // 4, 8))
            pygame.draw.rect(scr, (40, 36, 34), (x + w // 2 - 2, y - 6, 4, 10))
            pygame.draw.circle(scr, (200, 60, 60), (x + w // 2, y - 26), 4)
        else:
            pygame.draw.rect(scr, (44, 40, 34), rect.move(3, 4), border_radius=5)
            pygame.draw.rect(scr, body, rect, border_radius=4)
            pygame.draw.rect(scr, (58, 48, 40), rect, 2, border_radius=4)
            pygame.draw.polygon(scr, roof, [(x - 5, y + h * 0.42), (x + w / 2, y - 9), (x + w + 5, y + h * 0.42)])
            pygame.draw.polygon(scr, lerp_color(roof, (0, 0, 0), 0.35),
                                [(x - 5, y + h * 0.42), (x + w / 2, y - 9), (x + w / 2, y + h * 0.42 + 2)])
            pygame.draw.rect(scr, (66, 48, 34), (x + w / 2 - 7, y + h - 16, 14, 16))
            if b.type == "hall":
                fx, fy = x + 10, y - 9
                pygame.draw.line(scr, (60, 50, 40), (fx, fy), (fx, fy - 14), 2)
                pygame.draw.polygon(scr, (90, 140, 230), [(fx, fy - 14), (fx + 14, fy - 10), (fx, fy - 6)])
                pygame.draw.circle(scr, (230, 200, 120), (x + w - 14, y + 10), 5)
            elif b.type == "barracks":
                pygame.draw.line(scr, (210, 210, 220), (x + w / 2 - 10, y + 8), (x + w / 2 + 10, y + 22), 3)
                pygame.draw.line(scr, (210, 210, 220), (x + w / 2 + 10, y + 8), (x + w / 2 - 10, y + 22), 3)
            elif b.type == "farm":
                for i in range(4):
                    pygame.draw.circle(scr, (220, 200, 90), (x + 10 + i * 12, y + h - 12), 3)
            elif b.type == "ehall":
                for k in range(3):
                    sxp = x + w * (0.25 + 0.25 * k)
                    pygame.draw.polygon(scr, (110, 30, 30), [(sxp - 8, y + 4), (sxp, y - 22), (sxp + 8, y + 4)])
                fx, fy = x + w - 12, y - 8
                pygame.draw.line(scr, (50, 30, 30), (fx, fy), (fx, fy - 18), 2)
                pygame.draw.polygon(scr, (200, 50, 40), [(fx, fy - 18), (fx + 15, fy - 13), (fx, fy - 8)])
        if b.hp < b.max_hp or selected:
            self._hp_bar(scr, x + w / 2, y - 14, 46, b.hp / b.max_hp)
        if b.queue:
            draw_text(scr, "%s %d%%" % (UNIT_TYPES[b.queue[0]]["name"], b.prod_t * 100), 13,
                      x + w / 2, y + h + 4, (255, 230, 140), "center")

    def _draw_unit(self, scr, u, cx, cy):
        x = u.x - cx
        y = u.y - cy
        bob = math.sin(self.time * 11 + u.phase) * 2 if u.moving else 0
        if u.team == 0:
            body_col = (66, 108, 200)
            skin = (232, 194, 152)
        elif u.team == 1:
            body_col = (186, 66, 52)
            skin = (110, 158, 88)
        else:
            body_col = (150, 112, 82)
            skin = (196, 150, 110)
        if u.flash > 0:
            body_col = lerp_color(body_col, (255, 255, 255), 0.7)
        if u in self.selection:
            pygame.draw.ellipse(scr, C_SEL, (x - u.r - 4, y - 4, (u.r + 4) * 2, (u.r + 2) * 2), 2)
        pygame.draw.ellipse(scr, (22, 40, 22), (x - u.r, y - 2, u.r * 2, u.r), 1)
        by = y - 9 - bob
        rr = u.r * 0.8
        pygame.draw.circle(scr, lerp_color(body_col, (0, 0, 0), 0.35), (int(x), int(by)), int(rr) + 1)
        pygame.draw.circle(scr, body_col, (int(x), int(by)), int(rr))
        hxc = math.cos(u.face) * 2
        pygame.draw.circle(scr, skin, (int(x + hxc), int(by - rr - 3)), 5)
        if u.type == "footman" or u.type == "knight":
            pygame.draw.circle(scr, (188, 188, 196), (int(x + hxc), int(by - rr - 4)), 4, 2)
        # 武器
        if u.swing > 0:
            wa = u.face - 1.0 + (1 - u.swing / 0.25) * 1.9
        else:
            wa = u.face + 0.55
        hx = x + math.cos(wa) * (rr + 3)
        hy = by + math.sin(wa) * (rr + 3)
        tipx = x + math.cos(wa) * (rr + 13)
        tipy = by + math.sin(wa) * (rr + 13)
        if u.type == "worker":
            pygame.draw.line(scr, (150, 120, 80), (hx, hy), (tipx, tipy), 2)
            pygame.draw.circle(scr, (160, 160, 170), (int(tipx), int(tipy)), 2)
        elif u.type in ("footman", "knight"):
            pygame.draw.line(scr, (215, 215, 225), (hx, hy), (tipx, tipy), 3 if u.type == "footman" else 4)
            sx2 = x + math.cos(wa + math.pi / 2) * 7
            sy2 = by + math.sin(wa + math.pi / 2) * 7
            pygame.draw.rect(scr, (140, 110, 70), (sx2 - 3, sy2 - 4, 6, 8), border_radius=2)
        elif u.type == "archer":
            bx0 = x + math.cos(u.face) * (rr + 4)
            by0 = by + math.sin(u.face) * (rr + 4)
            ar = pygame.Rect(int(bx0 - 8), int(by0 - 8), 16, 16)
            pygame.draw.arc(scr, (150, 110, 60), ar, u.face - 1.2, u.face + 1.2, 2)
        elif u.type == "grunt":
            pygame.draw.line(scr, (140, 100, 60), (hx, hy), (tipx, tipy), 2)
            midx = (hx + tipx) / 2
            midy = (hy + tipy) / 2
            pygame.draw.polygon(scr, (170, 170, 180), [
                (midx + math.cos(wa + math.pi / 2) * 6, midy + math.sin(wa + math.pi / 2) * 6),
                (tipx, tipy),
                (midx - math.cos(wa + math.pi / 2) * 6, midy - math.sin(wa + math.pi / 2) * 6)])
        elif u.type == "troll":
            pygame.draw.line(scr, (120, 90, 130), (hx, hy), (tipx, tipy), 2)
            pygame.draw.circle(scr, (200, 200, 210), (int(tipx), int(tipy)), 2)
        elif u.type == "ogre":
            pygame.draw.line(scr, (110, 80, 50), (hx, hy), (tipx, tipy), 5)
            pygame.draw.circle(scr, (90, 66, 42), (int(tipx), int(tipy)), 5)
        # 携带资源
        if u.carry > 0:
            col = C_GOLD if u.carry_kind == "gold" else C_WOOD
            pygame.draw.circle(scr, col, (int(x - rr - 3), int(by + 2)), 4)
        if u.hp < u.max_hp or u in self.selection:
            self._hp_bar(scr, x, y - 24, 22, u.hp / u.max_hp)

    @staticmethod
    def _hp_bar(scr, cx, y, w, frac):
        frac = max(0.0, min(1.0, frac))
        r = pygame.Rect(int(cx - w / 2), int(y), w, 4)
        pygame.draw.rect(scr, (20, 20, 20), (r.x - 1, r.y - 1, r.w + 2, r.h + 2))
        col = C_HP if frac > 0.5 else ((240, 200, 70) if frac > 0.25 else C_HPBAD)
        pygame.draw.rect(scr, col, (r.x, r.y, int(r.w * frac), r.h))

    def _draw_ghost(self, scr):
        t = BUILDING_TYPES[self.placing]
        tw, th = t["w"], t["h"]
        wx, wy = self._world(self.mouse_pos)
        ptx = int(wx // TILE - tw / 2)
        pty = int(wy // TILE - th / 2)
        ok = self._area_free(ptx, pty, tw, th) and self._can_afford(t["cost_g"], t["cost_w"], 0)
        col = (120, 240, 140) if ok else (240, 90, 90)
        x = ptx * TILE - self.cam_x
        y = pty * TILE - self.cam_y
        s = pygame.Surface((tw * TILE, th * TILE), pygame.SRCALPHA)
        s.fill((col[0], col[1], col[2], 80))
        scr.blit(s, (x, y))
        pygame.draw.rect(scr, col, (x, y, tw * TILE, th * TILE), 2)
        draw_text(scr, "%s (%d金%d木)" % (t["name"], t["cost_g"], t["cost_w"]), 14,
                  x + tw * TILE / 2, y - 22, col, "center")

    # UI
    def _draw_top(self, scr):
        bar = pygame.Surface((SCREEN_W, UI_TOP), pygame.SRCALPHA)
        bar.fill((18, 18, 26, 220))
        scr.blit(bar, (0, 0))
        pygame.draw.line(scr, C_BORDER, (0, UI_TOP), (SCREEN_W, UI_TOP))
        draw_text(scr, "黄金 %d" % self.gold, 17, 12, 5, C_GOLD)
        draw_text(scr, "木材 %d" % self.wood, 17, 130, 5, C_WOOD)
        draw_text(scr, "食物 %d/%d" % (self.food_used(), self.food_limit), 17, 250, 5, C_FOOD)
        draw_text(scr, "第 %d 波" % (self.wave_n + 1), 17, 380, 5, (230, 140, 120))
        draw_text(scr, "下一波 %ds" % max(0, int(self.wave_timer)), 17, 460, 5, (230, 160, 140))
        m, s = divmod(int(self.time), 60)
        draw_text(scr, "时间 %02d:%02d" % (m, s), 17, 590, 5, (180, 180, 200))
        draw_text(scr, "兽人单位 %d" % sum(1 for u in self.units if u.team == 1), 17, 700, 5, (220, 120, 110))

    def _draw_bottom(self, scr):
        py = SCREEN_H - UI_BOTTOM
        pygame.draw.rect(scr, C_PANEL, (0, py, SCREEN_W, UI_BOTTOM))
        pygame.draw.line(scr, C_BORDER, (0, py), (SCREEN_W, py), 2)
        # 左侧信息
        info = pygame.Rect(8, py + 8, 248, UI_BOTTOM - 16)
        pygame.draw.rect(scr, C_PANEL_HI, info, border_radius=6)
        sel = self.selection
        if len(sel) == 1:
            e = sel[0]
            col = (110, 160, 255) if e.team == 0 else (255, 90, 70)
            pygame.draw.circle(scr, col, (info.x + 26, info.y + 26), 16)
            draw_text(scr, e.name[0], 18, info.x + 26, info.y + 15, (255, 255, 255), "center")
            draw_text(scr, e.name, 17, info.x + 52, info.y + 4)
            self._hp_bar(scr, info.x + 52 + 60, info.y + 26, 110, e.hp / e.max_hp)
            draw_text(scr, "%d/%d" % (max(0, int(e.hp)), e.max_hp), 13, info.x + 52, info.y + 34, (200, 200, 210))
            if isinstance(e, Unit):
                draw_text(scr, "攻击 %d  射程 %d" % (e.dmg, e.range), 14, info.x + 10, info.y + 58, (190, 190, 200))
                stt = {"idle": "待命", "move": "移动", "attack_move": "攻击移动", "attack": "攻击",
                       "to_res": "前往资源", "gather": "采集中", "to_base": "返回中",
                       "to_build": "前往工地", "building": "建造中"}.get(e.state, e.state)
                draw_text(scr, "状态: " + stt, 14, info.x + 10, info.y + 78, (190, 190, 200))
                if e.carry:
                    draw_text(scr, "携带 %d %s" % (e.carry, "黄金" if e.carry_kind == "gold" else "木材"),
                              14, info.x + 10, info.y + 96, C_GOLD if e.carry_kind == "gold" else C_WOOD)
            elif isinstance(e, Building):
                if e.under_construction:
                    draw_text(scr, "建造中 %d%%" % int(e.progress), 14, info.x + 10, info.y + 58, (250, 200, 90))
                elif e.queue:
                    names = ",".join(UNIT_TYPES[q]["name"] for q in e.queue)
                    draw_text(scr, "生产: %s" % names, 14, info.x + 10, info.y + 58, (250, 200, 90))
                    pygame.draw.rect(scr, (30, 30, 30), (info.x + 10, info.y + 80, 120, 8))
                    pygame.draw.rect(scr, (90, 200, 120),
                                     (info.x + 10, info.y + 80,
                                      int(120 * e.prod_t / max(1, UNIT_TYPES[e.queue[0]]["bt"])), 8))
                elif e.type == "tower":
                    draw_text(scr, "攻击 %d  射程 %d" % (e.dmg, e.range), 14, info.x + 10, info.y + 58, (190, 190, 200))
                else:
                    draw_text(scr, "右键地面设置集结点", 13, info.x + 10, info.y + 58, (160, 170, 180))
        elif len(sel) > 1:
            draw_text(scr, "已选择 %d 个单位" % len(sel), 16, info.x + 10, info.y + 6)
            counts = {}
            for u in sel:
                counts[u.name] = counts.get(u.name, 0) + 1
            yy = info.y + 32
            for k, v in list(counts.items())[:4]:
                draw_text(scr, "%s x%d" % (k, v), 14, info.x + 14, yy, (200, 205, 215))
                yy += 20
        else:
            draw_text(scr, "无选择", 15, info.centerx, info.centery - 10, (150, 155, 165), "center")
            draw_text(scr, "左键选择单位 / 框选军队", 13, info.centerx, info.centery + 12, (120, 126, 138), "center")
        # 命令按钮
        self.cmd_buttons = []
        cmds = self.current_commands()
        bw, bh, gap = 116, 44, 8
        bx0, by0 = 268, py + 10
        for idx, cmd in enumerate(cmds):
            col, row = idx % 4, idx // 4
            r = pygame.Rect(bx0 + col * (bw + gap), by0 + row * (bh + gap), bw, bh)
            name, cg, cw, cf = self._cmd_info(cmd)
            afford = self._can_afford(cg, cw, cf)
            hover = r.collidepoint(self.mouse_pos)
            bg = C_PANEL_HI if hover else (44, 44, 58)
            pygame.draw.rect(scr, bg, r, border_radius=6)
            pygame.draw.rect(scr, C_BORDER if afford else (110, 70, 70), r, 1, border_radius=6)
            tc = C_TEXT if afford else (150, 110, 110)
            draw_text(scr, name, 15, r.centerx, r.y + 5, tc, "center")
            cost = []
            if cg:
                cost.append("%d金" % cg)
            if cw:
                cost.append("%d木" % cw)
            if cf:
                cost.append("%d食" % cf)
            draw_text(scr, " ".join(cost) if cost else "-", 12, r.centerx, r.y + 25,
                      C_GOLD if afford and cost else (160, 120, 90), "center")
            self.cmd_buttons.append((r, cmd))
        # 小地图
        if self.mm_dirty or self.mm_base is None:
            self._rebuild_minimap()
        mx0 = SCREEN_W - MINIMAP - 10
        my0 = SCREEN_H - MINIMAP - 8
        pygame.draw.rect(scr, (10, 10, 14), (mx0 - 3, my0 - 3, MINIMAP + 6, MINIMAP + 6), border_radius=4)
        scr.blit(self.mm_base, (mx0, my0))
        for u in self.units:
            px = mx0 + int(u.x / WORLD_W * MINIMAP)
            py2 = my0 + int(u.y / WORLD_H * MINIMAP)
            col = (120, 190, 255) if u.team == 0 else (255, 90, 70) if u.team == 1 else (230, 170, 90)
            pygame.draw.rect(scr, col, (px - 1, py2 - 1, 3, 3))
        cam_r = pygame.Rect(
            mx0 + int(self.cam_x / WORLD_W * MINIMAP),
            my0 + int(self.cam_y / WORLD_H * MINIMAP),
            max(4, int(SCREEN_W / WORLD_W * MINIMAP)),
            max(4, int(SCREEN_H / WORLD_H * MINIMAP)))
        pygame.draw.rect(scr, (255, 255, 255), cam_r, 1)
        # 提示
        draw_text(scr, "A+左键攻击移动  S停止  空格回主城", 13, 268, py + UI_BOTTOM - 18, (140, 146, 158))

    def _draw_announces(self, scr):
        y = 60
        for text, t in self.announces:
            alpha = max(0, min(255, int(min(t, 1.0) * 255)))
            s = font(24).render(text, True, (255, 230, 150))
            s.set_alpha(alpha)
            sh = font(24).render(text, True, (0, 0, 0))
            sh.set_alpha(alpha)
            r = s.get_rect(center=(SCREEN_W // 2, y))
            scr.blit(sh, (r.x + 2, r.y + 2))
            scr.blit(s, r)
            y += 34

    def _draw_end(self, scr):
        s = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        s.fill((0, 0, 0, 150))
        scr.blit(s, (0, 0))
        if self.state == "win":
            draw_text(scr, "胜  利 ！", 64, SCREEN_W / 2, SCREEN_H / 2 - 60, (255, 220, 90), "center")
            draw_text(scr, "兽人的大厅已化为废墟，深渊大陆重归平静。", 22, SCREEN_W / 2, SCREEN_H / 2 + 10, C_TEXT, "center")
        else:
            draw_text(scr, "失  败 …", 64, SCREEN_W / 2, SCREEN_H / 2 - 60, (230, 80, 70), "center")
            draw_text(scr, "你的主城被摧毁了。再次集结，卷土重来！", 22, SCREEN_W / 2, SCREEN_H / 2 + 10, C_TEXT, "center")
        draw_text(scr, "点击鼠标或按 R 重新开始", 18, SCREEN_W / 2, SCREEN_H / 2 + 60, (200, 200, 210), "center")


# ------------------------------------------------------------ 主程序 ----
def _selftest_script(g, f):
    workers = [u for u in g.units if u.team == 0 and u.type == "worker"]
    if f == 30 and workers:
        w = workers[0]
        g.select_at(w.x, w.y)
        g.command_right(w.x + 120, w.y + 40)
    if f == 70 and len(workers) > 1:
        w = workers[1]
        g.select_at(w.x, w.y)
        tree = g.trees[0]
        g.command_right(tree.x, tree.y)
    if f == 120:
        g.select_at(g.player_hall.x, g.player_hall.y)
        g.do_command(("train", "worker"))
    if f == 170 and workers:
        g.selection = [workers[0]]
        g.placing = "farm"
        g._try_place(int(g.player_hall.x + 160 - g.cam_x), int(g.player_hall.y - g.cam_y))
    if f == 240:
        foot = [u for u in g.units if u.team == 0 and u.type == "footman"]
        if foot:
            g.selection = foot
            g.command_right(g.ehall.x, g.ehall.y)
    if f == 300:
        g.wave_timer = 0.4
    if f == 340:
        g.selection = [u for u in g.units if u.team == 0 and u.type == "footman"][:2]
        if g.selection:
            g.atk_move = True


def main(selftest=False):
    os.environ.setdefault("SDL_VIDEO_CENTERED", "1")
    if selftest:
        os.environ["SDL_VIDEODRIVER"] = "dummy"
        os.environ["SDL_AUDIODRIVER"] = "dummy"
    pygame.mixer.pre_init(22050, -16, 2, 512)
    pygame.init()
    init_sounds()
    pygame.display.set_caption("深渊争霸 - 类魔兽即时战略")
    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
    clock = pygame.time.Clock()
    game = Game()
    frame = 0
    running = True
    while running:
        dt = min(clock.tick(FPS) / 1000.0, 0.05)
        restart = False
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                running = False
                continue
            if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1 and game.state != "play":
                if not (e.pos[1] > SCREEN_H - UI_BOTTOM and game.cmd_buttons):
                    restart = True
                    continue
            r = game.handle_event(e)
            if r == "restart":
                restart = True
        if restart:
            game = Game()
        if selftest:
            _selftest_script(game, frame)
            if frame >= 700:
                running = False
        game.update(dt)
        if not selftest:
            game._camera(dt)
        game.draw(screen)
        pygame.display.flip()
        frame += 1
    if selftest:
        print("SELFTEST OK | units=%d buildings=%d gold=%d wood=%d wave=%d time=%.1f" %
              (len(game.units), len(game.buildings), game.gold, game.wood, game.wave_n, game.time))
    pygame.quit()


if __name__ == "__main__":
    main(selftest="--selftest" in sys.argv)
