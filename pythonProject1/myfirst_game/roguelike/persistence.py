"""存档读写：把 GameState 完整序列化为 JSON，再原样还原。"""
import json
import random

from .classes import get_class
from .dungeon import Map
from .entities import Player, Monster
from .items import Item

SAVE_VERSION = 1


# ---------------------------------------------------------------- 物件转换
def _item_to_dict(item):
    return {
        "name": item.name, "kind": item.kind, "glyph": item.glyph, "color": item.color,
        "value": item.value, "atk": item.atk, "defense": item.defense,
        "power": item.power, "effect": item.effect,
    }


def _item_from_dict(d):
    return Item(d["name"], d["kind"], d["glyph"], d["color"], d["value"],
                d["atk"], d["defense"], d["power"], d["effect"])


def _entity_common(e):
    return {"x": e.x, "y": e.y, "char": e.char, "name": e.name,
            "max_hp": e.max_hp, "hp": e.hp, "attack": e.attack, "defense": e.defense,
            "color": e.color, "xp_reward": e.xp_reward, "alive": e.alive}


def _player_to_dict(p):
    d = _entity_common(p)
    d.update({
        "type": "player",
        "class_key": p.class_key,
        "level": p.level, "xp": p.xp, "xp_to_next": p.xp_to_next, "gold": p.gold,
        "mp": p.mp, "max_mp": p.max_mp, "poison": p.poison, "regen": p.regen,
        "inventory": [_item_to_dict(i) for i in p.inventory],
        "weapon": _item_to_dict(p.weapon) if p.weapon else None,
        "armor": _item_to_dict(p.armor) if p.armor else None,
    })
    return d


def _player_from_dict(d):
    p = Player(d["x"], d["y"], get_class(d["class_key"]))   # 技能随职业重建
    p.name, p.char, p.color = d["name"], d["char"], d["color"]
    p.max_hp, p.hp = d["max_hp"], d["hp"]
    p.attack, p.defense = d["attack"], d["defense"]
    p.level, p.xp, p.xp_to_next, p.gold = d["level"], d["xp"], d["xp_to_next"], d["gold"]
    p.mp, p.max_mp = d["mp"], d["max_mp"]
    p.poison, p.regen = d["poison"], d["regen"]
    p.inventory = [_item_from_dict(i) for i in d["inventory"]]
    p.weapon = _item_from_dict(d["weapon"]) if d["weapon"] else None
    p.armor = _item_from_dict(d["armor"]) if d["armor"] else None
    p.alive = d["alive"]
    return p


def _monster_to_dict(m):
    d = _entity_common(m)
    d.update({"type": "monster", "aggro": m.aggro, "applies_poison": m.applies_poison,
              "is_boss": m.is_boss, "phase": m.phase,
              "breath_cd": m.breath_cd, "summon_cd": m.summon_cd})
    return d


def _monster_from_dict(d):
    m = Monster(d["x"], d["y"], d["name"], d["char"], d["max_hp"], d["attack"],
                d["defense"], d["xp_reward"], d["color"],
                aggro=d["aggro"], applies_poison=d["applies_poison"], is_boss=d["is_boss"])
    m.hp = d["hp"]
    m.alive = d["alive"]
    m.phase = d["phase"]
    m.breath_cd = d["breath_cd"]
    m.summon_cd = d["summon_cd"]
    return m


# ---------------------------------------------------------------- 整局转换
def to_dict(state):
    d = state.dungeon
    return {
        "version": SAVE_VERSION,
        "seed": state.seed,
        "floor": state.floor, "max_floor": state.max_floor, "turns": state.turns,
        "messages": list(state.messages),
        "game_over": state.game_over, "victory": state.victory,
        "rng_state": state.rng.getstate(),
        "dungeon": {"width": d.width, "height": d.height, "tiles": d.tiles},
        "stairs": list(state.stairs),
        "explored": [list(p) for p in state.explored],
        "visible": [list(p) for p in state.visible],
        "player": _player_to_dict(state.player),
        "monsters": [_monster_to_dict(m) for m in state.monsters],
        "items": [{"x": k[0], "y": k[1], "item": _item_to_dict(v)}
                  for k, v in state.items.items()],
    }


def from_dict(data):
    from .game import GameState

    state = GameState.__new__(GameState)
    state.seed = data["seed"]
    state.rng = random.Random()
    version, inner, gauss = data["rng_state"]
    state.rng.setstate((version, tuple(inner), gauss))
    state.floor = data["floor"]
    state.max_floor = data["max_floor"]
    state.turns = data["turns"]
    state.messages = list(data["messages"])
    state.game_over = data["game_over"]
    state.victory = data["victory"]

    dd = data["dungeon"]
    d = Map(dd["width"], dd["height"])
    d.tiles = dd["tiles"]
    state.dungeon = d
    state.rooms = []                             # 房间信息仅在生成时使用
    state.stairs = tuple(data["stairs"])
    state.explored = {tuple(p) for p in data["explored"]}
    state.visible = {tuple(p) for p in data["visible"]}
    state.player = _player_from_dict(data["player"])
    state.monsters = [_monster_from_dict(m) for m in data["monsters"]]
    state.items = {(it["x"], it["y"]): _item_from_dict(it["item"]) for it in data["items"]}
    state.pending_skill = None
    return state


def save(state, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(to_dict(state), f, ensure_ascii=False, indent=1)


def load(path):
    with open(path, "r", encoding="utf-8") as f:
        return from_dict(json.load(f))
