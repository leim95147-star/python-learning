"""curses TUI 界面。

把 view.py 生成的视口网格画到终端上，并处理按键。
非交互环境下 run_tui 返回 False，由调用方回退到行输入模式。
"""
import sys

try:
    import curses
except ImportError:  # 某些平台无 curses
    curses = None

from . import commands
from .view import build_cells

HUD_ROWS = 5

# 颜色名 -> curses 基础色
_CURSES_COLORS = {
    "black": 1, "red": 2, "green": 3, "brown": 4, "yellow": 4,
    "blue": 5, "magenta": 6, "cyan": 7, "white": 8,
}
# curses 基础色常量在导入后才能访问，故延迟构建
_BASE_PAIRS = ("black", "red", "green", "brown", "blue", "magenta", "cyan", "white")


def _split_bright(color):
    if color.startswith("bright_"):
        return color[len("bright_"):], True
    return color, False


def _init_pairs():
    raw = {
        "black": curses.COLOR_BLACK, "red": curses.COLOR_RED, "green": curses.COLOR_GREEN,
        "brown": curses.COLOR_YELLOW, "blue": curses.COLOR_BLUE, "magenta": curses.COLOR_MAGENTA,
        "cyan": curses.COLOR_CYAN, "white": curses.COLOR_WHITE,
    }
    pairs = {}
    for i, name in enumerate(_BASE_PAIRS, start=1):
        curses.init_pair(i, raw[name], curses.COLOR_BLACK)
        pairs[name] = i
    return pairs


def _attr(pairs, color, bold=False):
    if color is None:
        return curses.A_BOLD if bold else curses.A_NORMAL
    base, is_bright = _split_bright(color)
    pair = pairs.get(base)
    attr = curses.color_pair(pair) if pair else curses.A_NORMAL
    if bold or is_bright:
        attr |= curses.A_BOLD
    return attr


def _put(stdscr, row, col, text, attr, cols):
    if not text:
        return
    try:
        stdscr.addnstr(row, col, text, max(0, cols - col - 1), attr)
    except curses.error:
        pass


def _draw_hud(stdscr, state, top, cols, pairs):
    p = state.player
    rows = stdscr.getmaxyx()[0]
    status = "已通关" if state.victory else ("已阵亡" if state.game_over else "")
    _put(stdscr, top, 0,
         f"地牢探险 第{state.floor}/{state.max_floor}层 回合{state.turns} {status}", 
         _attr(pairs, "bright_white"), cols)

    hp_color = "green" if p.hp > p.max_hp * 0.5 else ("yellow" if p.hp > p.max_hp * 0.25 else "red")
    _put(stdscr, top + 1, 0,
         f"HP {max(0, p.hp)}/{p.max_hp}  MP {p.mp}/{p.max_mp}  Lv{p.level} "
         f"XP {p.xp}/{p.xp_to_next}  ATK {p.effective_attack()} DEF {p.effective_defense()} "
         f"金{p.gold}",
         _attr(pairs, hp_color), cols)

    skills = " ".join(f"{commands.SKILL_KEYS[i]}){s.name}({s.cost}MP)"
                      for i, s in enumerate(p.skills))
    inv = " ".join(f"{i + 1}){it.name}" for i, it in enumerate(p.inventory)) or "空"
    _put(stdscr, top + 2, 0, f"技能: {skills}", _attr(pairs, "bright_cyan"), cols)
    _put(stdscr, top + 3, 0, f"背包: {inv}", _attr(pairs, "white"), cols)

    for i, msg in enumerate(state.messages[-1:]):
        row = top + 4 + i
        if row < rows:
            _put(stdscr, row, 0, msg, _attr(pairs, "bright_yellow"), cols)


def _key_to_cmd(key):
    arrows = {curses.KEY_UP: "w", curses.KEY_DOWN: "s",
              curses.KEY_LEFT: "a", curses.KEY_RIGHT: "d"}
    if key in arrows:
        return arrows[key]
    if key in (10, 13, getattr(curses, "KEY_ENTER", 343)):
        return "."
    if key == 27:
        return "\x1b"
    if 0 <= key < 256:
        return chr(key)
    return None


def _curses_main(stdscr, state):
    curses.curs_set(0)
    stdscr.keypad(True)
    pairs = _init_pairs()

    while True:
        stdscr.erase()
        rows, cols = stdscr.getmaxyx()
        map_rows = max(1, rows - HUD_ROWS)
        grid, _, _ = build_cells(state, map_rows, cols)
        for sy, row in enumerate(grid):
            for sx, (char, color, visible) in enumerate(row):
                if char == " ":
                    continue
                attr = _attr(pairs, color)
                if not visible:
                    attr |= curses.A_DIM
                try:
                    stdscr.addstr(sy, sx, char, attr)
                except curses.error:
                    pass

        _draw_hud(stdscr, state, map_rows, cols, pairs)
        stdscr.refresh()

        if state.game_over or state.victory:
            _put(stdscr, rows - 1, 0, "按任意键退出……", _attr(pairs, "bright_white"), cols)
            stdscr.refresh()
            stdscr.getch()
            return

        cmd = _key_to_cmd(stdscr.getch())
        if cmd and not commands.handle_command(state, cmd):
            return


def run_tui(state):
    """尝试以 curses 运行；不可用时返回 False。"""
    if curses is None or not sys.stdin.isatty():
        return False
    try:
        curses.wrapper(_curses_main, state)
        return True
    except Exception:
        return False
