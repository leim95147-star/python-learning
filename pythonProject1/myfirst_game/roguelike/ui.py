"""终端渲染（行输入模式）：把游戏状态绘制成文本帧。"""
from . import commands
from .view import terrain_glyph

ANSI = {
    "black": 30, "red": 31, "green": 32, "brown": 33, "yellow": 33, "blue": 34,
    "magenta": 35, "cyan": 36, "white": 37,
    "bright_black": 90, "bright_red": 91, "bright_green": 92, "bright_yellow": 93,
    "bright_blue": 94, "bright_magenta": 95, "bright_cyan": 96, "bright_white": 97,
}
RESET = "\033[0m"


def _paint(text, color, use_color):
    if not use_color or not color:
        return text
    code = ANSI.get(color)
    if code is None:
        return text
    return f"\033[{code}m{text}{RESET}"


def _hp_bar(hp, max_hp, width, use_color):
    hp = max(0, hp)
    filled = int(width * hp / max_hp) if max_hp else 0
    filled = max(0, min(width, filled))
    bar = "█" * filled + "░" * (width - filled)
    if hp > max_hp * 0.5:
        color = "green"
    elif hp > max_hp * 0.25:
        color = "yellow"
    else:
        color = "red"
    return "[" + _paint(bar, color, use_color) + "]"


def render(state, use_color=False):
    """生成一帧文本画面（含地图、状态栏、技能/背包与消息）。"""
    d = state.dungeon
    p = state.player
    lines = []

    status = ""
    if state.victory:
        status = "【已通关】"
    elif state.game_over:
        status = "【已阵亡】"
    lines.append(f"=== 地牢探险 ===  第 {state.floor}/{state.max_floor} 层  "
                 f"回合 {state.turns}  {status}")

    for y in range(d.height):
        row = []
        for x in range(d.width):
            pos = (x, y)
            if pos not in state.explored:
                row.append(" ")
                continue
            char, color = terrain_glyph(d, x, y)
            visible = pos in state.visible
            if visible:
                ent = state.entity_at(x, y)
                if ent:
                    char, color = ent.char, ent.color
                elif pos in state.items:
                    item = state.items[pos]
                    char, color = item.glyph, item.color
            else:
                color = None    # 记忆中的地形不发光
            row.append(_paint(char, color, use_color))
        lines.append("".join(row))

    lines.append("")
    lines.append(f"HP {_hp_bar(p.hp, p.max_hp, 20, use_color)} {max(0, p.hp)}/{p.max_hp}   "
                 f"MP {p.mp}/{p.max_mp}   Lv{p.level} XP {p.xp}/{p.xp_to_next}   "
                 f"ATK {p.effective_attack()} DEF {p.effective_defense()}   金币 {p.gold}")
    lines.append(f"武器: {p.weapon.name if p.weapon else '无'}   "
                 f"护甲: {p.armor.name if p.armor else '无'}")
    if p.poison > 0:
        lines.append(_paint(f"※ 中毒（剩余 {p.poison} 回合）", "green", use_color))
    if p.regen > 0:
        lines.append(_paint(f"※ 再生（剩余 {p.regen} 回合）", "bright_cyan", use_color))

    skills = "  ".join(f"{commands.SKILL_KEYS[i]}){s.name}({s.cost}MP)"
                       for i, s in enumerate(p.skills))
    lines.append("技能: " + (skills or "（无）"))
    if p.inventory:
        inv = "  ".join(f"{i + 1}){it.name}" for i, it in enumerate(p.inventory))
    else:
        inv = "（空）"
    lines.append("背包: " + inv)

    lines.append("-" * min(d.width, 72))
    for msg in state.messages[-6:]:
        lines.append(msg)
    return "\n".join(lines)
