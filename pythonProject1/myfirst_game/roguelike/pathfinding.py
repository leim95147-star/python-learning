"""网格寻路工具（A*）。

本模块保持纯函数风格，不与具体游戏对象耦合：
调用者只需传入 is_walkable 回调即可复用。
"""
import heapq

DIRECTIONS_4 = ((0, -1), (1, 0), (0, 1), (-1, 0))
DIRECTIONS_8 = ((0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1))


def _reconstruct(came_from, current):
    path = [current]
    while current in came_from:
        current = came_from[current]
        path.append(current)
    path.reverse()
    return path


def astar(width, height, start, goal, is_walkable, diagonal=True, max_expansions=4000):
    """在 width×height 的网格上求 start→goal 的最短路径。

    返回从 start 到 goal 的坐标列表（含首尾）；不可达时返回 None。
    is_walkable(x, y) 判断某格是否可通行；目标格即使不可通行也会被尝试。
    max_expansions 用于限制搜索规模，避免极端情况下卡死。
    """
    if start == goal:
        return [start]

    dirs = DIRECTIONS_8 if diagonal else DIRECTIONS_4
    open_heap = []
    counter = 0
    g_score = {start: 0.0}
    came_from = {}
    closed = set()

    def heuristic(p):
        return abs(p[0] - goal[0]) + abs(p[1] - goal[1])

    heapq.heappush(open_heap, (heuristic(start), 0.0, counter, start))
    expansions = 0

    while open_heap:
        _, g, _, current = heapq.heappop(open_heap)
        if current in closed:
            continue
        if current == goal:
            return _reconstruct(came_from, current)
        closed.add(current)
        expansions += 1
        if expansions > max_expansions:
            break

        cx, cy = current
        for dx, dy in dirs:
            nx, ny = cx + dx, cy + dy
            if not (0 <= nx < width and 0 <= ny < height):
                continue
            neighbor = (nx, ny)
            if neighbor in closed:
                continue
            if neighbor != goal and not is_walkable(nx, ny):
                continue
            # 禁止贴着墙角斜穿
            if dx and dy:
                if not is_walkable(cx + dx, cy) or not is_walkable(cx, cy + dy):
                    continue
            step = 1.4142135 if (dx and dy) else 1.0
            tentative = g + step
            if tentative < g_score.get(neighbor, float("inf")):
                came_from[neighbor] = current
                g_score[neighbor] = tentative
                counter += 1
                heapq.heappush(open_heap,
                               (tentative + heuristic(neighbor), tentative, counter, neighbor))
    return None
