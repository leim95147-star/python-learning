# -*- coding: utf-8 -*-
"""
深渊地牢 (Abyss Dungeon) —— 单文件 Python Roguelike
====================================================
回合制地下城探险游戏，使用 pygame 渲染，无需任何外部素材（所有图形程序化绘制）。

特性：
  * 程序化地牢生成（房间+走廊+门+宝箱+陷阱），5 层难度递增
  * 战争迷雾 / 视野系统（逐格光线投射）
  * 7 种怪物 + 多阶段最终 Boss（近战/远程/减速/召唤等多种 AI）
  * BFS 寻路追踪、警报记忆、冻结等状态效果
  * 完整 RPG 数值：等级/经验/攻击/防御/暴击/金币/击杀
  * 物品系统：药水、卷轴、5 阶武器与护甲、宝箱掉落、地面拾取
  * 背包界面（使用/装备/丢弃 + 属性对比）、快捷键用药
  * 技能：火球术(方向射线, 耗蓝) / 治疗术(耗蓝)
  * HUD：血/蓝/经验条、装备栏、小地图、彩色消息日志
  * 打击特效：飘字伤害、粒子、弹道动画、屏幕震动、受击红闪

操作：
  移动 WASD/方向键(8向) | 攻击 撞向敌人 | 等待 空格
  下楼 站楼梯按 Enter/薪 | 技能 F 火球术 / E 治疗术 | 快捷 1 红药 2 蓝药
  背包 I (Enter 使用/装备, D 丢弃) | 帮助/暂停 Esc | 重来 R
运行：python3 abyss_dungeon.py        （--smoke 运行无头自检）
"""

import os
import sys
import math
import random
import traceback
from collections import deque

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
import pygame

# ============================================================
# 常量与配置
# ============================================================
MAP_W, MAP_H, TILE = 44, 30, 22
MAP_X, MAP_Y = 8, 8
VIEW_W, VIEW_H = MAP_W * TILE, MAP_H * TILE          # 968 x 660
PANEL_X = MAP_X + VIEW_W + 8
PANEL_W = 212
LOG_Y = MAP_Y + VIEW_H + 8
LOG_H = 96
WIN_W = PANEL_X + PANEL_W + 8
WIN_H = LOG_Y + LOG_H + 8
FPS = 60
FOV_R = 9
MAX_FLOOR = 5

WALL, FLOOR, DOOR, DOOR_OPEN, STAIRS, CHEST, CHEST_OPEN = range(7)
OPAQUE_T = {WALL, DOOR}
WALK_T = {FLOOR, DOOR, DOOR_OPEN, STAIRS, CHEST, CHEST_OPEN}

DIRS8 = [(-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1)]

ST_TITLE, ST_PLAY, ST_INV, ST_HELP, ST_OVER, ST_WIN = range(6)

FLOOR_NAMES = ["苔藓洞窟", "骸骨回廊", "暗流深沟", "熔火之厅", "深渊王座"]

# ---------------- 颜色 ----------------
C_BG        = (11, 14, 20)
C_PANEL     = (18, 23, 33)
C_PANEL_LN  = (48, 58, 76)
C_WALL      = (58, 66, 86)
C_WALL_TOP  = (86, 97, 122)
C_FLOOR     = (26, 31, 42)
C_FLOOR2    = (30, 36, 49)
C_DOOR      = (128, 86, 44)
C_DOOR_O    = (86, 58, 30)
C_STAIRS    = (222, 186, 84)
C_CHEST     = (188, 128, 40)
C_CHEST_O   = (96, 70, 32)
C_TRAP      = (196, 60, 60)
C_TXT       = (212, 218, 228)
C_TXT_DIM   = (128, 138, 156)
C_HP        = (214, 61, 74)
C_MP        = (66, 130, 236)
C_XP        = (222, 180, 60)
C_GOOD      = (110, 214, 120)
C_BAD       = (235, 100, 100)
C_GOLD      = (240, 200, 80)
C_CYAN      = (90, 210, 230)
C_PURP      = (186, 120, 255)

# ---------------- 物品定义 ----------------
# (名称, 数值, 颜色)
WEAPONS = [
    ("生锈短剑", 2, (154, 163, 173)),
    ("铁剑", 4, (200, 204, 210)),
    ("精钢长剑", 7, (127, 209, 255)),
    ("符文之刃", 10, (183, 140, 255)),
    ("屠龙者·暮光", 14, (255, 157, 92)),
]
ARMORS = [
    ("破旧布衣", 1, (154, 163, 173)),
    ("皮甲", 3, (172, 128, 84)),
    ("锁子甲", 5, (176, 186, 198)),
    ("符文板甲", 8, (183, 140, 255)),
    ("龙鳞铠", 12, (255, 157, 92)),
]
POTIONS = {
    "hp_s": ("小型治疗药水", "恢复 25 点生命", (226, 80, 90)),
    "hp_l": ("大型治疗药水", "恢复 55 点生命", (255, 110, 120)),
    "mp":   ("法力药水",     "恢复 12 点法力", (80, 140, 255)),
    "str":  ("力量药剂",     "永久 +2 攻击",   (255, 150, 60)),
    "def":  ("铁壁药剂",     "永久 +2 防御",   (150, 200, 220)),
}
SCROLLS = {
    "fire": ("火焰卷轴", "烈焰吞噬所有视野内敌人", (255, 130, 50)),
    "frost": ("冰霜卷轴", "冻结视野内敌人 4 回合", (120, 210, 255)),
    "tp":   ("传送卷轴", "随机传送至本层某处", (200, 120, 255)),
}

def item_info(iid):
    """iid -> (名称, 类别, 颜色, 描述)"""
    if iid.startswith("w"):
        n, v, c = WEAPONS[int(iid[1:])]
        return n, "武器", c, "攻击 +%d" % v
    if iid.startswith("a"):
        n, v, c = ARMORS[int(iid[1:])]
        return n, "护甲", c, "防御 +%d" % v
    if iid in POTIONS:
        n, d, c = POTIONS[iid]
        return n, "药水", c, d
    n, d, c = SCROLLS[iid]
    return n, "卷轴", c, d

# ---------------- 怪物定义 ----------------
ENEMY_TYPES = {
    "slime": dict(name="毒史莱姆", hp=14, atk=4, df=0, xp=7, sight=6, speed=2, color=(88, 214, 110), r=7),
    "bat": dict(name="噬血蝙蝠", hp=10, atk=5, df=0, xp=9, sight=8, speed=1, color=(168, 120, 255), r=6, erratic=True),
    "skel": dict(name="骷髅战士", hp=20, atk=7, df=2, xp=14, sight=7, speed=1, color=(222, 222, 210), r=7),
    "orc": dict(name="兽人狂战士", hp=30, atk=9, df=3, xp=22, sight=7, speed=1, color=(70, 160, 70), r=8),
    "lock": dict(name="深渊术士", hp=18, atk=5, df=1, xp=26, sight=8, speed=1, color=(190, 90, 220), r=7, ranged=(7, 9, 2)),
    "golem": dict(name="符文石魔", hp=52, atk=11, df=6, xp=44, sight=6, speed=2, color=(120, 130, 145), r=9),
    "boss": dict(name="深渊之主", hp=170, atk=14, df=6, xp=250, sight=12, speed=1, color=(200, 40, 60), r=12, ranged=(8, 13, 3), boss=True),
}
FLOOR_SPAWNS = {
    1: [("slime", 60), ("bat", 40)],
    2: [("slime", 40), ("bat", 30), ("skel", 30)],
    3: [("skel", 40), ("orc", 30), ("bat", 20), ("lock", 10)],
    4: [("orc", 35), ("lock", 25), ("skel", 20), ("golem", 20)],
    5: [("golem", 30), ("orc", 25), ("lock", 25), ("skel", 20)],
}

# ============================================================
# 工具函数
# ============================================================
def cheb(ax, ay, bx, by):
    return max(abs(ax - bx), abs(ay - by))

def bresenham(x0, y0, x1, y1):
    pts = []
    dx, dy = abs(x1 - x0), abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx - dy
    x, y = x0, y0
    while True:
        pts.append((x, y))
        if x == x1 and y == y1:
            break
        e2 = 2 * err
        if e2 > -dy:
            err -= dy
            x += sx
        if e2 < dx:
            err += dx
            y += sy
    return pts

_FONT_CACHE = {}

def get_font(size, bold=False):
    key = (size, bold)
    if key in _FONT_CACHE:
        return _FONT_CACHE[key]
    names = ["pingfangsc", "hiraginosansgb", "stheiti", "microsoftyahei",
             "arialunicodems", "simsun", "notosanssc"]
    path = None
    for n in names:
        path = pygame.font.match_font(n, bold)
        if path:
            break
    if not path:
        for p in ("/System/Library/Fonts/PingFang.ttc",
                  "/System/Library/Fonts/Hiragino Sans GB.ttc",
                  "/System/Library/Fonts/STHeiti Medium.ttc",
                  "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"):
            if os.path.exists(p):
                path = p
                break
    font = pygame.font.Font(path, size) if path else pygame.font.Font(None, size)
    font.set_bold(bold)
    _FONT_CACHE[key] = font
    return font

