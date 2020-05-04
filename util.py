from sortedcontainers import SortedSet


_COLLISION_PENALTY = 1000
_CROSS_PENALTY = 100
_TURN_PENALTY = 10


# A-star grid pathfinding algorithm with Manhattan distance heuristics.
# Terminates if the cost passes the threshold.
# Currently not used, but might be useful later for
# wire pathfinding.
def pathfind(start, goal, collide_check_func):
    if collide_check_func(*goal) or collide_check_func(*start):
        return None

    q = SortedSet()

    def _heuristic(x1, y1, x2, y2):
        return (abs(x1 - x2) + abs(y1 - y2)) ** 2

    max_h = _heuristic(*start, *goal)

    q.add((max_h, start))
    visited = set()
    curr_cost = dict()
    curr_cost[start] = (0, max_h)
    backtrace = dict()
    found = False
    while q:
        cost, point = q.pop(0)
        visited.add(point)

        if point == goal:
            found = True
            break

        for dir in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            npoint = (point[0] + dir[0], point[1] + dir[1])
            if collide_check_func(npoint[0], npoint[1]):
                continue
            if npoint in visited:
                continue
            h = _heuristic(*npoint, *goal)
            ncost = h + cost + 1
            if npoint not in curr_cost or ncost < sum(curr_cost[npoint]):
                if npoint in curr_cost:
                    q.remove((sum(curr_cost[npoint]), npoint))
                q.add((ncost, npoint))
                curr_cost[npoint] = (cost + 1, h)
                backtrace[npoint] = point

    if not found:
        return None

    l = [goal]
    while l[-1] != start:
        curr = backtrace[l[-1]]
        l.append(curr)

    l.reverse()

    return l
