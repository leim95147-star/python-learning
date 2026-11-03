"""职业与技能定义。

每个职业拥有不同的基础属性、初始物品与专属技能。
技能类型 kind：
    bolt  直线远程单体（沿方向命中第一个敌人）
    aoe   直线投掷后范围爆炸
    dash  沿方向冲锋并撞击路径上的敌人
    heal  自我治疗（无需选择方向）
"""
from dataclasses import dataclass

from .items import make_item


@dataclass(frozen=True)
class SkillDef:
    key: str
    name: str
    cost: int
    kind: str
    power: int
    range: int = 0
    radius: int = 0
    desc: str = ""


@dataclass(frozen=True)
class ClassDef:
    key: str
    name: str
    hp: int
    attack: int
    defense: int
    mp: int
    color: str
    desc: str
    start_items: tuple = ()
    skills: tuple = ()


CLASSES = {
    "warrior": ClassDef(
        "warrior", "战士", 42, 7, 3, 10, "bright_red",
        "近战强韧，冲锋突进与旋风斩",
        ("铁剑", "皮甲", "治疗药水"),
        (SkillDef("charge", "冲锋", 5, "dash", 5, range=4, desc="沿方向突进并撞击敌人"),
         SkillDef("whirl", "旋风斩", 6, "aoe", 6, range=1, radius=1, desc="对相邻范围造成伤害")),
    ),
    "mage": ClassDef(
        "mage", "法师", 24, 4, 1, 26, "bright_cyan",
        "法力汹涌，火球与奥术飞弹",
        ("治疗药水", "治疗药水"),
        (SkillDef("missile", "奥术飞弹", 4, "bolt", 10, range=7, desc="远程单体法术"),
         SkillDef("fireball", "火球术", 8, "aoe", 8, range=6, radius=1, desc="落点范围伤害")),
    ),
    "ranger": ClassDef(
        "ranger", "游侠", 32, 6, 2, 14, "bright_green",
        "远程精准，机动灵活",
        ("铁剑", "治疗药水"),
        (SkillDef("shot", "精准射击", 3, "bolt", 8, range=9, desc="远距离精准单体"),
         SkillDef("wind", "疾风步", 5, "dash", 3, range=5, desc="快速位移")),
    ),
    "cleric": ClassDef(
        "cleric", "牧师", 30, 5, 2, 20, "bright_yellow",
        "治疗续航，神圣冲击",
        ("皮甲", "治疗药水"),
        (SkillDef("heal", "治疗术", 6, "heal", 14, desc="回复自身生命"),
         SkillDef("smite", "神圣冲击", 5, "bolt", 9, range=5, desc="远程神圣伤害")),
    ),
}


def get_class(key):
    return CLASSES.get(key, CLASSES["warrior"])


def starting_items(class_def):
    return [make_item(name) for name in class_def.start_items]
