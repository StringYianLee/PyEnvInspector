"""强连通分量(SCC)检测 —— 迭代版 Tarjan 算法。

用于识别循环依赖:依赖图中成员数 > 1 的强连通分量即为一个循环依赖组,
单节点自环也视为循环。
采用迭代实现以避免深图递归爆栈。
"""

from __future__ import annotations

from collections import defaultdict
from typing import Iterable


def strongly_connected_components(
    nodes: Iterable[str], adj: dict[str, list[str]]
) -> list[list[str]]:
    """计算有向图的强连通分量。

    :param nodes: 全部节点(即使无边也要出现)
    :param adj:   邻接表 {node: [后继...]}
    :return:      SCC 列表, 每个分量是节点列表
    """
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    on_stack: set[str] = set()
    stack: list[str] = []
    result: list[list[str]] = []
    counter = 0

    for root in nodes:
        if root in index:
            continue
        # (节点, 其后继迭代器)
        work: list[tuple[str, object]] = [(root, iter(adj.get(root, ())))]
        index[root] = low[root] = counter
        counter += 1
        stack.append(root)
        on_stack.add(root)

        while work:
            node, it = work[-1]
            advanced = False
            for nxt in it:  # type: ignore[union-attr]
                if nxt not in index:
                    index[nxt] = low[nxt] = counter
                    counter += 1
                    stack.append(nxt)
                    on_stack.add(nxt)
                    work.append((nxt, iter(adj.get(nxt, ()))))
                    advanced = True
                    break
                if nxt in on_stack:
                    low[node] = min(low[node], index[nxt])
            if advanced:
                continue
            # 当前节点后继耗尽, 回溯
            work.pop()
            if work:
                parent = work[-1][0]
                low[parent] = min(low[parent], low[node])
            if low[node] == index[node]:
                comp: list[str] = []
                while True:
                    w = stack.pop()
                    on_stack.discard(w)
                    comp.append(w)
                    if w == node:
                        break
                result.append(comp)
    return result


def find_cycles(
    packages: dict, edges: list
) -> list[list[str]]:
    """从包依赖图中找出循环依赖组(成员数 > 1 的 SCC, 以及自环)。"""
    adj: dict[str, list[str]] = defaultdict(list)
    for e in edges:
        adj[e.source_key].append(e.target_key)

    comps = strongly_connected_components(list(packages.keys()), adj)
    cycles: list[list[str]] = []
    for comp in comps:
        if len(comp) > 1:
            cycles.append(sorted(comp))
        elif comp[0] in adj.get(comp[0], []):
            cycles.append(comp)  # 自环
    cycles.sort(key=lambda c: (-len(c), c))
    return cycles
