"""Plain-algorithm travel-time graph over move_edges.

No AI here on purpose (see spec section 9's AI/algorithm split): this module only
does graph building and shortest-path arithmetic. Phase 3's route optimizer reuses
these same functions to score candidate schedule orderings.
"""
import heapq
from datetime import datetime, timedelta

from sqlalchemy import text


def build_graph(conn, worksite_id):
    """dict[(type, id)] -> list of ((type, id), minutes, mode) for the current worksite.

    Every facility gets an implicit 0-minute bidirectional edge to its own floor:
    being "at a facility" and "on that facility's floor" are the same location for
    travel-time purposes at this level of detail (Phase 1's seeded graph only has
    floor<->floor elevator edges and facility<->facility walk/shuttle edges, so
    without this a facility would otherwise have no way to reach the elevator or a
    shuttle stop on its own floor).
    """
    graph = {}

    def add_edge(a, b, minutes, mode):
        graph.setdefault(a, []).append((b, minutes, mode))

    facilities = conn.execute(
        text(
            "SELECT fac.id, fl.id AS floor_id FROM facilities fac "
            "JOIN floors fl ON fl.id = fac.floor_id "
            "JOIN buildings b ON b.id = fl.building_id "
            "WHERE b.worksite_id = :w AND fac.active"
        ),
        {"w": worksite_id},
    ).mappings().all()
    for fac in facilities:
        fac_node = ("facility", fac["id"])
        floor_node = ("floor", fac["floor_id"])
        add_edge(fac_node, floor_node, 0, "same_spot")
        add_edge(floor_node, fac_node, 0, "same_spot")

    edges = conn.execute(
        text(
            "SELECT from_node_type, from_node_id, to_node_type, to_node_id, mode, minutes, bidirectional "
            "FROM move_edges WHERE worksite_id = :w AND active"
        ),
        {"w": worksite_id},
    ).mappings().all()
    for e in edges:
        a = (e["from_node_type"], e["from_node_id"])
        b = (e["to_node_type"], e["to_node_id"])
        add_edge(a, b, e["minutes"], e["mode"])
        if e["bidirectional"]:
            add_edge(b, a, e["minutes"], e["mode"])

    return graph


def shortest_path(graph, from_node, to_node):
    """Dijkstra. Returns (total_minutes, [(node, mode, minutes), ...]) or (None, None)."""
    if from_node == to_node:
        return 0, []

    dist = {from_node: 0}
    prev = {}
    visited = set()
    heap = [(0, from_node)]

    while heap:
        d, node = heapq.heappop(heap)
        if node in visited:
            continue
        visited.add(node)
        if node == to_node:
            break
        for neighbor, minutes, mode in graph.get(node, []):
            nd = d + minutes
            if nd < dist.get(neighbor, float("inf")):
                dist[neighbor] = nd
                prev[neighbor] = (node, mode, minutes)
                heapq.heappush(heap, (nd, neighbor))

    if to_node not in dist:
        return None, None

    path = []
    cur = to_node
    while cur in prev:
        parent, mode, minutes = prev[cur]
        path.append((cur, mode, minutes))
        cur = parent
    path.reverse()
    return dist[to_node], path


def travel_minutes_between_facilities(conn, worksite_id, facility_id_a, facility_id_b):
    """Convenience wrapper for the schedules day view. Returns (minutes, path) or (None, None)."""
    if facility_id_a is None or facility_id_b is None:
        return None, None
    graph = build_graph(conn, worksite_id)
    return shortest_path(graph, ("facility", facility_id_a), ("facility", facility_id_b))


def next_shuttle_departure(operation_start, operation_end, interval_minutes, now=None):
    """Next scheduled departure time (HH:MM) for a shuttle route, or None if service
    has ended for the day. Plain timetable arithmetic, not AI."""
    now = now or datetime.now()
    try:
        start_t = datetime.strptime(operation_start, "%H:%M").time()
        end_t = datetime.strptime(operation_end, "%H:%M").time()
    except (ValueError, TypeError):
        return None

    if now.time() < start_t:
        return operation_start
    if now.time() > end_t:
        return None

    start_dt = datetime.combine(now.date(), start_t)
    end_dt = datetime.combine(now.date(), end_t)
    elapsed_minutes = (now - start_dt).total_seconds() / 60
    departures_passed = int(elapsed_minutes // interval_minutes) + 1
    next_dt = start_dt + timedelta(minutes=departures_passed * interval_minutes)

    if next_dt > end_dt:
        return None
    return next_dt.strftime("%H:%M")


def generate_timetable(operation_start, operation_end, interval_minutes):
    """Every scheduled departure time (HH:MM) across the route's operating day.
    Plain timetable arithmetic, same spirit as next_shuttle_departure above."""
    try:
        start_t = datetime.strptime(operation_start, "%H:%M")
        end_t = datetime.strptime(operation_end, "%H:%M")
    except (ValueError, TypeError):
        return []

    times = []
    cur = start_t
    while cur <= end_t:
        times.append(cur.strftime("%H:%M"))
        cur += timedelta(minutes=interval_minutes)
    return times
