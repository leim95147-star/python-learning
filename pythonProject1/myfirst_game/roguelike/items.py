"""物品定义与随机掉落。"""
from dataclasses import dataclass


@dataclass
class Item:
    """一件物品。不同 kind 使用不同字段组合。"""

    name: str
    kind: str                 # potion / weapon / armor / scroll / gold
    glyph: str = "!"
    color: str = "white"
    value: int = 0            # 金币面额
    atk: int = 0              # 武器攻击加成
    defense: int = 0          # 护甲防御加成
    power: int = 0            # 药水/卷轴强度
    effect: str = ""          # 特殊效果标识

    def describe(self):
        if self.kind == "weapon":
            return f"{self.name}（攻击 +{self.atk}）"
        if self.kind == "armor":
            return f"{self.name}（防御 +{self.defense}）"
        if self.kind == "gold":
            return f"{self.name} ×{self.value}"
        if self.effect == "strength":
            return f"{self.name}（永久攻击 +{self.power}）"
        if self.effect == "regen":
            return f"{self.name}（持续回复生命）"
        if self.effect == "teleport":
            return f"{self.name}（随机传送）"
        if self.effect == "missile":
            return f"{self.name}（对最近敌人造成 {self.power} 伤害）"
        return f"{self.name}（回复 {self.power} 生命）"


# (出现权重基数, 物品模板)
_ITEM_TABLE = [
    (10, Item("治疗药水", "potion", "!", "bright_green", power=12)),
    (5, Item("强效药水", "potion", "!", "bright_green", power=28)),
    (3, Item("力量药水", "potion", "!", "bright_magenta", power=1, effect="strength")),
    (4, Item("再生药水", "potion", "!", "bright_cyan", effect="regen")),
    (8, Item("铁剑", "weapon", "/", "bright_cyan", atk=3)),
    (4, Item("钢剑", "weapon", "/", "bright_cyan", atk=6)),
    (7, Item("皮甲", "armor", "[", "white", defense=1)),
    (3, Item("锁子甲", "armor", "[", "bright_white", defense=3)),
    (4, Item("传送卷轴", "scroll", "?", "bright_yellow", effect="teleport")),
    (4, Item("魔法飞弹卷轴", "scroll", "?", "bright_yellow", power=15, effect="missile")),
]


def _clone(item):
    return Item(item.name, item.kind, item.glyph, item.color, item.value,
                item.atk, item.defense, item.power, item.effect)


def make_item(name):
    """按名字取一个全新物品实例（用于职业初始装备等）。"""
    for _, tpl in _ITEM_TABLE:
        if tpl.name == name:
            return _clone(tpl)
    raise KeyError(f"未知物品：{name}")


def random_item(rng, depth):
    """按当前层数加权生成一件物品；层数越深越容易出好装备。"""
    if rng.random() < 0.35:
        return Item("金币", "gold", "$", "bright_yellow",
                    value=rng.randint(5, 6 + depth * 6))

    candidates, weights = [], []
    for base, tpl in _ITEM_TABLE:
        weight = base
        if tpl.kind == "weapon" and tpl.atk >= 6:
            weight += depth * 2
        elif tpl.kind == "armor" and tpl.defense >= 3:
            weight += depth * 2
        elif tpl.effect == "strength":
            weight += depth
        candidates.append(tpl)
        weights.append(weight)

    chosen = rng.choices(range(len(candidates)), weights=weights, k=1)[0]
    return _clone(candidates[chosen])
