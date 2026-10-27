"""图布局引擎。

提供两种布局:

1. ``hierarchical_layout`` 分层布局(默认):
   先用 Tarjan SCC 把循环依赖折叠成组, 在凝聚图上做最长路径分层,
   同层节点水平居中排列, 层间自上而下 —— 依赖方向清晰, 毫秒级完成。
2. ``force_layout`` 力导向布局(Fruchterman-Reingold):
   斥力 + 引力迭代, 适合观察聚簇结构; 节点多时自动启用空间网格加速,
   建议在后台线程运行。
"""

from __future__ import annotations

import math
import random
from collections import defaultdict, deque

from .models import DepEdge, PackageInfo
from .scc import strongly_connected_components


def _active_adjacency(packages: dict[str, PackageInfo], edges: list[DepEdge]):
    adj: dict[str, list[str]] = {k: [] for k in packages}
    for e in edges:
        if e.source_key in adj and e.target_key in adj:
            adj[e.source_key].append(e.target_key)
    return adj


def estimate_node_width(name: str) -> float:
    """估算 UI 节点卡片宽度(与 graph_view.NodeItem 的字体度量近似)。

    布局层不依赖字体引擎, 用字符数线性近似;
    超长名截断到 240(与 UI 端省略号截断一致)。
    """
    return min(max(104.0, len(name) * 7.6 + 28.0), 240.0)


def hierarchical_layout(
    packages: dict[str, PackageInfo],
    edges: list[DepEdge],
    gap_x: float = 34.0,
    min_spacing_y: float = 150.0,
    max_spacing_y: float = 185.0,
) -> dict[str, tuple[float, float]]:
    """分层布局: 依赖方在上, 被依赖方在下; 循环组同层相邻。

    自适应间距:
    - 同层间距按每个节点的估算宽度排布(累积宽度 + 固定间隙),
      长名节点不再重叠, 短名节点不浪费空间;
    - 层间垂直距离随最宽层温和自适应(上限收敛, 保证整图高度
      不会被撑爆导致 fit 后缩得过小)。
    """
    if not packages:
        return {}
    adj = _active_adjacency(packages, edges)

    comps = strongly_connected_components(list(packages.keys()), adj)
    comp_of: dict[str, int] = {}
    for ci, comp in enumerate(comps):
        for n in comp:
            comp_of[n] = ci

    # 凝聚图(组为节点)上的 DAG 与最长路径分层
    dag_out: dict[int, set[int]] = defaultdict(set)
    indeg: dict[int, int] = defaultdict(int)
    for src, tgts in adj.items():
        for t in tgts:
            a, b = comp_of[src], comp_of[t]
            if a != b and b not in dag_out[a]:
                dag_out[a].add(b)
                indeg[b] += 1

    level = [0] * len(comps)
    queue = deque(ci for ci in range(len(comps)) if indeg[ci] == 0)
    visited = 0
    while queue:
        ci = queue.popleft()
        visited += 1
        for nxt in dag_out[ci]:
            level[nxt] = max(level[nxt], level[ci] + 1)
            indeg[nxt] -= 1
            if indeg[nxt] == 0:
                queue.append(nxt)
    # SCC 保证凝聚图无环; 兜底: 未访问的组层级置 0
    if visited != len(comps):
        for ci in range(len(comps)):
            if indeg[ci] > 0:
                level[ci] = 0

    def degree(n: str) -> int:
        p = packages[n]
        return len(p.outgoing) + len(p.incoming)

    levels: dict[int, list[str]] = defaultdict(list)
    for ci, comp in enumerate(comps):
        members = sorted(comp, key=lambda n: (-degree(n), n))
        levels[level[ci]].extend(members)

    # 层间垂直距离: 随最宽层温和自适应(上限收敛, 避免整图过高)
    max_layer_width = max(
        (sum(estimate_node_width(n) for n in members)
         + gap_x * max(len(members) - 1, 0))
        for members in levels.values()
    ) if levels else 0.0
    spacing_y = min(max(max_layer_width * 0.15 + 80.0, min_spacing_y),
                    max_spacing_y)

    pos: dict[str, tuple[float, float]] = {}
    for lv in sorted(levels):
        members = levels[lv]
        widths = [estimate_node_width(n) for n in members]
        total_w = sum(widths) + gap_x * max(len(members) - 1, 0)
        # 整层水平居中, 按累积宽度逐个定位(左上角语义)
        cursor = -total_w / 2.0
        for w, n in zip(widths, members):
            pos[n] = (cursor, lv * spacing_y)
            cursor += w + gap_x
    return pos


