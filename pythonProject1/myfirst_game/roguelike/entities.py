"""实体定义：玩家与各类怪物。"""
from .classes import starting_items

INVENTORY_SIZE = 16


class Entity:
    """所有可放在地图格上的生命体的基类。"""

    def __init__(self, x, y, char, name, hp, attack, defense, color="white", xp_reward=0):
        self.x = x
        self.y = y
        self.char = char
        self.name = name
        self.max_hp = hp
        self.hp = hp
        self.attack = attack        # 基础攻击力
        self.defense = defense      # 基础防御力
        self.color = color
        self.xp_reward = xp_reward  # 被击败后给予玩家的经验
        self.alive = True

    @property
    def pos(self):
        return (self.x, self.y)

    def effective_attack(self):
        return self.attack

    def effective_defense(self):
        return self.defense

    def __repr__(self):
        return f"<{self.name} pos={self.pos} hp={self.hp}/{self.max_hp}>"


class Player(Entity):
    def __init__(self, x, y, class_def):
        super().__init__(x, y, "@", class_def.name, class_def.hp,
                         class_def.attack, class_def.defense, class_def.color)
        self.class_key = class_def.key
        self.level = 1
        self.xp = 0
        self.xp_to_next = 20
        self.gold = 0
        self.inventory = []
        self.weapon = None
        self.armor = None
        self.mp = class_def.mp      # 当前法力
        self.max_mp = class_def.mp  # 法力上限
        self.poison = 0             # 中毒剩余回合
        self.regen = 0              # 再生剩余回合
        self.skills = list(class_def.skills)
        for item in starting_items(class_def):
            self.inventory.append(item)

    def effective_attack(self):
        return self.attack + (self.weapon.atk if self.weapon else 0)

    def effective_defense(self):
        return self.defense + (self.armor.defense if self.armor else 0)

    def add_item(self, item):
        """把物品放入背包（金币直接计入）。返回 (是否成功, 提示文本)。"""
        if item.kind == "gold":
            self.gold += item.value
            return True, f"拾取了 {item.value} 枚金币（共 {self.gold}）"
        if len(self.inventory) >= INVENTORY_SIZE:
            return False, "背包已满，无法拾取"
        self.inventory.append(item)
        return True, f"拾取了 {item.name}"


class Monster(Entity):
    def __init__(self, x, y, name, char, hp, attack, defense, xp_reward, color,
                 aggro=False, applies_poison=False, is_boss=False):
        super().__init__(x, y, char, name, hp, attack, defense, color, xp_reward)
        self.aggro = aggro
        self.applies_poison = applies_poison
        self.is_boss = is_boss
        self.phase = 1        # Boss 阶段
        self.breath_cd = 0    # 龙息冷却
        self.summon_cd = 0    # 召唤冷却


# 怪物模板：min_floor/max_floor 决定该怪物出现的层数区间
MONSTER_TEMPLATES = [
    {"name": "老鼠", "char": "r", "hp": 6, "attack": 3, "defense": 0, "xp": 5,
     "color": "brown", "min_floor": 1, "max_floor": 3},
    {"name": "蝙蝠", "char": "b", "hp": 8, "attack": 4, "defense": 0, "xp": 8,
     "color": "bright_black", "min_floor": 1, "max_floor": 4},
    {"name": "毒蛛", "char": "S", "hp": 10, "attack": 4, "defense": 1, "xp": 16,
     "color": "bright_blue", "min_floor": 2, "max_floor": 5, "poison": True},
    {"name": "哥布林", "char": "g", "hp": 12, "attack": 5, "defense": 1, "xp": 14,
     "color": "green", "min_floor": 2, "max_floor": 5},
    {"name": "骷髅兵", "char": "s", "hp": 18, "attack": 7, "defense": 2, "xp": 24,
     "color": "bright_white", "min_floor": 3, "max_floor": 7},
    {"name": "兽人战士", "char": "o", "hp": 26, "attack": 9, "defense": 4, "xp": 40,
     "color": "bright_green", "min_floor": 4, "max_floor": 8},
    {"name": "巨魔", "char": "T", "hp": 40, "attack": 12, "defense": 5, "xp": 70,
     "color": "bright_magenta", "min_floor": 6, "max_floor": 8},
]

BOSS_NAME = "远古巨龙"
MINION_NAME = "兽人战士"


def _monster_from_template(t, x, y):
    return Monster(x, y, t["name"], t["char"], t["hp"], t["attack"],
                   t["defense"], t["xp"], t["color"],
                   applies_poison=t.get("poison", False))


def spawn_monsters(rng, rooms, floor, start):
    """在当前层生成普通怪物，尽量避开玩家出生房间。"""
    monsters = []
    candidate_rooms = rooms[1:] if len(rooms) > 1 else rooms
    templates = [t for t in MONSTER_TEMPLATES if t["min_floor"] <= floor <= t["max_floor"]]
    if not templates:
        templates = [MONSTER_TEMPLATES[-1]]

    count = 4 + floor * 2
    for _ in range(count):
        room = rng.choice(candidate_rooms)
        x = rng.randint(room.x1, room.x2)
        y = rng.randint(room.y1, room.y2)
        if (x, y) == start:
            continue
        if any(m.x == x and m.y == y for m in monsters):
            continue
        monsters.append(_monster_from_template(rng.choice(templates), x, y))
    return monsters


def spawn_boss(x, y):
    """最终 Boss：多阶段、带龙息与召唤。"""
    return Monster(x, y, BOSS_NAME, "D", 150, 16, 7, 600, "bright_red",
                   aggro=True, is_boss=True)


def summon_minion(x, y):
    """Boss 召唤出的仆从。"""
    t = next(t for t in MONSTER_TEMPLATES if t["name"] == MINION_NAME)
    return _monster_from_template(t, x, y)
