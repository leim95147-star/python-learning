"""指令解析：把按键/字符串翻译为游戏动作。

被行输入模式与 curses TUI 共用，保证两套界面行为一致。
"""
from . import persistence

# 移动方向（含斜向，采用经典 roguelike 键位）
DIR_KEYS = {
    "w": (0, -1), "k": (0, -1), "8": (0, -1),
    "s": (0, 1), "j": (0, 1), "2": (0, 1),
    "a": (-1, 0), "h": (-1, 0), "4": (-1, 0),
    "d": (1, 0), "l": (1, 0), "6": (1, 0),
    "y": (-1, -1), "u": (1, -1), "b": (-1, 1), "n": (1, 1),
}
WAIT_KEYS = {".", " "}
SKILL_KEYS = ("z", "x", "c", "v")
DEFAULT_SAVE = "savegame.json"

HELP_TEXT = ("指令：w/a/s/d 或方向键移动（y/u/b/n 斜向，撞向怪物即攻击）｜. 等待｜"
             "g 拾取｜1-9 使用物品｜z/x/c/v 施放技能（再按方向）｜"
             "> 下楼｜S 存档｜? 帮助｜q 退出")


def handle_command(state, cmd):
    """逐字符执行指令，返回 True 表示继续游戏。"""
    if cmd is None:
        return False
    for ch in cmd.strip():
        # 施法等待方向：方向键结算，其他键取消
        if state.pending_skill is not None:
            if ch in DIR_KEYS:
                state.resolve_skill(*DIR_KEYS[ch])
            else:
                state.pending_skill = None
                state.log("已取消施法。")
            if state.game_over or state.victory:
                return False
            continue

        if ch == "q":
            return False
        if ch == "?":
            state.log(HELP_TEXT)
            continue
        if ch == "S":
            persistence.save(state, DEFAULT_SAVE)
            state.log(f"已保存到 {DEFAULT_SAVE}")
            continue
        if ch in DIR_KEYS:
            state.player_move(*DIR_KEYS[ch])
        elif ch in WAIT_KEYS:
            state.player_wait()
        elif ch == "g":
            state.player_pickup()
        elif ch == ">":
            state.player_descend()
        elif ch in SKILL_KEYS:
            state.start_skill(SKILL_KEYS.index(ch))
        elif ch.isdigit() and ch != "0":
            state.player_use(int(ch) - 1)

        if state.game_over or state.victory:
            return False
    return True
