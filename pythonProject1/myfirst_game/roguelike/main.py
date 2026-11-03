"""命令行入口与交互循环。"""
import argparse
import sys

from .game import GameState
from .ui import render
from . import simulation

MOVE_KEYS = {
    "w": (0, -1), "k": (0, -1),
    "s": (0, 1), "j": (0, 1),
    "a": (-1, 0), "h": (-1, 0),
    "d": (1, 0), "l": (1, 0),
}
WAIT_KEYS = {".", " ", "5"}
HELP_TEXT = ("指令：w/a/s/d 或 k/h/j/l 移动（撞向怪物即攻击）｜. 原地等待｜"
             "g 拾取｜1-9 使用物品｜> 下楼｜? 帮助｜q 退出")

ARROW_MAP = {"A": "w", "B": "s", "C": "d", "D": "a"}


def _getch():
    """尝试以原始模式读取单个按键；非终端环境返回 None。"""
    try:
        import termios
        import tty
    except ImportError:
        return None
    if not sys.stdin.isatty():
        return None
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
    return ch


def _read_command():
    """读取一条指令。终端下读单键，否则回退到整行输入。"""
    ch = _getch()
    if ch is not None:
        if ch == "\x1b":                    # 方向键等转义序列
            seq = sys.stdin.read(2)
            return ARROW_MAP.get(seq[-1:], "")
        return ch
    try:
        return input("指令> ")
    except EOFError:
        return None


def _handle(state, cmd):
    """按字符依次执行指令，返回 True 表示继续游戏。"""
    if cmd is None:
        return False
    for ch in cmd.strip():
        if ch == "q":
            return False
        if ch == "?":
            state.log(HELP_TEXT)
            continue
        if ch in MOVE_KEYS:
            state.player_move(*MOVE_KEYS[ch])
        elif ch in WAIT_KEYS:
            state.player_wait()
        elif ch == "g":
            state.player_pickup()
        elif ch == ">":
            state.player_descend()
        elif ch.isdigit() and ch != "0":
            state.player_use(int(ch) - 1)
        if state.game_over or state.victory:
            return False
    return True


def interactive_loop(state, use_color):
    print("欢迎来到《地牢探险》！输入 ? 查看指令，q 退出。")
    while True:
        if use_color:
            print("\033[2J\033[H", end="")     # 清屏，仅终端有意义
        print(render(state, use_color))
        if state.game_over or state.victory:
            break
        cmd = _read_command()
        if not _handle(state, cmd):
            break
    print("游戏结束，感谢游玩。")


def main(argv=None):
    parser = argparse.ArgumentParser(description="地牢探险 —— 一个复杂的 Python Roguelike")
    parser.add_argument("--seed", type=int, default=None, help="随机种子（可用同一地牢复现）")
    parser.add_argument("--sim", type=int, default=0, metavar="TURNS",
                        help="无头模拟：自动游玩 N 回合，用于演示与自测")
    parser.add_argument("--verbose", action="store_true", help="模拟时额外打印最终画面")
    parser.add_argument("--color", action="store_true", help="强制启用 ANSI 颜色")
    args = parser.parse_args(argv)

    if args.sim:
        simulation.run(args.seed, args.sim, verbose=args.verbose)
        return

    state = GameState(seed=args.seed)
    use_color = args.color or sys.stdout.isatty()
    interactive_loop(state, use_color)


if __name__ == "__main__":
    main()
