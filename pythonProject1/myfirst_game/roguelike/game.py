"""游戏核心：回合状态机与所有交互规则。"""
import random

from .classes import get_class
from .dungeon import generate_dungeon, WALL, FLOOR
from .entities import Player, spawn_monsters, spawn_boss, summon_minion, BOSS_NAME
from .items import random_item
from .pathfinding import astar

MAX_FLOOR = 8
FOV_RADIUS = 8
MAX_MESSAGES = 200
CRIT_CHANCE = 0.10
POISON_TURNS = 3
MP_REGEN_INTERVAL = 4      # 每 N 回合回复 1 点法力
DIRECTIONS_8 = ((0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1))


class GameState:
    """一次完整冒险的全部状态。"""

    def __init__(self, seed=None, player_class="warrior"):
        self.seed = seed
        self.rng = random.Random(seed)
        self.floor = 1
        self.max_floor = MAX_FLOOR
        self.turns = 0
        self.messages = []
        self.game_over = False
        self.victory = False
        self.player = Player(0, 0, get_class(player_class))
        self.dungeon = None
        self.rooms = []
        self.stairs = (0, 0)
        self.monsters = []
        self.items = {}          # (x, y) -> Item，散落在地面的物品
        self.explored = set()
        self.visible = set()
        self.pending_skill = None  # 已选择但等待方向输入的技能
        self._generate_level()

    # ---------------------------------------------------------------- 日志
    def log(self, message):
        self.messages.append(message)
        if len(self.messages) > MAX_MESSAGES:
            self.messages = self.messages[-MAX_MESSAGES:]

    # ------------------------------------------------------------ 关卡生成
    def _generate_level(self):
        d, rooms, start, stairs = generate_dungeon(self.rng)
        self.dungeon = d
        self.rooms = rooms
        self.stairs = stairs
        self.player.x, self.player.y = start
        self.explored = set()
        self.visible = set()
        self.monsters = spawn_monsters(self.rng, rooms, self.floor, start)
        self.items = {}

        if self.floor >= self.max_floor:
            # 最后一层：楼梯由 Boss 把守，击败它即可通关
            d.tiles[stairs[1]][stairs[0]] = FLOOR
            self.monsters.append(spawn_boss(*stairs))
            self.log(f"你踏入了地牢最深处（第 {self.floor} 层），空气中弥漫着龙的气息……")
        else:
            self.log(f"你来到地牢第 {self.floor} 层。")

        # 在各房间随机撒一些物品
        for room in rooms[1:]:
            for _ in range(self.rng.randint(0, 2)):
                x = self.rng.randint(room.x1, room.x2)
                y = self.rng.randint(room.y1, room.y2)
                if (x, y) not in self.items and (x, y) != start and d.is_walkable(x, y):
                    self.items[(x, y)] = random_item(self.rng, self.floor)

        self._update_fov()

    def _update_fov(self):
        self.visible = self.dungeon.compute_fov(self.player.pos, FOV_RADIUS)
        self.explored |= self.visible

    # ------------------------------------------------------------ 查询工具
    def monster_at(self, x, y):
        for m in self.monsters:
            if m.alive and m.x == x and m.y == y:
                return m
        return None

    def entity_at(self, x, y):
        if (self.player.x, self.player.y) == (x, y):
            return self.player
        return self.monster_at(x, y)

    def _occupied(self, x, y):
        if (self.player.x, self.player.y) == (x, y):
            return True
        return self.monster_at(x, y) is not None

    # ------------------------------------------------------------ 玩家行动
    def player_move(self, dx, dy):
        if self.game_over or self.victory:
            return False
        nx, ny = self.player.x + dx, self.player.y + dy
        if not self.dungeon.in_bounds(nx, ny):
            return False
        target = self.monster_at(nx, ny)
        if target:
            self._attack(self.player, target)   # 撞向怪物 = 发起攻击
            self.end_turn()
            return True
        if self.dungeon.tiles[ny][nx] == WALL:
            return False
        self.player.x, self.player.y = nx, ny
        self._auto_pickup_gold()
        self.end_turn()
        return True

    def player_wait(self):
        if self.game_over or self.victory:
            return False
        self.end_turn()
        return True

    def player_pickup(self):
        if self.game_over or self.victory:
            return False
        item = self.items.get(self.player.pos)
        if not item:
            self.log("这里没有可拾取的物品。")
            return False
        ok, msg = self.player.add_item(item)
        self.log(msg)
        if ok:
            del self.items[self.player.pos]
            self.end_turn()
            return True
        return False

    def player_use(self, index):
        if self.game_over or self.victory:
            return False
        inv = self.player.inventory
        if not (0 <= index < len(inv)):
            self.log("没有这个物品。")
            return False
        item = inv[index]
        p = self.player

        if item.kind == "weapon":
            old = p.weapon
            p.weapon = item
            inv.remove(item)
            if old:
                inv.append(old)
            self.log(f"你装备了 {item.name}（攻击 +{item.atk}）。")
        elif item.kind == "armor":
            old = p.armor
            p.armor = item
            inv.remove(item)
            if old:
                inv.append(old)
            self.log(f"你穿上了 {item.name}（防御 +{item.defense}）。")
        elif item.effect == "strength":
            p.attack += item.power
            inv.remove(item)
            self.log(f"你感到力量涌现，攻击力 +{item.power}！")
        elif item.effect == "regen":
            p.regen += 8
            inv.remove(item)
            self.log("再生之力涌入体内。")
        elif item.effect == "teleport":
            inv.remove(item)
            self._teleport()
        elif item.effect == "missile":
            inv.remove(item)
            self._cast_missile(item.power)
        elif item.kind == "potion":
            healed = min(item.power, p.max_hp - p.hp)
            p.hp += healed
            inv.remove(item)
            self.log(f"你喝下 {item.name}，回复了 {healed} 点生命。")
        else:
            self.log("这个物品无法直接使用。")
            return False

        self.end_turn()
        return True

    def player_descend(self):
        if self.game_over or self.victory:
            return False
        if self.player.pos != self.stairs or self.floor >= self.max_floor:
            self.log("这里没有向下的楼梯。")
            return False
        self.floor += 1
        self._generate_level()
        return True

    # ------------------------------------------------------------ 回合推进
    def end_turn(self):
        if self.game_over or self.victory:
            return
        self.turns += 1
        for m in list(self.monsters):
            if self.game_over or self.victory:
                break
            if m.alive:
                self._monster_turn(m)
        self._tick_status()
        if self.turns % MP_REGEN_INTERVAL == 0 and self.player.mp < self.player.max_mp:
            self.player.mp += 1
        self._update_fov()

    # ------------------------------------------------------------ 战斗结算
    def _attack(self, attacker, defender):
        atk = attacker.effective_attack()
        dfn = defender.effective_defense()
        crit = self.rng.random() < CRIT_CHANCE
        if crit:
            damage = max(1, atk * 2 - dfn)
        else:
            damage = max(1, atk + self.rng.randint(0, 2) - dfn)
        defender.hp -= damage
        text = f"{attacker.name} 攻击 {defender.name}，造成 {damage} 点伤害"
        if crit:
            text += "（暴击！）"
        self.log(text)

        if getattr(attacker, "applies_poison", False) and isinstance(defender, Player) and defender.hp > 0:
            defender.poison = POISON_TURNS
            self.log("你中毒了！")

        if defender.hp <= 0:
            self._on_death(defender)

    def _on_death(self, entity):
        entity.alive = False
        if isinstance(entity, Player):
            entity.hp = 0
            self.game_over = True
            self.log("你倒下了……地牢吞噬了又一位冒险者。")
            return

        if entity in self.monsters:
            self.monsters.remove(entity)
        self.log(f"{entity.name} 被击败了！")
        self._gain_xp(entity.xp_reward)
        if entity.name == BOSS_NAME:
            self.victory = True
            self.log("巨龙轰然倒地，你征服了整座地牢！")

    def _gain_xp(self, amount):
        p = self.player
        p.xp += amount
        self.log(f"获得 {amount} 点经验。")
        while p.xp >= p.xp_to_next:
            p.xp -= p.xp_to_next
            p.level += 1
            p.max_hp += 6
            p.hp = p.max_hp
            p.attack += 1
            p.defense += 1
            p.xp_to_next = 20 + (p.level - 1) * 15
            self.log(f"升级！你现在是 {p.level} 级，最大生命 {p.max_hp}。")

    def _tick_status(self):
        p = self.player
        if p.poison > 0:
            p.poison -= 1
            p.hp -= 1
            self.log("毒性发作，损失 1 点生命。")
            if p.hp <= 0:
                self.game_over = True
                self.log("毒发了，你没能挺过来……")
                return
        if p.regen > 0:
            p.regen -= 1
            if p.hp < p.max_hp:
                p.hp += 1

    # ------------------------------------------------------------ 技能系统
    def start_skill(self, index):
        """选择技能：自我治疗立即结算，其余进入等待方向的状态。"""
        if self.game_over or self.victory:
            return False
        skills = self.player.skills
        if not (0 <= index < len(skills)):
            self.log("没有这个技能。")
            return False
        skill = skills[index]
        if self.player.mp < skill.cost:
            self.log(f"法力不足，无法施放 {skill.name}（需要 {skill.cost} 点）。")
            return False
        if skill.kind == "heal":
            self.player.mp -= skill.cost
            healed = min(skill.power, self.player.max_hp - self.player.hp)
            self.player.hp += healed
            self.log(f"你施放 {skill.name}，回复 {healed} 点生命。")
            self.end_turn()
            return True
        self.pending_skill = skill
        self.log(f"已选择 {skill.name}，请按方向键决定方向（其他键取消）。")
        return True

    def resolve_skill(self, dx, dy):
        """用给定方向结算等待中的技能。"""
        skill = self.pending_skill
        self.pending_skill = None
        if skill is None:
            return False
        if self.player.mp < skill.cost:
            self.log("法力不足。")
            return False
        self.player.mp -= skill.cost
        if skill.kind == "bolt":
            self._skill_bolt(skill, dx, dy)
        elif skill.kind == "aoe":
            self._skill_aoe(skill, dx, dy)
        elif skill.kind == "dash":
            self._skill_dash(skill, dx, dy)
        self.end_turn()
        return True

    def _skill_bolt(self, skill, dx, dy):
        """沿方向命中射程内第一个敌人。"""
        x, y = self.player.pos
        target = None
        for _ in range(skill.range):
            x, y = x + dx, y + dy
            if not self.dungeon.in_bounds(x, y) or self.dungeon.tiles[y][x] == WALL:
                break
            m = self.monster_at(x, y)
            if m:
                target = m
                break
        if target:
            target.hp -= skill.power
            self.log(f"{skill.name} 命中 {target.name}，造成 {skill.power} 点伤害。")
            if target.hp <= 0:
                self._on_death(target)
        else:
            self.log(f"{skill.name} 没有命中目标。")

    def _skill_aoe(self, skill, dx, dy):
        """沿方向飞行的投掷物，在落点周围 range 内造成范围伤害。"""
        ix, iy = self.player.x, self.player.y
        x, y = self.player.pos
        for _ in range(skill.range):
            x, y = x + dx, y + dy
            if not self.dungeon.in_bounds(x, y) or self.dungeon.tiles[y][x] == WALL:
                break
            ix, iy = x, y
            if self.monster_at(x, y):
                break
        hits = 0
        for m in list(self.monsters):
            if m.alive and max(abs(m.x - ix), abs(m.y - iy)) <= skill.radius:
                m.hp -= skill.power
                hits += 1
                if m.hp <= 0:
                    self._on_death(m)
        self.log(f"{skill.name} 在 ({ix},{iy}) 炸开，命中 {hits} 个敌人。")

    def _skill_dash(self, skill, dx, dy):
        """沿方向突进，撞击路径上的第一个敌人并停下。"""
        x, y = self.player.pos
        moved = 0
        for _ in range(skill.range):
            nx, ny = x + dx, y + dy
            if not self.dungeon.is_walkable(nx, ny):
                break
            m = self.monster_at(nx, ny)
            if m:
                m.hp -= skill.power
                moved += 1
                self.log(f"你撞向 {m.name}，造成 {skill.power} 点伤害。")
                if m.hp <= 0:
                    self._on_death(m)
                break
            x, y = nx, ny
            moved += 1
        self.player.x, self.player.y = x, y
        self._auto_pickup_gold()
        self.log(f"你向前冲锋了 {moved} 格。")

    # ------------------------------------------------------------ 怪物 AI
    def _monster_turn(self, m):
        if m.is_boss:
            self._boss_turn(m)
            return
        p = self.player
        dist = max(abs(m.x - p.x), abs(m.y - p.y))
        if dist <= 12 and self.dungeon.has_line_of_sight(m.pos, p.pos):
            m.aggro = True

        if not m.aggro:
            if self.rng.random() < 0.15:
                self._wander(m)
            return

        if dist <= 1:                      # 相邻即攻击
            self._attack(m, p)
            return

        path = astar(self.dungeon.width, self.dungeon.height, m.pos, p.pos,
                     self.dungeon.is_walkable, max_expansions=1500)
        if path and len(path) > 1:
            nx, ny = path[1]
            if (nx, ny) == p.pos:
                self._attack(m, p)
            elif not self._occupied(nx, ny):
                m.x, m.y = nx, ny

    def _wander(self, m):
        dx, dy = self.rng.choice(((0, -1), (1, 0), (0, 1), (-1, 0)))
        nx, ny = m.x + dx, m.y + dy
        if self.dungeon.is_walkable(nx, ny) and not self._occupied(nx, ny):
            m.x, m.y = nx, ny

    # ------------------------------------------------------------ Boss 阶段
    def _boss_turn(self, m):
        """多阶段 Boss：狂暴龙息 → 最终形态召唤 + 强化。"""
        p = self.player
        ratio = m.hp / m.max_hp
        phase = 1 if ratio > 0.66 else (2 if ratio > 0.33 else 3)
        if phase > m.phase:
            m.phase = phase
            if phase == 2:
                m.attack += 3
                self.log("巨龙发出震耳欲聋的咆哮，进入狂暴状态！")
            else:
                m.attack += 3
                m.defense += 2
                self.log("巨龙进入最终形态，召唤仆从并喷吐烈焰！")

        if m.breath_cd > 0:
            m.breath_cd -= 1
        if m.summon_cd > 0:
            m.summon_cd -= 1

        dist = max(abs(m.x - p.x), abs(m.y - p.y))

        # 最终形态：优先召唤仆从
        if m.phase >= 3 and m.summon_cd == 0:
            self._boss_summon(m)
            m.summon_cd = 8
            return

        # 二阶段起：远程龙息
        if (m.phase >= 2 and m.breath_cd == 0 and dist <= 8
                and self.dungeon.has_line_of_sight(m.pos, p.pos)):
            dmg = 6 + m.phase * 3
            p.hp -= dmg
            self.log(f"巨龙喷吐烈焰，造成 {dmg} 点伤害！")
            m.breath_cd = 3
            if p.hp <= 0:
                self._on_death(p)
            return

        if dist <= 1:
            self._attack(m, p)
            return

        path = astar(self.dungeon.width, self.dungeon.height, m.pos, p.pos,
                     self.dungeon.is_walkable, max_expansions=2000)
        if path and len(path) > 1:
            nx, ny = path[1]
            if (nx, ny) == p.pos:
                self._attack(m, p)
            elif not self._occupied(nx, ny):
                m.x, m.y = nx, ny

    def _boss_summon(self, m):
        offsets = list(DIRECTIONS_8)
        self.rng.shuffle(offsets)
        placed = 0
        for dx, dy in offsets:
            if placed >= 2:
                break
            x, y = m.x + dx, m.y + dy
            if self.dungeon.is_walkable(x, y) and not self._occupied(x, y):
                self.monsters.append(summon_minion(x, y))
                placed += 1
        if placed:
            self.log(f"巨龙召唤出 {placed} 个仆从！")

    # ------------------------------------------------------------ 辅助效果
    def _auto_pickup_gold(self):
        item = self.items.get(self.player.pos)
        if item and item.kind == "gold":
            ok, msg = self.player.add_item(item)
            if ok:
                del self.items[self.player.pos]
                self.log(msg)

    def _teleport(self):
        candidates = [(x, y)
                      for y in range(self.dungeon.height)
                      for x in range(self.dungeon.width)
                      if self.dungeon.is_walkable(x, y) and not self._occupied(x, y)]
        if candidates:
            self.player.x, self.player.y = self.rng.choice(candidates)
        self.log("一阵闪光之后，你被传送到别处。")

    def _cast_missile(self, power):
        alive = [m for m in self.monsters if m.alive]
        if not alive:
            self.log("魔法飞弹没有命中任何目标。")
            return
        target = min(alive, key=lambda m: abs(m.x - self.player.x) + abs(m.y - self.player.y))
        target.hp -= power
        self.log(f"魔法飞弹击中 {target.name}，造成 {power} 点伤害。")
        if target.hp <= 0:
            self._on_death(target)