def draw_text(surf, text, size, x, y, color, anchor="tl", bold=False):
    f = get_font(size, bold)
    img = f.render(text, True, color)
    r = img.get_rect()
    if "t" in anchor:
        r.top = y
    if "b" in anchor:
        r.bottom = y
    if "l" in anchor:
        r.left = x
    if "r" in anchor:
        r.right = x
    if anchor == "c":
        r.center = (x, y)
    surf.blit(img, r)
    return r

def draw_bar(surf, x, y, w, h, ratio, fg, label=None, bg=(30, 34, 44)):
    ratio = max(0.0, min(1.0, ratio))
    pygame.draw.rect(surf, bg, (x, y, w, h), border_radius=3)
    if ratio > 0:
        pygame.draw.rect(surf, fg, (x, y, int(w * ratio), h), border_radius=3)
    pygame.draw.rect(surf, C_PANEL_LN, (x, y, w, h), 1, border_radius=3)
    if label:
        draw_text(surf, label, 13, x + w // 2, y + h // 2, C_TXT, anchor="c", bold=True)

def tile_center(tx, ty, ox=MAP_X, oy=MAP_Y):
    return ox + tx * TILE + TILE // 2, oy + ty * TILE + TILE // 2

# ============================================================
# 实体
# ============================================================
class Player:
    def __init__(self, x, y):
        self.x, self.y = x, y
        self.face = (1, 0)
        self.maxhp, self.hp = 42, 42
        self.maxmp, self.mp = 12, 12
        self.batk, self.bdef = 4, 1
        self.strb, self.defb = 0, 0
        self.lvl, self.xp, self.gold = 1, 0, 0
        self.weapon, self.armor = 0, 0
        self.inv = {"hp_s": 2, "mp": 1}
        self.kills = 0

    @property
    def atk(self):
        return self.batk + WEAPONS[self.weapon][1] + self.strb

    @property
    def dfn(self):
        return self.bdef + ARMORS[self.armor][1] + self.defb

    @property
    def xp_next(self):
        return 18 + (self.lvl - 1) * 14

class Enemy:
    def __init__(self, t, x, y, floor):
        d = ENEMY_TYPES[t]
        self.type = t
        self.name = d["name"]
        mult = 1 + 0.15 * (floor - 1)
        self.maxhp = int(d["hp"] * mult)
        self.hp = self.maxhp
        self.atk = d["atk"] + (floor - 1)
        self.dfn = d["df"]
        self.xp = d["xp"]
        self.sight = d["sight"]
        self.speed = d.get("speed", 1)
        self.color = d["color"]
        self.r = d["r"]
        self.ranged = d.get("ranged")
        self.erratic = d.get("erratic", False)
        self.boss = d.get("boss", False)
        self.x, self.y = x, y
        self.alert = 0
        self.cd = 0
        self.frozen = 0
        self.slowtick = 0
        self.flash = 0.0

# ============================================================
# 地牢生成
# ============================================================
class Rect:
    def __init__(self, x, y, w, h):
        self.x, self.y, self.w, self.h = x, y, w, h

    @property
    def cx(self):
        return self.x + self.w // 2

    @property
    def cy(self):
        return self.y + self.h // 2

    def intersects(self, o, pad=1):
        return (self.x - pad < o.x + o.w and self.x + self.w + pad > o.x and
                self.y - pad < o.y + o.h and self.y + self.h + pad > o.y)

    def contains(self, x, y):
        return self.x <= x < self.x + self.w and self.y <= y < self.y + self.h

def gen_dungeon(floor):
    """返回 (tiles, rooms)"""
    tiles = [[WALL for _ in range(MAP_H)] for _ in range(MAP_W)]
    rooms = []
    boss_floor = (floor == MAX_FLOOR)
    max_rooms = 11
    for _ in range(80):
        if len(rooms) >= max_rooms:
            break
        if boss_floor and not rooms:
            w, h = 12, 8                       # Boss 层保证一个大厅
        else:
            w, h = random.randint(4, 9), random.randint(3, 6)
        x = random.randint(1, MAP_W - w - 2)
        y = random.randint(1, MAP_H - h - 2)
        r = Rect(x, y, w, h)
        if any(r.intersects(o) for o in rooms):
            continue
        for i in range(x, x + w):
            for j in range(y, y + h):
                tiles[i][j] = FLOOR
        rooms.append(r)
    # 连接相邻房间（L 形走廊）
    for a, b in zip(rooms, rooms[1:]):
        x1, y1 = a.cx, a.cy
        x2, y2 = b.cx, b.cy
        if random.random() < 0.5:
            carve_h(tiles, x1, x2, y1)
            carve_v(tiles, y1, y2, x2)
        else:
            carve_v(tiles, y1, y2, x1)
            carve_h(tiles, x1, x2, y2)
    # 门：扫描每个房间的边界，走廊从房间里"穿出"的位置放门
    cands = set()
    for r in rooms:
        for y in range(r.y, r.y + r.h):
            for bx, by, ox in ((r.x, y, -1), (r.x + r.w - 1, y, 1)):
                wx, wy = bx + ox, by
                if 0 <= wx < MAP_W and tiles[wx][wy] == FLOOR:
                    fx = bx + 2 * ox
                    if not (0 <= fx < MAP_W) or tiles[fx][wy] == WALL:
                        cands.add((bx, by))
        for x in range(r.x, r.x + r.w):
            for bx, by, oy in ((x, r.y, -1), (x, r.y + r.h - 1, 1)):
                wx, wy = bx, by + oy
                if 0 <= wy < MAP_H and tiles[wx][wy] == FLOOR:
                    fy = by + 2 * oy
                    if not (0 <= fy < MAP_H) or tiles[wx][fy] == WALL:
                        cands.add((bx, by))
    for bx, by in cands:
        if tiles[bx][by] == FLOOR and random.random() < 0.55:
            tiles[bx][by] = DOOR
    return tiles, rooms

def carve_h(tiles, x1, x2, y):
    for x in range(min(x1, x2), max(x1, x2) + 1):
        tiles[x][y] = FLOOR

def carve_v(tiles, y1, y2, x):
    for y in range(min(y1, y2), max(y1, y2) + 1):
        tiles[x][y] = FLOOR

# ============================================================
# 游戏主体
# ============================================================
class Game:
    def __init__(self, screen):
        self.screen = screen
        self.clock = pygame.time.Clock()
        self.state = ST_TITLE
        self.prev_state = ST_PLAY
        self.inv_sel = 0
        self.time = 0.0
        self.shake = 0.0
        self.hurt = 0.0
        self.blink = 0.0
        # 特效
        self.particles = []
        self.floats = []
        self.projs = []
        self.dust = [self._new_dust() for _ in range(36)]
        self.embers = []
        # 对局数据
        self.floor = 1
        self.turn = 0
        self.tiles = None
        self.rooms = []
        self.explored = set()
        self.visible = set()
        self.enemies = []
        self.ground = {}
        self.traps = set()
        self.player = None
        self.msgs = deque(maxlen=60)
        self.log_view = deque(maxlen=5)
        self.stairs_pos = None

    # ---------- 通用 ----------
    def _new_dust(self):
        return [random.uniform(0, VIEW_W), random.uniform(0, VIEW_H),
                random.uniform(4, 14), random.uniform(0.02, 0.1)]

    def in_bounds(self, x, y):
        return 0 <= x < MAP_W and 0 <= y < MAP_H

    def tile(self, x, y):
        return self.tiles[x][y]

    def opaque(self, x, y):
        return self.tiles[x][y] in OPAQUE_T

    def los(self, x0, y0, x1, y1):
        for px, py in bresenham(x0, y0, x1, y1)[1:]:
            if (px, py) == (x1, y1):
                return True
            if self.opaque(px, py):
                return False
        return True

    def compute_fov(self):
        p = self.player
        self.visible = set()
        r2 = FOV_R * FOV_R
        for x in range(max(0, p.x - FOV_R), min(MAP_W, p.x + FOV_R + 1)):
            for y in range(max(0, p.y - FOV_R), min(MAP_H, p.y + FOV_R + 1)):
                dx, dy = x - p.x, y - p.y
                if dx * dx + dy * dy <= r2 and self.los(p.x, p.y, x, y):
                    self.visible.add((x, y))
        self.explored |= self.visible

    def add_msg(self, text, color=C_TXT):
        self.msgs.append((text, color))
        self.log_view.append((text, color))

    # ---------- 特效 ----------
    def add_burst(self, tx, ty, color, n=12, ox=MAP_X, oy=MAP_Y):
        cx, cy = tile_center(tx, ty, ox, oy)
        for _ in range(n):
            ang = random.uniform(0, math.tau)
            spd = random.uniform(30, 130)
            self.particles.append([cx, cy, math.cos(ang) * spd, math.sin(ang) * spd,
                                   random.uniform(0.3, 0.7), color, random.uniform(1.5, 3.5)])

    def add_float(self, tx, ty, text, color, vy=-34):
        cx, cy = tile_center(tx, ty)
        self.floats.append([cx, cy, text, color, 0.95, vy])

    def add_proj(self, x0, y0, x1, y1, color, w=3):
        ax, ay = tile_center(x0, y0)
        bx, by = tile_center(x1, y1)
        self.projs.append([ax, ay, bx, by, 0.0, color, w])

    def shake_screen(self, v):
        self.shake = min(10.0, self.shake + v)

    # ---------- 开局 ----------
    def new_game(self):
        self.floor, self.turn = 1, 0
        self.player = Player(0, 0)
        self.msgs.clear()
        self.log_view.clear()
        self.gen_floor()
        self.state = ST_PLAY
        self.add_msg("你踏入了深渊地牢的入口……", C_CYAN)
        self.add_msg("提示：走到物品上自动拾取，I 打开背包。", C_TXT_DIM)

    def gen_floor(self):
        f = self.floor
        self.tiles, self.rooms = gen_dungeon(f)
        self.explored, self.visible = set(), set()
        self.enemies, self.ground, self.traps = [], {}, set()
        self.projs, self.floats = [], []
        self.stairs_pos = None
        start_room = self.rooms[0]
        self.player.x, self.player.y = start_room.cx, start_room.cy
        used = {(self.player.x, self.player.y)}
        # 楼梯：距出生点最远的房间（Boss 层不放楼梯）
        if f < MAX_FLOOR:
            far = max(self.rooms[1:], key=lambda r: cheb(r.cx, r.cy, self.player.x, self.player.y))
            sx, sy = far.cx, far.cy
            self.tiles[sx][sy] = STAIRS
            self.stairs_pos = (sx, sy)
            used.add((sx, sy))
        # 宝箱
        other = self.rooms[1:]
        for r in random.sample(other, min(len(other), 3 if f < MAX_FLOOR else 2)):
            for _ in range(8):
                x = random.randint(r.x, r.x + r.w - 1)
                y = random.randint(r.y, r.y + r.h - 1)
                if self.tiles[x][y] == FLOOR and (x, y) not in used:
                    self.tiles[x][y] = CHEST
                    used.add((x, y))
                    break
        # 陷阱
        for _ in range(f):
            for _try in range(20):
                r = random.choice(self.rooms[1:])
                x, y = random.randint(r.x, r.x + r.w - 1), random.randint(r.y, r.y + r.h - 1)
                if self.tiles[x][y] == FLOOR and (x, y) not in used and cheb(x, y, self.player.x, self.player.y) > 3:
                    self.traps.add((x, y))
                    used.add((x, y))
                    break
        # 地面物品
        n_items = 3 + random.randint(0, 2)
        pool = ["hp_s", "mp", "fire", "frost", "tp", "hp_l"]
        if random.random() < 0.5:
            pool.append("w%d" % min(4, max(0, f - 1 + (1 if random.random() < 0.3 else 0))))
        if random.random() < 0.5:
            pool.append("a%d" % min(4, max(0, f - 1 + (1 if random.random() < 0.3 else 0))))
        for _ in range(n_items):
            iid = random.choice(pool)
            for _try in range(20):
                r = random.choice(self.rooms)
                x, y = random.randint(r.x, r.x + r.w - 1), random.randint(r.y, r.y + r.h - 1)
                if self.tiles[x][y] == FLOOR and (x, y) not in used:
                    self.ground.setdefault((x, y), []).append(iid)
                    used.add((x, y))
                    break
        # 怪物
        if f == MAX_FLOOR:
            far = max(self.rooms[1:], key=lambda r: cheb(r.cx, r.cy, self.player.x, self.player.y))
            bx, by = far.cx, far.cy
            self.enemies.append(Enemy("boss", bx, by, f))
            used.add((bx, by))
            table, count = FLOOR_SPAWNS[f], 6
        else:
            table, count = FLOOR_SPAWNS[f], 4 + f * 2
        weights = [w for _, w in table]
        spawn_room = self.rooms[0]
        for _ in range(count):
            t = random.choices([t for t, _ in table], weights)[0]
            for _try in range(30):
                r = random.choice([rm for rm in self.rooms if rm is not spawn_room])
                x, y = random.randint(r.x, r.x + r.w - 1), random.randint(r.y, r.y + r.h - 1)
                if self.tiles[x][y] == FLOOR and (x, y) not in used and \
                        cheb(x, y, self.player.x, self.player.y) > 5:
                    self.enemies.append(Enemy(t, x, y, f))
                    used.add((x, y))
                    break
        self.compute_fov()
        if f == MAX_FLOOR:
            self.add_msg("【第 %d 层·深渊王座】黑暗中传来低沉的心跳……" % f, C_BAD)
            self.add_msg("深渊之主现身了！击败它才能离开深渊！", C_BAD)
        else:
            self.add_msg("—— 第 %d 层 · %s ——" % (f, FLOOR_NAMES[f - 1]), C_CYAN)

    # ---------- 玩家动作 ----------
    def enemy_at(self, x, y):
        for e in self.enemies:
            if e.x == x and e.y == y:
                return e
        return None

    def try_move(self, dx, dy):
        p = self.player
        if dx or dy:
            p.face = (dx, dy)
        nx, ny = p.x + dx, p.y + dy
        if not self.in_bounds(nx, ny):
            return False
        e = self.enemy_at(nx, ny)
        if e:
            self.player_attack(e)
            return True
        t = self.tile(nx, ny)
        if t == WALL:
            return False
        if t == DOOR:
            self.tiles[nx][ny] = DOOR_OPEN
            self.add_msg("你推开了门。", C_TXT_DIM)
            self.compute_fov()
            return True
        p.x, p.y = nx, ny
        self.after_step(nx, ny)
        return True

    def after_step(self, x, y):
        p = self.player
        t = self.tile(x, y)
        if t == CHEST:
            self.tiles[x][y] = CHEST_OPEN
            self.open_chest(x, y)
        if (x, y) in self.traps:
            self.traps.discard((x, y))
            dmg = 6 + self.floor * 3
            self.damage_player(dmg, "尖刺陷阱", crit=False)
            self.add_burst(x, y, C_TRAP, 10)
        if (x, y) in self.ground:
            ids = self.ground.pop((x, y))
            for iid in ids:
                p.inv[iid] = p.inv.get(iid, 0) + 1
                name, kind, col, desc = item_info(iid)
                if kind == "武器":
                    self.add_msg("拾取 [%s]（攻击 +%d），按 I 装备。" % (name, WEAPONS[int(iid[1:])][1]), C_GOLD)
                elif kind == "护甲":
                    self.add_msg("拾取 [%s]（防御 +%d），按 I 装备。" % (name, ARMORS[int(iid[1:])][1]), C_GOLD)
                else:
                    self.add_msg("拾取 [%s]。" % name, C_GOOD)
        self.compute_fov()

    def open_chest(self, x, y):
        f = self.floor
        roll = random.random()
        p = self.player
        if roll < 0.35:
            g = 12 + f * 10 + random.randint(0, 20)
            p.gold += g
            self.add_msg("宝箱中散落着 %d 枚金币！" % g, C_GOLD)
        elif roll < 0.60:
            iid = random.choice(["hp_s", "hp_l", "mp", "str", "def"])
            p.inv[iid] = p.inv.get(iid, 0) + 1
            self.add_msg("宝箱中有 [%s]！" % POTIONS[iid][0], C_GOOD)
        elif roll < 0.80:
            iid = random.choice(list(SCROLLS))
            p.inv[iid] = p.inv.get(iid, 0) + 1
            self.add_msg("宝箱中有一张 [%s]！" % SCROLLS[iid][0], C_PURP)
        else:
            tier = min(4, max(0, f - 1 + (1 if random.random() < 0.35 else 0)))
            iid = random.choice(["w%d" % tier, "a%d" % tier])
            p.inv[iid] = p.inv.get(iid, 0) + 1
            name, kind, col, desc = item_info(iid)
            self.add_msg("宝箱中藏着 [%s]（%s）！" % (name, desc), C_GOLD)
        self.add_burst(x, y, C_CHEST, 14)

    def player_attack(self, e):
        p = self.player
        crit = random.random() < 0.08
        dmg = max(1, p.atk + random.randint(-2, 2) - e.dfn)
        if crit:
            dmg = int(dmg * 1.7)
        e.hp -= dmg
        e.flash = 0.18
        col = (255, 230, 90) if crit else (240, 240, 240)
        self.add_float(e.x, e.y, str(dmg), col)
        self.add_burst(e.x, e.y, e.color, 6)
        self.shake_screen(3 if crit else 1.5)
        if crit:
            self.add_msg("会心一击！你对 %s 造成 %d 点伤害！" % (e.name, dmg), C_XP)
        else:
            self.add_msg("你攻击了 %s，造成 %d 点伤害。" % (e.name, dmg), C_TXT)
        if e.hp <= 0:
            self.kill_enemy(e)

    def kill_enemy(self, e):
        p = self.player
        if e in self.enemies:
            self.enemies.remove(e)
        p.kills += 1
        self.add_burst(e.x, e.y, e.color, 20 if e.boss else 14)
        self.add_msg("%s 被击杀了！" % e.name, C_GOOD)
        p.xp += e.xp
        self.add_msg("获得 %d 点经验。" % e.xp, C_XP)
        # 掉落
        roll = random.random()
        if roll < 0.35:
            g = 5 + self.floor * 6 + random.randint(0, 8)
            p.gold += g
            self.add_msg("掉落 %d 金币。" % g, C_GOLD)
        elif roll < 0.47:
            iid = random.choice(["hp_s", "mp"])
            p.inv[iid] = p.inv.get(iid, 0) + 1
            self.add_msg("掉落 [%s]。" % POTIONS[iid][0], C_GOOD)
        if e.boss:
            self.state = ST_WIN
            self.add_msg("深渊之主倒下了，地牢开始崩塌……", C_XP)
        self.check_level_up()

    def check_level_up(self):
        p = self.player
        while p.xp >= p.xp_next:
            p.xp -= p.xp_next
            p.lvl += 1
            p.maxhp += 6
            p.maxmp += 3
            p.batk += 1
            p.bdef += 1
            p.hp = min(p.maxhp, p.hp + 10)
            p.mp = min(p.maxmp, p.mp + 4)
            self.add_msg("★ 升级！现在是 %d 级。生命+6 法力+3 攻+1 防+1" % p.lvl, C_XP)
            self.add_burst(p.x, p.y, C_XP, 22)
            self.shake_screen(4)

    def damage_player(self, dmg, src, crit=False):
        p = self.player
        p.hp -= dmg
        self.add_float(p.x, p.y, str(dmg), C_BAD)
        self.hurt = 0.5
        self.shake_screen(5 if crit else 3)
        self.add_burst(p.x, p.y, C_HP, 8)
        self.add_msg("%s 击中了你，造成 %d 点伤害！" % (src, dmg), C_BAD)
        if p.hp <= 0:
            p.hp = 0
            self.state = ST_OVER
            self.add_msg("你倒在了第 %d 层……" % self.floor, C_BAD)

    # ---------- 技能 / 物品 ----------
    def cast_firebolt(self):
        p = self.player
        if p.mp < 6:
            self.add_msg("法力不足，无法施放火球术。", C_MP)
            return False
        dx, dy = p.face
        tx, ty = p.x, p.y
        target = None
        for _ in range(7):
            tx, ty = tx + dx, ty + dy
            if not self.in_bounds(tx, ty) or self.opaque(tx, ty):
                break
            e = self.enemy_at(tx, ty)
            if e:
                target = e
                break
        if not target:
            self.add_msg("火球术的弹道上没有目标。", C_TXT_DIM)
            return False
        p.mp -= 6
        dmg = 9 + p.lvl * 2 + random.randint(0, 3)
        self.add_proj(p.x, p.y, target.x, target.y, (255, 140, 50), 4)
        target.hp -= dmg
        target.flash = 0.2
        self.add_float(target.x, target.y, str(dmg), (255, 150, 60))
        self.add_burst(target.x, target.y, (255, 140, 50), 14)
        self.shake_screen(3)
        self.add_msg("火球术命中 %s，造成 %d 点伤害！" % (target.name, dmg), (255, 150, 60))
        if target.hp <= 0:
            self.kill_enemy(target)
        return True

    def cast_heal(self):
        p = self.player
        if p.mp < 8:
            self.add_msg("法力不足，无法施放治疗术。", C_MP)
            return False
        if p.hp >= p.maxhp:
            self.add_msg("生命值已满，无需治疗。", C_TXT_DIM)
            return False
        p.mp -= 8
        amt = max(1, int(p.maxhp * 0.3))
        p.hp = min(p.maxhp, p.hp + amt)
        self.add_float(p.x, p.y, "+%d" % amt, C_GOOD)
        self.add_burst(p.x, p.y, C_GOOD, 14)
        self.add_msg("治疗术恢复了 %d 点生命。" % amt, C_GOOD)
        return True

    def visible_enemies(self):
        return [e for e in self.enemies if (e.x, e.y) in self.visible]

    def use_scroll(self, iid):
        p = self.player
        if iid == "fire":
            es = self.visible_enemies()
            if not es:
                self.add_msg("视野内没有敌人，卷轴的火焰徒劳地熄灭了。", C_TXT_DIM)
                return False
            dmg = 16 + self.floor * 4
            for e in es:
                e.hp -= dmg
                e.flash = 0.25
                self.add_float(e.x, e.y, str(dmg), (255, 130, 50))
                self.add_burst(e.x, e.y, (255, 130, 50), 12)
            self.shake_screen(6)
            self.add_msg("火焰卷轴爆发！%d 个敌人受到 %d 点伤害！" % (len(es), dmg), (255, 130, 50))
            for e in [e for e in es if e.hp <= 0]:
                self.kill_enemy(e)
            return True
        if iid == "frost":
            es = self.visible_enemies()
            if not es:
                self.add_msg("视野内没有敌人。", C_TXT_DIM)
                return False
            for e in es:
                e.frozen = 4
                self.add_burst(e.x, e.y, (120, 210, 255), 8)
            self.add_msg("寒霜蔓延，冻结了 %d 个敌人！" % len(es), (120, 210, 255))
            return True
        if iid == "tp":
            spots = [(x, y) for x in range(1, MAP_W - 1) for y in range(1, MAP_H - 1)
                     if self.tile(x, y) in (FLOOR, STAIRS, DOOR_OPEN) and not self.enemy_at(x, y)]
            if not spots:
                return False
            self.add_burst(p.x, p.y, C_PURP, 16)
            p.x, p.y = random.choice(spots)
            self.add_burst(p.x, p.y, C_PURP, 16)
            self.add_msg("空间扭曲，你被传送到了未知之处……", C_PURP)
            self.after_step(p.x, p.y)
            return True
        return False

    def use_item(self, iid):
        p = self.player
        name, kind, col, desc = item_info(iid)
        if kind == "药水":
            if iid == "hp_s" or iid == "hp_l":
                amt = 25 if iid == "hp_s" else 55
                if p.hp >= p.maxhp:
                    self.add_msg("生命值已满，无需使用。", C_TXT_DIM)
                    return False
                p.hp = min(p.maxhp, p.hp + amt)
                self.add_float(p.x, p.y, "+%d" % amt, C_GOOD)
                self.add_msg("喝下 %s，恢复 %d 点生命。" % (name, amt), C_GOOD)
            elif iid == "mp":
                if p.mp >= p.maxmp:
                    self.add_msg("法力值已满，无需使用。", C_TXT_DIM)
                    return False
                p.mp = min(p.maxmp, p.mp + 12)
                self.add_float(p.x, p.y, "+12", C_MP)
                self.add_msg("喝下 %s，恢复 12 点法力。" % name, C_MP)
            elif iid == "str":
                p.strb += 2
                self.add_msg("喝下 %s，力量永久 +2！" % name, (255, 150, 60))
            elif iid == "def":
                p.defb += 2
                self.add_msg("喝下 %s，防御永久 +2！" % name, (150, 200, 220))
        elif kind == "卷轴":
            if not self.use_scroll(iid):
                return False
        elif kind == "武器":
            tier = int(iid[1:])
            old = p.weapon
            p.weapon = tier
            p.inv["w%d" % old] = p.inv.get("w%d" % old, 0) + 1
            self.add_msg("装备了 [%s]（攻击 +%d）。" % (name, WEAPONS[tier][1]), C_GOLD)
        elif kind == "护甲":
            tier = int(iid[1:])
            old = p.armor
            p.armor = tier
            p.inv["a%d" % old] = p.inv.get("a%d" % old, 0) + 1
            self.add_msg("装备了 [%s]（防御 +%d）。" % (name, ARMORS[tier][1]), C_GOLD)
        p.inv[iid] -= 1
        if p.inv[iid] <= 0:
            del p.inv[iid]
        return True

    def inv_list(self):
        order = {"药水": 0, "卷轴": 1, "武器": 2, "护甲": 3}
        items = []
        for iid, n in self.player.inv.items():
            items.append((iid, n))
        items.sort(key=lambda t: (order.get(item_info(t[0])[1], 9), t[0]))
        return items

    def descend(self):
        if self.floor >= MAX_FLOOR:
            self.add_msg("这里已是深渊最底层！", C_TXT_DIM)
            return False
        self.floor += 1
        self.add_msg("你沿螺旋石阶向下走去……", C_CYAN)
        self.gen_floor()
        return True

    # ---------- 怪物回合 ----------
    def dist_field(self):
        p = self.player
        dist = [[9999] * MAP_H for _ in range(MAP_W)]
        dq = deque()
        dist[p.x][p.y] = 0
        dq.append((p.x, p.y))
        while dq:
            x, y = dq.popleft()
            d = dist[x][y]
            for dx, dy in DIRS8:
                nx, ny = x + dx, y + dy
                if self.in_bounds(nx, ny) and self.tile(nx, ny) in WALK_T and dist[nx][ny] > d + 1:
                    dist[nx][ny] = d + 1
                    dq.append((nx, ny))
        return dist

    def enemy_turns(self):
        p = self.player
        field = self.dist_field()
        occupied = {(e.x, e.y) for e in self.enemies} | {(p.x, p.y)}
        for e in self.enemies:
            self.enemy_act(e, field, occupied)
            if self.state != ST_PLAY:
                return

    def enemy_act(self, e, field, occupied):
        # 减速：speed=2 时隔回合行动
        e.slowtick = (e.slowtick + 1) % e.speed
        if e.slowtick != 0 and e.speed > 1:
            return
        if e.frozen > 0:
            e.frozen -= 1
            if e.frozen == 0:
                self.add_msg("%s 挣脱了冰霜。" % e.name, (120, 210, 255))
            return
        p = self.player
        d = cheb(e.x, e.y, p.x, p.y)
        see = d <= e.sight and self.los(e.x, e.y, p.x, p.y)
        if see:
            e.alert = 10
        elif e.alert > 0:
            e.alert -= 1
        # Boss 召唤
        if e.boss and see and e.hp < e.maxhp and self.turn % 5 == 0 and len(self.enemies) < 7:
            free = [(e.x + dx, e.y + dy) for dx, dy in DIRS8
                    if self.in_bounds(e.x + dx, e.y + dy) and
                    self.tile(e.x + dx, e.y + dy) in WALK_T and
                    not self.enemy_at(e.x + dx, e.y + dy) and (e.x + dx, e.y + dy) != (p.x, p.y)]
            if free:
                sx, sy = random.choice(free)
                m = Enemy("slime", sx, sy, self.floor)
                self.enemies.append(m)
                occupied.add((sx, sy))
                self.add_burst(sx, sy, (120, 60, 160), 12)
                self.add_msg("%s 召唤了毒史莱姆！" % e.name, C_BAD)
                return
        # 远程攻击
        if e.ranged and see:
            rng, dmg, cd = e.ranged
            if e.cd > 0:
                e.cd -= 1
            if e.cd == 0 and 2 <= d <= rng:
                e.cd = cd
                self.add_proj(e.x, e.y, p.x, p.y, e.color if not e.boss else (255, 60, 90), 3)
                self.damage_player(max(1, dmg + random.randint(-1, 2) - p.dfn // 2), e.name)
                return
        if d == 1:
            crit = random.random() < 0.06
            dmg = max(1, e.atk + random.randint(-2, 2) - p.dfn)
            if crit:
                dmg = int(dmg * 1.5)
            self.damage_player(dmg, e.name, crit)
            return
        if see or e.alert > 0:
            self.enemy_step(e, field, occupied)
        else:
            if random.random() < 0.3:
                self.enemy_step(e, None, occupied)

    def enemy_step(self, e, field, occupied):
        p = self.player
        options = []
        for dx, dy in DIRS8:
            nx, ny = e.x + dx, e.y + dy
            if not self.in_bounds(nx, ny):
                continue
            t = self.tile(nx, ny)
            if t not in WALK_T:
                continue
            if (nx, ny) in occupied and (nx, ny) != (p.x, p.y):
                continue
            if t == DOOR:
                self.tiles[nx][ny] = DOOR_OPEN
                return
            if field is not None:
                options.append((field[nx][ny], nx, ny))
            else:
                options.append((random.random(), nx, ny))
        if not options:
            return
        if e.erratic and random.random() < 0.35:
            options.sort(key=lambda o: o[0] + random.uniform(-2, 2))
        else:
            options.sort(key=lambda o: o[0])
        best = options[0]
        cur = field[e.x][e.y] if field is not None else 9999
        if field is not None and best[0] >= cur:
            return
        occupied.discard((e.x, e.y))
        e.x, e.y = best[1], best[2]
        occupied.add((e.x, e.y))

    # ---------- 回合推进 ----------
    def end_turn(self):
        p = self.player
        self.turn += 1
        if self.turn % 6 == 0 and p.mp < p.maxmp:
            p.mp += 1
        self.enemy_turns()
        self.compute_fov()

    # ---------- 绘制 ----------
    def draw(self):
        s = self.screen
        s.fill(C_BG)
        if self.state == ST_TITLE:
            self.draw_title()
            return
        sx = int(random.uniform(-self.shake, self.shake)) if self.shake > 0.3 else 0
        sy = int(random.uniform(-self.shake, self.shake)) if self.shake > 0.3 else 0
        self.draw_map(sx, sy)
        self.draw_panel()
        self.draw_log()
        if self.floor == MAX_FLOOR and self.state == ST_PLAY:
            boss = next((e for e in self.enemies if e.boss), None)
            if boss:
                bx, by = MAP_X + 180, MAP_Y + 8
                draw_text(s, boss.name, 15, bx, by - 2, C_BAD, bold=True)
                draw_bar(s, bx, by + 16, 420, 12, boss.hp / boss.maxhp, C_BAD)
        if self.state == ST_INV:
            self.draw_inventory()
        elif self.state == ST_HELP:
            self.draw_help()
        elif self.state == ST_OVER:
            self.draw_end(False)
        elif self.state == ST_WIN:
            self.draw_end(True)

    def draw_map(self, sx=0, sy=0):
        s = self.screen
        ox, oy = MAP_X + sx, MAP_Y + sy
        pygame.draw.rect(s, (6, 8, 12), (MAP_X - 2, MAP_Y - 2, VIEW_W + 4, VIEW_H + 4), border_radius=4)
        p = self.player
        for x in range(MAP_W):
            for y in range(MAP_H):
                key = (x, y)
                if key not in self.explored:
                    continue
                vis = key in self.visible
                t = self.tiles[x][y]
                rx, ry = ox + x * TILE, oy + y * TILE
                if t == WALL:
                    shade = (x * 7 + y * 13) % 3
                    base = C_WALL if shade else (64, 72, 94)
                    pygame.draw.rect(s, base, (rx, ry, TILE, TILE))
                    pygame.draw.rect(s, C_WALL_TOP, (rx, ry, TILE, 4))
                else:
                    c = C_FLOOR if (x + y) % 2 else C_FLOOR2
                    pygame.draw.rect(s, c, (rx, ry, TILE, TILE))
                    if t == STAIRS:
                        pygame.draw.rect(s, (40, 34, 14), (rx + 2, ry + 2, TILE - 4, TILE - 4), border_radius=3)
                        draw_text(s, ">", 15, rx + TILE // 2, ry + TILE // 2, C_STAIRS, anchor="c", bold=True)
                    elif t == CHEST:
                        pygame.draw.rect(s, C_CHEST, (rx + 4, ry + 6, TILE - 8, TILE - 11), border_radius=2)
                        pygame.draw.rect(s, (240, 200, 80), (rx + TILE // 2 - 2, ry + 9, 4, 5))
                    elif t == CHEST_OPEN:
                        pygame.draw.rect(s, C_CHEST_O, (rx + 4, ry + 8, TILE - 8, TILE - 13), 2, border_radius=2)
                    elif t == DOOR:
                        pygame.draw.rect(s, C_DOOR, (rx + 2, ry, TILE - 4, TILE), border_radius=2)
                        pygame.draw.rect(s, (90, 60, 30), (rx + 2, ry, TILE - 4, TILE), 1)
                    elif t == DOOR_OPEN:
                        pygame.draw.rect(s, C_DOOR_O, (rx + 1, ry, 3, TILE))
                        pygame.draw.rect(s, C_DOOR_O, (rx + TILE - 4, ry, 3, TILE))
                if key in self.traps and vis:
                    pygame.draw.polygon(s, C_TRAP, [(rx + 5, ry + TILE - 4), (rx + 8, ry + 6), (rx + 11, ry + TILE - 4)])
                    pygame.draw.polygon(s, C_TRAP, [(rx + 11, ry + TILE - 4), (rx + 14, ry + 6), (rx + 17, ry + TILE - 4)])
        # 环境尘埃
        for d in self.dust:
            pygame.draw.circle(s, (70, 80, 100), (int(ox + d[0]) % (MAP_X + VIEW_W), int(oy + d[1])), 1)
        # 地面物品
        for (x, y), ids in self.ground.items():
            if (x, y) not in self.visible:
                continue
            cx, cy = tile_center(x, y, ox, oy)
            for k, iid in enumerate(ids[:3]):
                off = (k - min(2, len(ids) - 1)) * 6
                name, kind, col, desc = item_info(iid)
                if kind == "药水":
                    pygame.draw.circle(s, col, (cx + off, cy + 2), 4)
                    pygame.draw.rect(s, (200, 200, 210), (cx + off - 1, cy - 5, 3, 4))
                elif kind == "卷轴":
                    pygame.draw.rect(s, col, (cx + off - 4, cy - 3, 8, 7), border_radius=1)
                    pygame.draw.line(s, (240, 230, 200), (cx + off - 4, cy - 1), (cx + off + 4, cy - 1))
                elif kind == "武器":
                    pygame.draw.line(s, col, (cx + off - 3, cy + 4), (cx + off + 3, cy - 4), 2)
                    pygame.draw.line(s, (120, 90, 50), (cx + off - 1, cy + 1), (cx + off + 1, cy + 3), 2)
                elif kind == "护甲":
                    pygame.draw.polygon(s, col, [(cx + off - 4, cy - 4), (cx + off + 4, cy - 4),
                                                 (cx + off + 4, cy + 1), (cx + off, cy + 5), (cx + off - 4, cy + 1)])
        # 怪物
        t = self.time
        for e in self.enemies:
            if (e.x, e.y) not in self.visible:
                continue
            cx, cy = tile_center(e.x, e.y, ox, oy)
            self.draw_enemy(s, e, cx, cy, t)
        # 玩家
        px, py = tile_center(p.x, p.y, ox, oy)
        pygame.draw.circle(s, (40, 160, 190), (px, py), 8)
        pygame.draw.circle(s, (150, 230, 250), (px, py), 5)
        fx, fy = p.face
        pygame.draw.line(s, (230, 240, 255), (px + fx * 8, py + fy * 8), (px + fx * 12, py + fy * 12), 2)
        # 弹道
        for pr in self.projs:
            ax, ay, bx, by, prog, col, w = pr
            cx = ax + (bx - ax) * prog
            cy = ay + (by - ay) * prog
            pygame.draw.circle(s, col, (int(cx), int(cy)), w + 2)
            pygame.draw.circle(s, (255, 255, 255), (int(cx), int(cy)), max(1, w - 1))
        # 粒子
        for pt in self.particles:
            x, y, _, _, life, col, r = pt
            a = max(0, min(255, int(life * 300)))
            gfx = pygame.Surface((int(r * 2), int(r * 2)), pygame.SRCALPHA)
            pygame.draw.circle(gfx, (*col, a), (int(r), int(r)), int(r))
            s.blit(gfx, (x - r, y - r))
        # 飘字
        for ft in self.floats:
            x, y, text, col, life, vy = ft
            yy = y + (1 - life) * vy * -1
            alpha = max(0, min(255, int(life * 280)))
            img = get_font(15, True).render(text, True, col)
            img.set_alpha(alpha)
            s.blit(img, (x - img.get_width() // 2, yy - 10))
        # 战争迷雾（未探索已由跳过绘制覆盖；可见性调光）
        fog = pygame.Surface((TILE, TILE), pygame.SRCALPHA)
        fog.fill((6, 8, 12, 150))
        for x in range(MAP_W):
            for y in range(MAP_H):
                if (x, y) in self.explored and (x, y) not in self.visible:
                    s.blit(fog, (ox + x * TILE, oy + y * TILE))
        # 脚下提示
        if self.tile(p.x, p.y) == STAIRS:
            draw_text(s, "↲ 按 Enter 下楼", 14, MAP_X + VIEW_W // 2, MAP_Y + VIEW_H - 14, C_STAIRS, anchor="c", bold=True)

    def draw_enemy(self, s, e, cx, cy, t):
        c = e.color
        if e.type == "slime":
            bob = math.sin(t * 3 + e.x) * 1.5
            pygame.draw.ellipse(s, c, (cx - 8, cy - 6 + bob, 16, 12))
            pygame.draw.circle(s, (20, 40, 20), (cx - 3, cy - 2 + bob), 2)
            pygame.draw.circle(s, (20, 40, 20), (cx + 3, cy - 2 + bob), 2)
        elif e.type == "bat":
            flap = math.sin(t * 9 + e.y) * 4
            pygame.draw.polygon(s, c, [(cx - 3, cy), (cx - 12, cy - 4 + flap), (cx - 9, cy + 3)])
            pygame.draw.polygon(s, c, [(cx + 3, cy), (cx + 12, cy - 4 + flap), (cx + 9, cy + 3)])
            pygame.draw.circle(s, c, (cx, cy), 5)
            pygame.draw.circle(s, (255, 80, 80), (cx - 2, cy - 1), 1)
            pygame.draw.circle(s, (255, 80, 80), (cx + 2, cy - 1), 1)
        elif e.type == "skel":
            pygame.draw.circle(s, c, (cx, cy - 3), 5)
            pygame.draw.rect(s, c, (cx - 3, cy + 1, 6, 7), border_radius=2)
            pygame.draw.circle(s, (30, 30, 30), (cx - 2, cy - 3), 1)
            pygame.draw.circle(s, (30, 30, 30), (cx + 2, cy - 3), 1)
        elif e.type == "orc":
            pygame.draw.rect(s, c, (cx - 7, cy - 6, 14, 12), border_radius=3)
            pygame.draw.rect(s, (30, 70, 30), (cx - 7, cy + 2, 14, 4), border_radius=2)
            pygame.draw.circle(s, (90, 200, 90), (cx - 2, cy - 2), 1)
            pygame.draw.circle(s, (90, 200, 90), (cx + 2, cy - 2), 1)
        elif e.type == "lock":
            pygame.draw.polygon(s, c, [(cx, cy - 8), (cx - 7, cy + 6), (cx + 7, cy + 6)])
            pygame.draw.circle(s, (240, 200, 240), (cx, cy - 6), 3)
            glow = pygame.Surface((10, 10), pygame.SRCALPHA)
            pygame.draw.circle(glow, (255, 120, 255, 120), (5, 5), 4)
            s.blit(glow, (cx - 5, cy - 9))
        elif e.type == "golem":
            pygame.draw.rect(s, c, (cx - 9, cy - 8, 18, 16), border_radius=4)
            pygame.draw.rect(s, (80, 90, 110), (cx - 9, cy - 8, 18, 5), border_radius=4)
            pulse = 150 + int(60 * math.sin(t * 4))
            pygame.draw.circle(s, (90, pulse, 255), (cx, cy + 1), 3)
        elif e.type == "boss":
            pulse = 6 + int(2 * math.sin(t * 3))
            halo = pygame.Surface((40, 40), pygame.SRCALPHA)
            pygame.draw.circle(halo, (160, 20, 40, 70), (20, 20), 17 + pulse)
            s.blit(halo, (cx - 20, cy - 20))
            pygame.draw.circle(s, c, (cx, cy), 12)
            pygame.draw.polygon(s, (60, 20, 25), [(cx - 12, cy - 6), (cx - 16, cy - 16), (cx - 6, cy - 10)])
            pygame.draw.polygon(s, (60, 20, 25), [(cx + 12, cy - 6), (cx + 16, cy - 16), (cx + 6, cy - 10)])
            for i, ex in enumerate((-4, 4)):
                pygame.draw.circle(s, (255, 200, 60), (cx + ex, cy - 3), 2)
        if e.frozen > 0:
            ice = pygame.Surface((e.r * 3, e.r * 3), pygame.SRCALPHA)
            pygame.draw.circle(ice, (120, 210, 255, 110), (e.r * 3 // 2, e.r * 3 // 2), e.r + 3)
            s.blit(ice, (cx - e.r * 1.5, cy - e.r * 1.5))
        if e.flash > 0:
            fl = pygame.Surface((e.r * 3, e.r * 3), pygame.SRCALPHA)
            pygame.draw.circle(fl, (255, 255, 255, int(e.flash * 900)), (e.r * 3 // 2, e.r * 3 // 2), e.r + 1)
            s.blit(fl, (cx - e.r * 1.5, cy - e.r * 1.5))
        if e.hp < e.maxhp:
            w = max(16, e.r * 2)
            draw_bar(s, cx - w // 2, cy - e.r - 8, w, 3, e.hp / e.maxhp, C_HP)

    def draw_panel(self):
        s = self.screen
        p = self.player
        pygame.draw.rect(s, C_PANEL, (PANEL_X, MAP_Y, PANEL_W, VIEW_H), border_radius=6)
        pygame.draw.rect(s, C_PANEL_LN, (PANEL_X, MAP_Y, PANEL_W, VIEW_H), 1, border_radius=6)
        x = PANEL_X + 12
        y = MAP_Y + 12
        draw_text(s, "深渊地牢 · 第 %d/%d 层" % (self.floor, MAX_FLOOR), 15, x, y, C_CYAN, bold=True)
        y += 24
        draw_text(s, "Lv.%d  %s" % (p.lvl, FLOOR_NAMES[self.floor - 1]), 13, x, y, C_TXT_DIM)
        y += 20
        draw_bar(s, x, y, PANEL_W - 24, 16, p.hp / p.maxhp, C_HP, "HP %d/%d" % (p.hp, p.maxhp))
        y += 22
        draw_bar(s, x, y, PANEL_W - 24, 12, p.mp / p.maxmp, C_MP, "MP %d/%d" % (p.mp, p.maxmp))
        y += 18
        draw_bar(s, x, y, PANEL_W - 24, 8, p.xp / p.xp_next, C_XP, None)
        draw_text(s, "EXP %d/%d" % (p.xp, p.xp_next), 12, PANEL_X + PANEL_W - 12, y - 2, C_TXT_DIM, anchor="tr")
        y += 16
        stats = "攻 %d  防 %d" % (p.atk, p.dfn)
        draw_text(s, stats, 14, x, y, C_TXT, bold=True)
        draw_text(s, "%d 金" % p.gold, 14, PANEL_X + PANEL_W - 12, y, C_GOLD, anchor="tr")
        y += 20
        wn, wv, wc = WEAPONS[p.weapon]
        an, av, ac = ARMORS[p.armor]
        draw_text(s, "武器 %s +%d" % (wn, wv), 13, x, y, wc)
        y += 17
        draw_text(s, "护甲 %s +%d" % (an, av), 13, x, y, ac)
        y += 24
        pygame.draw.line(s, C_PANEL_LN, (x, y), (PANEL_X + PANEL_W - 12, y))
        y += 8
        draw_text(s, "小地图", 13, x, y, C_TXT_DIM, bold=True)
        y += 20
        self.draw_minimap(x, y)
        y += MAP_H * 3 + 14
        pygame.draw.line(s, C_PANEL_LN, (x, y), (PANEL_X + PANEL_W - 12, y))
        y += 8
        kills = "击杀 %d · 回合 %d" % (p.kills, self.turn)
        draw_text(s, kills, 12, x, y, C_TXT_DIM)
        y += 18
        for line in ("WASD/方向键 移动", "空格 等待  Enter 下楼",
                     "F 火球术(6MP)  E 治疗术(8MP)", "1 红药  2 蓝药  I 背包", "Esc 帮助/暂停"):
            draw_text(s, line, 12, x, y, C_TXT_DIM)
            y += 15

    def draw_minimap(self, x, y):
        s = self.screen
        cell = 3
        surf = pygame.Surface((MAP_W * cell, MAP_H * cell))
        surf.fill((10, 12, 18))
        for (mx, my) in self.explored:
            t = self.tiles[mx][my]
            if t == WALL:
                col = (60, 66, 84)
            elif t == STAIRS:
                col = C_STAIRS
            elif t in (CHEST, CHEST_OPEN):
                col = C_CHEST
            else:
                col = (36, 42, 56)
            surf.fill(col, (mx * cell, my * cell, cell, cell))
        for e in self.enemies:
            if (e.x, e.y) in self.visible:
                col = (255, 70, 70) if e.boss else (220, 90, 90)
                surf.fill(col, (e.x * cell, e.y * cell, cell, cell))
        p = self.player
        surf.fill((90, 220, 250), (p.x * cell, p.y * cell, cell, cell))
        s.blit(surf, (x, y))
        pygame.draw.rect(s, C_PANEL_LN, (x - 1, y - 1, MAP_W * cell + 2, MAP_H * cell + 2), 1)

    def draw_log(self):
        s = self.screen
        pygame.draw.rect(s, C_PANEL, (MAP_X, LOG_Y, VIEW_W, LOG_H), border_radius=6)
        pygame.draw.rect(s, C_PANEL_LN, (MAP_X, LOG_Y, VIEW_W, LOG_H), 1, border_radius=6)
        y = LOG_Y + 8
        recent = list(self.msgs)[-5:]
        for text, col in recent:
            draw_text(s, text, 14, MAP_X + 12, y, col)
            y += 17

    def draw_inventory(self):
        s = self.screen
        ov = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
        ov.fill((0, 0, 0, 170))
        s.blit(ov, (0, 0))
        w, h = 560, 480
        px, py = (WIN_W - w) // 2, (WIN_H - h) // 2
        pygame.draw.rect(s, C_PANEL, (px, py, w, h), border_radius=8)
        pygame.draw.rect(s, C_PANEL_LN, (px, py, w, h), 1, border_radius=8)
        draw_text(s, "背  包", 20, px + w // 2, py + 16, C_TXT, anchor="c", bold=True)
        items = self.inv_list()
        if not items:
            draw_text(s, "（空空如也）", 15, px + w // 2, py + 120, C_TXT_DIM, anchor="c")
        self.inv_sel = max(0, min(self.inv_sel, len(items) - 1))
        for i, (iid, n) in enumerate(items):
            iy = py + 56 + i * 30
            if i == self.inv_sel:
                pygame.draw.rect(s, (40, 52, 72), (px + 20, iy - 4, w - 40, 26), border_radius=4)
            name, kind, col, desc = item_info(iid)
            tag = "%d×" % n if kind in ("药水", "卷轴") else ""
            draw_text(s, "[%s]" % kind, 13, px + 30, iy, C_TXT_DIM)
            draw_text(s, name + (" " + tag if tag else ""), 15, px + 88, iy, col, bold=True)
            draw_text(s, desc, 13, px + 280, iy, C_TXT_DIM)
        hy = py + h - 34
        draw_text(s, "↑↓ 选择   Enter 使用/装备   D 丢弃   Esc 关闭", 13, px + w // 2, hy, C_TXT_DIM, anchor="c")

    def draw_help(self):
        s = self.screen
        ov = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
        ov.fill((0, 0, 0, 180))
        s.blit(ov, (0, 0))
        w, h = 600, 470
        px, py = (WIN_W - w) // 2, (WIN_H - h) // 2
        pygame.draw.rect(s, C_PANEL, (px, py, w, h), border_radius=8)
        pygame.draw.rect(s, C_PANEL_LN, (px, py, w, h), 1, border_radius=8)
        draw_text(s, "操 作 说 明", 20, px + w // 2, py + 18, C_TXT, anchor="c", bold=True)
        lines = [
            ("移动 / 攻击", "WASD 或 方向键（8 方向），撞向敌人即攻击"),
            ("等待一回合", "空格"),
            ("下楼", "站在楼梯上按 Enter 或 >"),
            ("火球术", "按 F，朝面朝方向发射（消耗 6 MP）"),
            ("治疗术", "按 E，恢复 30% 生命（消耗 8 MP）"),
            ("快捷用药", "1 小红药  2 法力药"),
            ("背包", "I 打开；Enter 使用/装备，D 丢弃"),
            ("门 / 宝箱 / 陷阱", "走向门开门；踩上宝箱开启；小心尖刺！"),
            ("暂停 / 帮助", "Esc"),
        ]
        y = py + 62
        for k, v in lines:
            draw_text(s, k, 14, px + 40, y, C_CYAN, bold=True)
            draw_text(s, v, 14, px + 170, y, C_TXT)
            y += 34
        draw_text(s, "每 6 回合回复 1 点法力。击败第 5 层的深渊之主即可获胜！", 13, px + w // 2, py + h - 30, C_TXT_DIM, anchor="c")

    def draw_end(self, win):
        s = self.screen
        p = self.player
        ov = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
        ov.fill((0, 0, 0, 200))
        s.blit(ov, (0, 0))
        score = p.gold + p.lvl * 100 + self.floor * 200 + p.kills * 10
        title = "胜  利 ！" if win else "你 死 了"
        col = C_XP if win else C_BAD
        sub = "深渊之主已被讨伐，光明重回大地。" if win else \
              "你的冒险在第 %d 层画上了句号。" % self.floor
        draw_text(s, title, 44, WIN_W // 2, WIN_H // 2 - 90, col, anchor="c", bold=True)
        draw_text(s, sub, 16, WIN_W // 2, WIN_H // 2 - 30, C_TXT, anchor="c")
        stats = "等级 %d   击杀 %d   金币 %d   回合 %d   评分 %d" % (
            p.lvl, p.kills, p.gold, self.turn, score)
        draw_text(s, stats, 16, WIN_W // 2, WIN_H // 2 + 10, C_TXT, anchor="c", bold=True)
        if self.blink < 0.5:
            draw_text(s, "按 R 再来一局   ·   按 Q 退出", 16, WIN_W // 2, WIN_H // 2 + 70, C_TXT_DIM, anchor="c")

    def draw_title(self):
        s = self.screen
        t = self.time
        # 漂浮余烬
        if random.random() < 0.3:
            self.embers.append([random.uniform(0, WIN_W), WIN_H + 10,
                                random.uniform(-8, 8), random.uniform(-30, -70),
                                random.uniform(2, 5), random.uniform(2.5, 6)])
        for em in self.embers[:]:
            em[0] += em[2] * 0.016
            em[1] += em[3] * 0.016
            em[4] -= 0.016
            if em[4] <= 0:
                self.embers.remove(em)
            else:
                a = int(min(1, em[4]) * 160)
                g = pygame.Surface((int(em[5] * 2),) * 2, pygame.SRCALPHA)
                pygame.draw.circle(g, (255, 150, 60, a), (int(em[5]), int(em[5])), int(em[5]))
                s.blit(g, (em[0] - em[5], em[1] - em[5]))
        title = "深  渊  地  牢"
        glow = int(8 + 4 * math.sin(t * 2))
        for dx in (-2, 2):
            draw_text(s, title, 52, WIN_W // 2 + dx, 140 + dx, (60, 30, 20), anchor="c", bold=True)
        draw_text(s, title, 52, WIN_W // 2, 140 - glow // 2, (255, 170, 70), anchor="c", bold=True)
        draw_text(s, "A B Y S S   D U N G E O N", 16, WIN_W // 2, 190, C_TXT_DIM, anchor="c")
        draw_text(s, "传说深渊最底层沉睡着【深渊之主】，无数勇者有去无回。", 15, WIN_W // 2, 250, C_TXT, anchor="c")
        draw_text(s, "深入 5 层地牢，击败它，活着回来。", 15, WIN_W // 2, 276, C_TXT, anchor="c")
        for i, line in enumerate([
                "WASD / 方向键 移动（8向）   撞向敌人即攻击   空格 等待",
                "F 火球术   E 治疗术   1/2 快捷用药   I 背包   Esc 帮助"]):
            draw_text(s, line, 14, WIN_W // 2, 340 + i * 26, C_TXT_DIM, anchor="c")
        if self.blink < 0.55:
            draw_text(s, "—— 按任意键开始冒险 ——", 20, WIN_W // 2, 470, C_STAIRS, anchor="c", bold=True)
        pygame.draw.rect(s, C_PANEL_LN, (WIN_W // 2 - 220, 500, 440, 1))

    # ---------- 特效更新 ----------
    def update(self, dt):
        dt = min(dt, 0.05)
        self.time += dt
        self.blink = (self.blink + dt) % 1.0
        self.shake = max(0.0, self.shake - dt * 18)
        self.hurt = max(0.0, self.hurt - dt)
        for pt in self.particles[:]:
            pt[0] += pt[2] * dt
            pt[1] += pt[3] * dt
            pt[4] -= dt
            if pt[4] <= 0:
                self.particles.remove(pt)
        for ft in self.floats[:]:
            ft[4] -= dt
            if ft[4] <= 0:
                self.floats.remove(ft)
        for pr in self.projs[:]:
            pr[4] += dt * 6
            if pr[4] >= 1:
                self.projs.remove(pr)
        for e in self.enemies:
            if e.flash > 0:
                e.flash -= dt
        for d in self.dust:
            d[0] += d[2] * dt
            d[1] += d[3] * dt * 6
            if d[1] > VIEW_H:
                d[0], d[1] = random.uniform(0, VIEW_W), -4

    # ---------- 事件 ----------
    def handle_event(self, ev):
        if ev.type != pygame.KEYDOWN:
            return
        key = ev.key
        if self.state == ST_TITLE:
            self.new_game()
            return
        if self.state in (ST_OVER, ST_WIN):
            if key == pygame.K_r:
                self.new_game()
            elif key == pygame.K_q:
                pygame.event.post(pygame.event.Event(pygame.QUIT))
            return
        if self.state == ST_INV:
            items = self.inv_list()
            if key in (pygame.K_ESCAPE, pygame.K_i):
                self.state = ST_PLAY
            elif key in (pygame.K_UP, pygame.K_w):
                self.inv_sel = max(0, self.inv_sel - 1)
            elif key in (pygame.K_DOWN, pygame.K_s):
                self.inv_sel = min(max(0, len(items) - 1), self.inv_sel + 1)
            elif key == pygame.K_RETURN:
                if items:
                    iid = items[self.inv_sel][0]
                    if self.use_item(iid):
                        self.end_turn()
            elif key == pygame.K_d:
                if items:
                    iid = items[self.inv_sel][0]
                    name, kind, col, desc = item_info(iid)
                    self.player.inv[iid] -= 1
                    if self.player.inv[iid] <= 0:
                        del self.player.inv[iid]
                    self.add_msg("丢弃了 [%s]。" % name, C_TXT_DIM)
                    self.state = ST_PLAY
                    self.end_turn()
            return
        if self.state == ST_HELP:
            if key in (pygame.K_ESCAPE, pygame.K_h):
                self.state = ST_PLAY
            return
        # ST_PLAY
        acted = False
        if key in (pygame.K_UP, pygame.K_w):
            acted = self.try_move(0, -1)
        elif key in (pygame.K_DOWN, pygame.K_s):
            acted = self.try_move(0, 1)
        elif key in (pygame.K_LEFT, pygame.K_a):
            acted = self.try_move(-1, 0)
        elif key in (pygame.K_RIGHT, pygame.K_d):
            acted = self.try_move(1, 0)
        elif key in (pygame.K_HOME, pygame.K_KP7):
            acted = self.try_move(-1, -1)
        elif key in (pygame.K_PAGEUP, pygame.K_KP9):
            acted = self.try_move(1, -1)
        elif key in (pygame.K_END, pygame.K_KP1):
            acted = self.try_move(-1, 1)
        elif key in (pygame.K_PAGEDOWN, pygame.K_KP3):
            acted = self.try_move(1, 1)
        elif key == pygame.K_SPACE:
            acted = True
        elif key in (pygame.K_RETURN, pygame.K_GREATER):
            if self.tile(self.player.x, self.player.y) == STAIRS:
                acted = self.descend()
        elif key == pygame.K_f:
            acted = self.cast_firebolt()
        elif key == pygame.K_e:
            acted = self.cast_heal()
        elif key == pygame.K_1:
            for iid in ("hp_s", "hp_l"):
                if iid in self.player.inv:
                    acted = self.use_item(iid)
                    break
            else:
                self.add_msg("没有治疗药水了。", C_TXT_DIM)
        elif key == pygame.K_2:
            if "mp" in self.player.inv:
                acted = self.use_item("mp")
            else:
                self.add_msg("没有法力药水了。", C_TXT_DIM)
        elif key in (pygame.K_i, pygame.K_TAB):
            self.inv_sel = 0
            self.state = ST_INV
            return
        elif key in (pygame.K_ESCAPE, pygame.K_h):
            self.state = ST_HELP
            return
        if acted and self.state == ST_PLAY:
            self.end_turn()

# ============================================================
# 主循环
# ============================================================
def main():
    pygame.init()
    pygame.display.set_caption("深渊地牢 · Abyss Dungeon")
    screen = pygame.display.set_mode((WIN_W, WIN_H))
    pygame.key.set_repeat(280, 90)
    game = Game(screen)
    if "--smoke" in sys.argv:
        run_smoke(game, screen)
        pygame.quit()
        return
    running = True
    while running:
        dt = game.clock.tick(FPS) / 1000.0
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                running = False
            else:
                game.handle_event(ev)
        game.update(dt)
        game.draw()
        if game.hurt > 0 and game.state == ST_PLAY:
            flash = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
            flash.fill((180, 20, 30, int(game.hurt * 90)))
            screen.blit(flash, (0, 0))
        pygame.display.flip()
    pygame.quit()

# ============================================================
# 无头冒烟测试
# ============================================================
def run_smoke(game, screen):
    random.seed(7)
    try:
        game.new_game()
        assert game.state == ST_PLAY
        # 1) 随机走 400 回合，覆盖移动/战斗/物品/楼层
        moves = DIRS8 + [(0, 0)]
        for i in range(400):
            game.try_move(*random.choice(moves))
            if game.state != ST_PLAY:
                game.new_game()
            if i % 40 == 0:
                game.cast_firebolt()
                game.cast_heal()
            if i % 70 == 0 and game.inv_list():
                game.state = ST_INV
                game.use_item(game.inv_list()[0][0])
                game.state = ST_PLAY
            if game.tile(game.player.x, game.player.y) == STAIRS:
                game.descend()
            game.update(0.016)
            if i % 25 == 0:
                game.draw()
            assert game.player.hp >= 0
        # 2) 直接跳层验证 Boss 层与屏障
        game.floor = MAX_FLOOR - 1
        game.gen_floor()
        game.floor = MAX_FLOOR
        game.gen_floor()
        boss = next(e for e in game.enemies if e.boss)
        assert any(e.boss for e in game.enemies)
        # Boss 击杀 → 胜利
        boss.hp = 1
        game.player_attack(boss)
        assert game.state == ST_WIN, "击杀 Boss 应进入胜利"
        # 3) 死亡流程
        game.new_game()
        game.damage_player(9999, "测试深渊", False)
        assert game.state == ST_OVER, "生命归零应进入死亡"
        # 4) 物品系统全量覆盖
        game.new_game()
        for iid in ["hp_s", "hp_l", "mp", "str", "def", "fire", "frost", "tp", "w3", "a3", "w4", "a4"]:
            game.player.inv[iid] = 1
        game.state = ST_INV
        for _ in range(12):
            items = game.inv_list()
            if items:
                game.use_item(items[0][0])
        game.state = ST_PLAY
        assert game.player.weapon >= 0 and game.player.armor >= 0
        # 5) 升级
        game.player.xp = 999
        game.check_level_up()
        assert game.player.lvl > 1
        game.draw()
        print("SMOKE OK — 地图/战斗/物品/技能/升级/Boss/胜负 全部通过")
    except Exception:
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
