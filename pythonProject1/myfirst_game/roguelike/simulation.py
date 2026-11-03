"""无头自动游玩：用于演示与自测（不需要终端交互）。"""
from .game import GameState
from .entities import BOSS_NAME
from .pathfinding import astar
from .ui import render

NEIGHBORS = ((0, -1), (1, 0), (0, 1), (-1, 0),
             (1, 1), (-1, -1), (1, -1), (-1, 1))


def _aligned_dir(p, m, max_range):
    """若怪物与玩家处于同一行/列/对角线且在射程内，返回对应单位方向。"""
    dx, dy = m.x - p.x, m.y - p.y
    if dx == 0 and 0 < abs(dy) <= max_range:
        return (0, 1 if dy > 0 else -1)
    if dy == 0 and 0 < abs(dx) <= max_range:
        return (1 if dx > 0 else -1, 0)
    if abs(dx) == abs(dy) and 0 < abs(dx) <= max_range:
        return (1 if dx > 0 else -1, 1 if dy > 0 else -1)
    return None


def _skill_index(p, kind):
    for i, s in enumerate(p.skills):
        if s.kind == kind:
            return i
    return None


def _auto_step(state):
    """用简单启发式规则替玩家做一次决策。"""
    p = state.player

    # 1) 濒死先治疗（技能优先，其次药水）
    if p.hp < p.max_hp * 0.35:
        heal_idx = _skill_index(p, "heal")
        if heal_idx is not None and p.mp >= p.skills[heal_idx].cost:
            state.start_skill(heal_idx)
            return
        for i, it in enumerate(p.inventory):
            if it.kind == "potion" and it.effect not in ("strength", "regen"):
                if state.player_use(i):
                    return

    # 2) 换上更好的装备
    for i, it in enumerate(list(p.inventory)):
        if it.kind == "weapon" and (p.weapon is None or it.atk > p.weapon.atk):
            if state.player_use(i):
                return
        if it.kind == "armor" and (p.armor is None or it.defense > p.armor.defense):
            if state.player_use(i):
                return

    # 3) 有敌人正好在同一线上：远程/范围技能先手
    attack_skill = _skill_index(p, "bolt")
    if attack_skill is None:
        attack_skill = _skill_index(p, "aoe")
    if attack_skill is not None:
        skill = p.skills[attack_skill]
        if p.mp >= skill.cost:
            for m in state.monsters:
                if not m.alive:
                    continue
                direction = _aligned_dir(p, m, skill.range)
                if direction:
                    state.start_skill(attack_skill)
                    state.resolve_skill(*direction)
                    return

    # 4) 相邻有敌人：直接攻击
    for dx, dy in NEIGHBORS:
        if state.monster_at(p.x + dx, p.y + dy):
            state.player_move(dx, dy)
            return

    # 5) 站在楼梯上且未到最深层：下楼
    if p.pos == state.stairs and state.floor < state.max_floor:
        state.player_descend()
        return

    # 6) 脚下有物品：拾取
    if p.pos in state.items:
        state.player_pickup()
        return

    # 7) 选择目标并沿最短路径靠近
    if state.floor < state.max_floor:
        goal = state.stairs
    else:
        boss = next((m for m in state.monsters if m.name == BOSS_NAME), None)
        goal = boss.pos if boss else None

    if goal is None:
        state.player_wait()
        return

    path = astar(state.dungeon.width, state.dungeon.height, p.pos, goal,
                 state.dungeon.is_walkable, max_expansions=8000)
    if path and len(path) > 1:
        nx, ny = path[1]
        state.player_move(nx - p.x, ny - p.y)
    else:
        state.player_wait()


def run(seed, turns, verbose=False, player_class="warrior"):
    """自动游玩最多 turns 回合，并打印结果摘要。"""
    state = GameState(seed=seed, player_class=player_class)
    for _ in range(turns):
        if state.game_over or state.victory:
            break
        _auto_step(state)

    if state.victory:
        result = "胜利：击败了远古巨龙"
    elif state.game_over:
        result = "阵亡"
    else:
        result = "未结束（回合数用尽）"

    print("=== 模拟结束 ===")
    print(f"职业: {state.player.name}   层数: {state.floor}/{state.max_floor}   "
          f"回合: {state.turns}   等级: {state.player.level}   "
          f"生命: {max(0, state.player.hp)}/{state.player.max_hp}   金币: {state.player.gold}")
    print(f"结果: {result}")
    if verbose:
        print(render(state, use_color=False))
    return state
