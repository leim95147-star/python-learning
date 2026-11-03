"""地牢地图数据结构与程序化生成。

瓦片编码：
    WALL   = 0  墙
    FLOOR  = 1  地板
    STAIRS = 2  向下的楼梯
"""

WALL = 0
FLOOR = 1
STAIRS = 2


class Rect:
    """矩形房间，(x1, y1) 为左上角、(x2, y2) 为右下角（均含边界）。"""

    def __init__(self, x, y, w, h):
        self.x1 = x
        self.y1 = y
        self.x2 = x + w - 1
        self.y2 = y + h - 1

    @property
    def center(self):
        return ((self.x1 + self.x2) // 2, (self.y1 + self.y2) // 2)

    def intersects(self, other, pad=1):
        return (self.x1 - pad <= other.x2 and self.x2 + pad >= other.x1 and
                self.y1 - pad <= other.y2 and self.y2 + pad >= other.y1)

    def cells(self):
        for y in range(self.y1, self.y2 + 1):
            for x in range(self.x1, self.x2 + 1):
                yield (x, y)


class Map:
    """瓦片网格，附带通行性判断与视野计算。"""

    def __init__(self, width, height):
        self.width = width
        self.height = height
        self.tiles = [[WALL] * width for _ in range(height)]

    def in_bounds(self, x, y):
        return 0 <= x < self.width and 0 <= y < self.height

    def is_wall(self, x, y):
        return (not self.in_bounds(x, y)) or self.tiles[y][x] == WALL

    def is_walkable(self, x, y):
        return self.in_bounds(x, y) and self.tiles[y][x] != WALL

    def has_line_of_sight(self, a, b):
        """a 到 b 之间是否无遮挡（两端点本身不计入阻挡）。"""
        ox, oy = a
        for (x, y) in _bresenham(a[0], a[1], b[0], b[1])[1:-1]:
            if self.tiles[y][x] == WALL:
                return False
        return True

    def compute_fov(self, origin, radius):
        """以 origin 为中心、radius 为半径计算可见格集合（逐格连线判定）。"""
        visible = set()
        ox, oy = origin
        r2 = radius * radius
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                if dx * dx + dy * dy > r2:
                    continue
                x, y = ox + dx, oy + dy
                if not self.in_bounds(x, y):
                    continue
                if self.has_line_of_sight(origin, (x, y)):
                    visible.add((x, y))
        return visible


def _bresenham(x0, y0, x1, y1):
    """Bresenham 直线，返回经过的所有格子坐标。"""
    points = []
    dx = abs(x1 - x0)
    dy = abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx - dy
    while True:
        points.append((x0, y0))
        if x0 == x1 and y0 == y1:
            break
        e2 = 2 * err
        if e2 > -dy:
            err -= dy
            x0 += sx
        if e2 < dx:
            err += dx
            y0 += sy
    return points


def _carve_rect(m, rect):
    for (x, y) in rect.cells():
        if m.in_bounds(x, y):
            m.tiles[y][x] = FLOOR


def _carve_h(m, x1, x2, y):
    for x in range(min(x1, x2), max(x1, x2) + 1):
        if m.in_bounds(x, y) and m.tiles[y][x] == WALL:
            m.tiles[y][x] = FLOOR


def _carve_v(m, y1, y2, x):
    for y in range(min(y1, y2), max(y1, y2) + 1):
        if m.in_bounds(x, y) and m.tiles[y][x] == WALL:
            m.tiles[y][x] = FLOOR


def _connect(m, a, b, rng):
    """用 L 形走廊连接两个坐标点。"""
    if rng.random() < 0.5:
        _carve_h(m, a[0], b[0], a[1])
        _carve_v(m, a[1], b[1], b[0])
    else:
        _carve_v(m, a[1], b[1], a[0])
        _carve_h(m, a[0], b[0], b[1])


def generate_dungeon(rng, width=64, height=34, max_rooms=14, min_size=5, max_size=11):
    """随机生成"房间 + 走廊"式地牢。

    返回 (map, rooms, player_start, stairs)：
        map          生成的 Map
        rooms        Rect 列表
        player_start 起始坐标
        stairs       向下楼梯坐标
    """
    m = Map(width, height)
    rooms = []
    attempts = max_rooms * 4
    for _ in range(attempts):
        if len(rooms) >= max_rooms:
            break
        w = rng.randint(min_size, max_size)
        h = rng.randint(min_size, max_size)
        x = rng.randint(1, max(1, width - w - 2))
        y = rng.randint(1, max(1, height - h - 2))
        rect = Rect(x, y, w, h)
        if any(rect.intersects(other) for other in rooms):
            continue
        _carve_rect(m, rect)
        if rooms:
            _connect(m, rooms[-1].center, rect.center, rng)
        rooms.append(rect)

    # 额外连接几条随机走廊，制造环状结构，让地图更有趣
    for _ in range(rng.randint(0, 3)):
        if len(rooms) >= 3:
            a, b = rng.sample(rooms, 2)
            _connect(m, a.center, b.center, rng)

    start = rooms[0].center
    stairs = rooms[-1].center
    if stairs == start:  # 起点与楼梯不能重合
        for cell in rooms[-1].cells():
            if cell != start:
                stairs = cell
                break
    m.tiles[stairs[1]][stairs[0]] = STAIRS
    return m, rooms, start, stairs
