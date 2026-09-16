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


def facility_building(conn, facility_id):
    """The building a facility sits in (id/name/pos_x/pos_y), for map placement."""
    return conn.execute(
        text(
            "SELECT b.id, b.name, b.pos_x, b.pos_y FROM facilities fac "
            "JOIN floors fl ON fl.id = fac.floor_id "
            "JOIN buildings b ON b.id = fl.building_id "
            "WHERE fac.id = :id"
        ),
        {"id": facility_id},
    ).mappings().first()


def elbow_points(x1, y1, x2, y2):
    """A right-angle "follows the road grid" bend between two map points instead
    of a diagonal straight line cutting across buildings — routes along the
    longer axis first, then turns 90°, echoing how a site map's roads tend to
    run mostly horizontal/vertical."""
    if x1 == x2 or y1 == y2:
        return [(x1, y1), (x2, y2)]
    if abs(x2 - x1) >= abs(y2 - y1):
        return [(x1, y1), (x2, y1), (x2, y2)]
    return [(x1, y1), (x1, y2), (x2, y2)]


ROUTE_HOP_PALETTE = ["#FB8520", "#2f6feb", "#2e7d32", "#8e44ad", "#c0392b", "#00897b"]


def build_day_route(conn, worksite_id, items):
    """Ordered map stops + inter-stop hops (mode/points/travel time) for the
    subset of a day's schedule items (from schedules.get_day_items) that have a
    facility. Shared by the dedicated day-route map page and the inline "동선"
    section on the day view — kept here (not in a blueprint) so both
    blueprints/mapview.py and blueprints/schedules.py can use it without
    importing from each other."""
    located = [it for it in items if it["schedule"]["facility_id"]]

    stops = []
    for idx, it in enumerate(located):
        b = facility_building(conn, it["schedule"]["facility_id"])
        stops.append(
            {
                "order": idx + 1,
                "pos_x": b["pos_x"],
                "pos_y": b["pos_y"],
                "label": it["facility_label"] or b["name"],
                "start_time": it["start_time"],
            }
        )

    hops = []
    for i in range(len(located) - 1):
        a_item, b_item = located[i], located[i + 1]
        a_fac = a_item["schedule"]["facility_id"]
        b_fac = b_item["schedule"]["facility_id"]
        a_b = facility_building(conn, a_fac)
        b_b = facility_building(conn, b_fac)

        travel, path = travel_minutes_between_facilities(conn, worksite_id, a_fac, b_fac)
        is_shuttle = bool(path) and any(mode == "shuttle" for _n, mode, _m in path)
        same_building = a_b["id"] == b_b["id"]

        points = elbow_points(a_b["pos_x"], a_b["pos_y"], b_b["pos_x"], b_b["pos_y"])

        hops.append(
            {
                "order": i + 1,
                "mode": "shuttle" if is_shuttle else ("same" if same_building else "walk"),
                "color": ROUTE_HOP_PALETTE[i % len(ROUTE_HOP_PALETTE)],
                "points": " ".join(f"{x},{y}" for x, y in points),
                "travel_minutes": travel,
                "from_label": a_item["facility_label"],
                "to_label": b_item["facility_label"],
            }
        )

    return stops, hops
