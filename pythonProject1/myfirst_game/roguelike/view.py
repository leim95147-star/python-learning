"""视口与逐格画面构建。

把"某格显示什么字符/颜色"的逻辑集中在这里，
既供 TUI（curses）复用，也能脱离终端独立测试。
"""
from .dungeon import WALL, STAIRS


def terrain_glyph(d, x, y):
    """返回地形 (字符, 颜色名)。"""
    t = d.tiles[y][x]
    if t == WALL:
        return "#", "white"
    if t == STAIRS:
        return ">", "bright_yellow"
    return ".", None


def cell_at(state, x, y):
    """返回单格 (字符, 颜色名, 是否可见)。越界或未探索显示为空白。"""
    d = state.dungeon
    if not d.in_bounds(x, y) or (x, y) not in state.explored:
        return " ", None, False
    char, color = terrain_glyph(d, x, y)
    visible = (x, y) in state.visible
    if visible:
        ent = state.entity_at(x, y)
        if ent:
            char, color = ent.char, ent.color
        elif (x, y) in state.items:
            item = state.items[(x, y)]
            char, color = item.glyph, item.color
    else:
        color = None    # 记忆中的地形不发光
    return char, color, visible


def camera_origin(state, rows, cols):
    """以玩家为中心计算视口左上角，并夹紧在地图范围内。"""
    d = state.dungeon
    px, py = state.player.pos
    cx = px - cols // 2
    cy = py - rows // 2
    cx = max(0, min(cx, max(0, d.width - cols)))
    cy = max(0, min(cy, max(0, d.height - rows)))
    return cx, cy


def build_cells(state, rows, cols):
    """构建 rows×cols 的视口网格，返回 (grid, origin_x, origin_y)。"""
    cx, cy = camera_origin(state, rows, cols)
    grid = []
    for sy in range(rows):
        row = []
        y = cy + sy
        for sx in range(cols):
            row.append(cell_at(state, cx + sx, y))
        grid.append(row)
    return grid, cx, cy