def force_layout(
    packages: dict[str, PackageInfo],
    edges: list[DepEdge],
    width: float = 1500.0,
    height: float = 850.0,
    iterations: int = 0,   # 0 = 按节点数自适应
    seed: int = 7,
) -> dict[str, tuple[float, float]]:
    """力导向布局(FR 算法)。节点 > 120 时启用网格斥力加速。

    自适应: 理想边长 k 乘以 1.15 松弛系数(节点更舒展),
    迭代次数按规模缩放(小图精修, 大图提速);
    画布 1500x850 宽扁比例, 与典型分析页视口匹配, 减少留白。
    """
    nodes = [k for k, p in packages.items()]
    n = len(nodes)
    if n == 0:
        return {}
    if n == 1:
        return {nodes[0]: (width / 2, height / 2)}
    if iterations <= 0:
        iterations = 170 if n <= 120 else 130

    rng = random.Random(seed)
    pos = {k: (rng.uniform(0, width), rng.uniform(0, height)) for k in nodes}
    edge_pairs = [
        (e.source_key, e.target_key)
        for e in edges
        if e.source_key in pos and e.target_key in pos
    ]

    # 理想边长: FR 经典值乘松弛系数, 减少节点视觉拥挤
    k = 1.15 * math.sqrt((width * height) / max(n, 1))
    temp = width / 8.0
    use_grid = n > 120

    for _ in range(iterations):
        disp: dict[str, list[float]] = {a: [0.0, 0.0] for a in nodes}

        # ---- 斥力 ----
        if use_grid:
            cell = max(k * 2.0, 40.0)
            grid: dict[tuple[int, int], list[str]] = defaultdict(list)
            for a in nodes:
                gx = int(pos[a][0] // cell)
                gy = int(pos[a][1] // cell)
                grid[(gx, gy)].append(a)
            for a in nodes:
                ax, ay = pos[a]
                gx, gy = int(ax // cell), int(ay // cell)
                for dx in (-1, 0, 1):
                    for dy in (-1, 0, 1):
                        for b in grid.get((gx + dx, gy + dy), ()):
                            _repel(a, b, pos, disp, k)
        else:
            for i in range(n):
                for j in range(i + 1, n):
                    a, b = nodes[i], nodes[j]
                    _repel(a, b, pos, disp, k, symmetric=True)

        # ---- 引力 ----
        for s, t in edge_pairs:
            sx, sy = pos[s]
            tx, ty = pos[t]
            ddx, ddy = tx - sx, ty - sy
            dist = max(math.hypot(ddx, ddy), 1e-3)
            force = (dist * dist) / k
            fx, fy = force * ddx / dist, force * ddy / dist
            disp[s][0] += fx
            disp[s][1] += fy
            disp[t][0] -= fx
            disp[t][1] -= fy

        # ---- 限温位移 + 边界 ----
        for a in nodes:
            dx, dy = disp[a]
            d = max(math.hypot(dx, dy), 1e-3)
            step = min(d, temp)
            nx = min(max(pos[a][0] + dx / d * step, 24.0), width - 24.0)
            ny = min(max(pos[a][1] + dy / d * step, 24.0), height - 24.0)
            pos[a] = (nx, ny)
        temp = max(temp * 0.93, 1.0)
    return pos


def _repel(a: str, b: str, pos, disp, k: float, symmetric: bool = False) -> None:
    if a == b:
        return
    ax, ay = pos[a]
    bx, by = pos[b]
    ddx, ddy = ax - bx, ay - by
    dist2 = ddx * ddx + ddy * ddy
    if dist2 < 1e-9:
        ddx, ddy = 0.5, 0.5
        dist2 = 0.5
    dist = math.sqrt(dist2)
    # FR 经典斥力: k²/d (沿单位方向) —— 与引力 d²/k 对称, 平衡距离恰为 k
    force = (k * k) / dist
    fx, fy = force * ddx / dist, force * ddy / dist
    disp[a][0] += fx
    disp[a][1] += fy
    if symmetric:
        disp[b][0] -= fx
        disp[b][1] -= fy
