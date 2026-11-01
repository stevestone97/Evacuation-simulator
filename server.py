from __future__ import annotations

import csv
import heapq
import io
import json
import math
import os
import shutil
import subprocess
import threading
import time
from collections import defaultdict, deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
GRAPH = json.loads((ROOT / 'graph.json').read_text(encoding='utf-8'))
NODES = {n['id']: n for n in GRAPH['nodes']} 
EDGES = GRAPH['edges']
ROOMS = sorted(
    (node for node in NODES if node.startswith('K')),
    key=lambda node: int(node[1:]),
)
EXITS = ('U1', 'U2')
EDGE_INDEX = {edge['id']: edge for edge in EDGES}
ADJ_EDGES = defaultdict(list)
for edge in EDGES:
    ADJ_EDGES[edge['a']].append(edge)
    ADJ_EDGES[edge['b']].append(edge)


def edge_key(a, b):
    return next(
        (
            edge['id']
            for edge in ADJ_EDGES.get(a, [])
            if b in (edge['a'], edge['b'])
        ),
        None,
    )


def clamp(v, lo, hi):
    return min(hi, max(lo, v))


class CRouter:
    def __init__(self, stem, env_var=None):
        self.source = ROOT / 'c_algorithm' / f'{stem}.c'
        self.env_var = env_var

        default_executable = (
            f'{stem}.exe' if os.name == 'nt' else stem
        )

        override = os.environ.get(env_var) if env_var else None

        self.executable = Path(
            override or ROOT / 'c_algorithm' / default_executable
        )
        
    def available(self):
        compiler_available = shutil.which('gcc') or shutil.which('clang')
        return self.executable.exists() or bool(compiler_available)

    def compile(self):
        executable_is_current = (
            self.executable.exists()
            and (
                (self.env_var and os.environ.get(self.env_var))
                or self.executable.stat().st_mtime >= self.source.stat().st_mtime
            )
        )
        if executable_is_current:
            return

        cc = shutil.which('gcc') or shutil.which('clang')
        if not cc:
            raise ValueError(
                'GCC/Clang not found. Use Python Dijkstra for now, '
                'or install GCC to test C.'
            )

        command = [
            cc,
            '-O2',
            '-std=c11',
            str(self.source),
            '-o',
            str(self.executable),
        ]
        result = subprocess.run(
            command,
            text=True,
            capture_output=True,
            timeout=30,
        )
        if result.returncode:
            raise ValueError('C build failed: ' + result.stderr[-600:])

    def route(self, adj, start, avoid):
        self.compile()
        arcs = [
            (node, neighbor, weight)
            for node, neighbors in adj.items()
            for neighbor, weight in neighbors
        ]
        data = ['EVAC1', f'{len(NODES)} {len(arcs)} {len(EXITS)}']
        data += list(NODES)
        data += list(EXITS)
        data += [f'{source} {target} {weight:.9f}' for source, target, weight in arcs]
        data += [f'{start} {avoid or "_"}']

        try:
            reply = subprocess.run(
                [str(self.executable)],
                input='\n'.join(data) + '\n',
                text=True,
                capture_output=True,
                timeout=2,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ValueError('C routing execution failed: ' + str(exc)) from exc

        if reply.returncode:
            raise ValueError('C routing error: ' + reply.stderr[-400:])

        try:
            out = json.loads(reply.stdout)
        except json.JSONDecodeError as exc:
            raise ValueError('C returned invalid JSON') from exc

        path = out.get('path', [])
        if not isinstance(path, list) or (
            path and (path[0] != start or path[-1] not in EXITS)
        ):
            raise ValueError('C returned an invalid route')

        neighbors_by_node = {
            node: {neighbor for neighbor, _ in neighbors}
            for node, neighbors in adj.items()
        }
        if any(
            target not in neighbors_by_node.get(source, set())
            for source, target in zip(path, path[1:])
        ):
            raise ValueError('C returned an edge not in the graph')
        if avoid and len(path) > 1 and path[1] == avoid:
            raise ValueError('C ignored the forbidden first step')
        return (
            path,
            out.get('cost'),
            int(out.get('visited', 0)),
            int(out.get('relaxations', 0)),
        )



#ADD NEW EXECUTABLES HERE, AND UPDATE THE C_ROUTERS DICTIONARY BELOW
C_ROUTERS = {
    'c_test': CRouter(
        'test_routing',
        env_var='EVAC_C_EXECUTABLE'
    ),
}


def dijkstra(adj, start):
    queue = [(0.0, start)]
    distances = {start: 0.0}
    parents = {}
    visited = 0
    relaxations = 0

    while queue:
        distance, node = heapq.heappop(queue)
        if distance > distances[node] + 1e-9:
            continue

        visited += 1
        if node in EXITS:
            path = [node]
            while path[-1] != start:
                path.append(parents[path[-1]])
            return list(reversed(path)), distance, visited, relaxations

        for neighbor, weight in adj[node]:
            relaxations += 1
            new_distance = distance + weight
            if new_distance < distances.get(neighbor, math.inf) - 1e-9:
                distances[neighbor] = new_distance
                parents[neighbor] = node
                heapq.heappush(queue, (new_distance, neighbor))

    return [], None, visited, relaxations


def bidirectional_one(adj, source, goal):
    if source == goal:
        return [source], 0, 0, 0

    reverse = {node: [] for node in adj}
    for node, neighbors in adj.items():
        for neighbor, weight in neighbors:
            reverse[neighbor].append((node, weight))

    forward_distances = {source: 0.0}
    backward_distances = {goal: 0.0}
    forward_parents = {}
    backward_parents = {}
    forward_queue = [(0.0, source)]
    backward_queue = [(0.0, goal)]
    best_cost = math.inf
    meeting_node = None
    visited = 0
    relaxations = 0

    while forward_queue and backward_queue:
        while (
            forward_queue
            and forward_queue[0][0]
            > forward_distances.get(forward_queue[0][1], math.inf) + 1e-9
        ):
            heapq.heappop(forward_queue)
        while (
            backward_queue
            and backward_queue[0][0]
            > backward_distances.get(backward_queue[0][1], math.inf) + 1e-9
        ):
            heapq.heappop(backward_queue)

        if (
            not forward_queue
            or not backward_queue
            or forward_queue[0][0] + backward_queue[0][0] >= best_cost - 1e-9
        ):
            break

        search_forward = forward_queue[0][0] <= backward_queue[0][0]
        if search_forward:
            queue = forward_queue
            distances = forward_distances
            other_distances = backward_distances
            network = adj
            parents = forward_parents
        else:
            queue = backward_queue
            distances = backward_distances
            other_distances = forward_distances
            network = reverse
            parents = backward_parents

        cost, node = heapq.heappop(queue)
        visited += 1

        if node in other_distances and cost + other_distances[node] < best_cost:
            best_cost = cost + other_distances[node]
            meeting_node = node

        for neighbor, weight in network[node]:
            relaxations += 1
            new_cost = cost + weight
            if new_cost < distances.get(neighbor, math.inf) - 1e-9:
                distances[neighbor] = new_cost
                parents[neighbor] = node
                heapq.heappush(queue, (new_cost, neighbor))

            if (
                neighbor in other_distances
                and distances.get(neighbor, math.inf) + other_distances[neighbor]
                < best_cost
            ):
                best_cost = distances[neighbor] + other_distances[neighbor]
                meeting_node = neighbor

    if meeting_node is None:
        return [], None, visited, relaxations

    left_path = [meeting_node]
    while left_path[-1] != source:
        left_path.append(forward_parents[left_path[-1]])
    left_path.reverse()

    right_path = []
    node = meeting_node
    while node != goal:
        node = backward_parents[node]
        right_path.append(node)

    return left_path + right_path, best_cost, visited, relaxations


def bidirectional(adj, start):
    outcomes = [bidirectional_one(adj, start, exit_node) for exit_node in EXITS]
    path, cost, _, _ = min(
        outcomes,
        key=lambda outcome: math.inf if outcome[1] is None else outcome[1],
    )
    return (
        path,
        cost,
        sum(outcome[2] for outcome in outcomes),
        sum(outcome[3] for outcome in outcomes),
    )


def initial_config():
    return {
        'population': {
            'K1': 10,
            'K2': 10,
            'K3': 10,
            'K4': 10,
            'K5': 10,
            'K6': 10,
        },
        'speed': 1.2,
        'corridor_flow': 2.0,
        'exit_capacity': 1.0,
        'lengths': {},
    }

class Simulation:
    def __init__(self):
        self.lock = threading.RLock()
        self.config = initial_config()
        self.algorithm = 'dijkstra'
        self.completed = []
        self.reset()

    def length(self, edge):
        return self.config['lengths'].get(edge['id'],edge['length'])

    def reset(self):
        with self.lock:
            self.t = 0.0
            self.blocked = set()
            self.route_calls = 0
            self.explored = 0
            self.relaxations = 0
            self.routing_ms = 0.0
            self.max_routing_ms = 0.0
            self.reroutes = 0
            self.exit_counts = {exit_node: 0 for exit_node in EXITS}
            self.exit_queues = {exit_node: deque() for exit_node in EXITS}
            self.exit_credit = {exit_node: 0.0 for exit_node in EXITS}
            self.edge_credit = {edge['id']: 0.0 for edge in EDGES}
            self.max_exit_queue = 0
            self.events = []
            self.run_recorded = False
            self.students = []

            for room in ROOMS:
                for _ in range(self.config['population'][room]):
                    self.students.append({
                        'id': len(self.students),
                        'origin': room,
                        'node': room,
                        'state': 'waiting',
                        'src': None,
                        'dst': None,
                        'progress': 0.0,
                        'previous': None,
                        'candidate': None,
                        'desired': None,
                        'planned_path': None,
                        'in_class_group': True,
                        'distance': 0.0,
                        'exit_time': None,
                        'route_history': [],
                    })

            self.route_cache = {}
            self.initial_group_routes = {}
            self.group_plans_locked = False
            self._route_signature = None

    def queues(self):
        waiting = defaultdict(int)
        incoming = defaultdict(int)
        for student in self.students:
            if student['state'] == 'waiting' and student['desired']:
                waiting[(student['node'], student['desired'])] += 1
            if student['state'] == 'moving' and student['dst'] in EXITS:
                incoming[student['dst']] += 1
        return waiting, incoming

    def adjacency(self):
        waiting, incoming = self.queues()
        adjacency = {node: [] for node in NODES}
        for edge in EDGES:
            node_a, node_b = edge['a'], edge['b']
            if edge['id'] in self.blocked:
                continue

            base_cost = self.length(edge) / self.config['speed']
            for source, target in ((node_a, node_b), (node_b, node_a)):
                if source in EXITS:
                    continue

                cost = (
                    base_cost
                    + waiting[(source, target)] / self.config['corridor_flow']
                )
                if target in EXITS:
                    exit_queue_size = len(self.exit_queues[target])
                    cost += (
                        exit_queue_size + incoming[target] + 1
                    ) / self.config['exit_capacity']
                adjacency[source].append((target, cost))

        return adjacency

    def route(self, start, avoid=None, count=True, network=None):
        if start in EXITS:
            return [start], 0.0

        adjacency = network if network is not None else self.adjacency()
        cache_key = (self.algorithm, start, avoid)
        if cache_key in self.route_cache:
            return self.route_cache[cache_key]

        search_adjacency = adjacency
        if avoid:
            search_adjacency = dict(adjacency)
            search_adjacency[start] = [
                (neighbor, weight)
                for neighbor, weight in adjacency[start]
                if neighbor != avoid
            ]

        started_at = time.perf_counter_ns()
        
        if self.algorithm in C_ROUTERS:
            path, cost, visited, relaxations = (
                C_ROUTERS[self.algorithm].route(
                    search_adjacency, start, avoid
                )
            )
        elif self.algorithm == 'bidirectional':
            path, cost, visited, relaxations = bidirectional(
                search_adjacency, start
            )
        else:
            path, cost, visited, relaxations = dijkstra(search_adjacency, start)

        elapsed_ms = (time.perf_counter_ns() - started_at) / 1_000_000
        if count:
            self.route_calls += 1
            self.explored += visited
            self.relaxations += relaxations
            self.routing_ms += elapsed_ms
            self.max_routing_ms = max(self.max_routing_ms, elapsed_ms)

        result = (path, cost)
        self.route_cache[cache_key] = result
        return result

    def assign_initial_group_routes(self, network):
        if self.group_plans_locked:
            return

        for room in ROOMS:
            path, _ = self.route(room, network=network)
            self.initial_group_routes[room] = list(path)

        self.group_plans_locked = True
        self.events.append(f'{self.t:.1f}s — classroom groups received initial routes')

    def choose(self, student, adjacency):
        node = student['node']
        if student['in_class_group'] and node in ROOMS:
            initial = self.initial_group_routes.get(student['origin'], [])
            if node in initial:
                segment = initial[initial.index(node):]
                if len(segment) > 1 and edge_key(node, segment[1]) not in self.blocked:
                    return segment

        avoid = student['previous']
        path, _ = self.route(node, avoid, network=adjacency)
        if len(path) < 2 and avoid:
            path, _ = self.route(node, network=adjacency)
        return path

    def step(self,dt=0.2):
        with self.lock:
            if self.run_recorded:
                return

            dt = clamp(float(dt), 0.02, 0.25)
            self.t += dt
            self.route_cache = {}
            corridor_flow = self.config['corridor_flow']

            for edge in EDGES:
                edge_id = edge['id']
                self.edge_credit[edge_id] = min(
                    1.0,
                    self.edge_credit[edge_id] + corridor_flow * dt,
                )

            for student in self.students:
                if student['state'] != 'moving':
                    continue

                edge_id = edge_key(student['src'], student['dst'])
                edge = EDGE_INDEX[edge_id]
                student['progress'] += (
                    self.config['speed'] * dt / self.length(edge)
                )

                if student['progress'] >= 1:
                    student['distance'] += self.length(edge)
                    student['previous'] = student['src']
                    student['node'] = student['dst']
                    if NODES[student['node']]['type'] == 'sign':
                        student['in_class_group'] = False

                    old_path = student.get('planned_path')
                    if old_path and student['node'] in old_path:
                        student['planned_path'] = old_path[
                            old_path.index(student['node']):]

                    student['src'] = None
                    student['dst'] = None
                    student['progress'] = 0.0
                    if student['node'] in EXITS:
                        student['state'] = 'exit_queue'
                        self.exit_queues[student['node']].append(student['id'])
                    else:
                        student['state'] = 'waiting'

            self.max_exit_queue = max(
                self.max_exit_queue,
                *(len(queue) for queue in self.exit_queues.values()),
            )
            for exit_node in EXITS:
                self.exit_credit[exit_node] += self.config['exit_capacity'] * dt
                while (
                    self.exit_credit[exit_node] >= 1
                    and self.exit_queues[exit_node]
                ):
                    student = self.students[
                        self.exit_queues[exit_node].popleft()
                    ]
                    student['state'] = 'evacuated'
                    student['exit_time'] = self.t
                    self.exit_counts[exit_node] += 1
                    self.exit_credit[exit_node] -= 1
                self.exit_credit[exit_node] = min(
                    1.0,
                    self.exit_credit[exit_node],
                )

            self.max_exit_queue = max(
                self.max_exit_queue,
                *(len(queue) for queue in self.exit_queues.values()),
            )
            network = self.adjacency()
            self.assign_initial_group_routes(network)

            for student in self.students:
                if student['state'] != 'waiting':
                    continue
                path = self.choose(student, network)
                student['candidate'] = path
                student['desired'] = path[1] if len(path) >= 2 else None

            ready = [
                student
                for student in self.students
                if student['state'] == 'waiting' and student['desired']
            ]
            ready.sort(
                key=lambda student: (
                    student['id'] * 17 + int(self.t / dt) * 13
                ) % max(1, len(self.students))
            )
            for student in ready:
                destination = student['desired']
                edge_id = edge_key(student['node'], destination)
                if edge_id in self.blocked or self.edge_credit[edge_id] < 1:
                    continue

                previous_path = student['planned_path']
                proposed_path = student['candidate']
                if (
                    previous_path
                    and proposed_path
                    and previous_path[0] == student['node']
                    and previous_path != proposed_path
                ):
                    self.reroutes += 1

                student['planned_path'] = (
                    list(proposed_path) if proposed_path else None
                )
                student['route_history'].append(destination)
                self.edge_credit[edge_id] -= 1
                student['src'] = student['node']
                student['dst'] = destination
                student['state'] = 'moving'
                student['progress'] = 0.0
                student['desired'] = None

            for student in self.students:
                planned_path = student['planned_path']
                if (
                    student['state'] == 'waiting'
                    and planned_path
                    and student['node'] in planned_path
                ):
                    path_index = planned_path.index(student['node'])
                    student['planned_path'] = planned_path[path_index:]

            if not self.students or all(
                student['state'] == 'evacuated' for student in self.students
            ):
                self.run_recorded = True
                self.completed.append(self.summary(completed=True))
                self.events.append(f'{self.t:.1f}s — evacuation complete')

    def summary(self, completed=False):
        evacuated = [
            student
            for student in self.students
            if student['state'] == 'evacuated'
        ]
        evacuated_count = len(evacuated)
        return {
            'algorithm': self.algorithm,
            'status': 'completed' if completed else 'in progress',
            'sim_time_s': round(self.t, 2),
            'total': len(self.students),
            'evacuated': evacuated_count,
            'route_decisions': self.route_calls,
            'routing_total_ms': round(self.routing_ms, 4),
            'routing_avg_ms': (
                round(self.routing_ms / self.route_calls, 5)
                if self.route_calls
                else None
            ),
            'routing_max_ms': (
                round(self.max_routing_ms, 5) if self.route_calls else None
            ),
            'nodes_explored': self.explored,
            'relaxations': self.relaxations,
            'mean_exit_time_s': (
                round(
                    sum(student['exit_time'] for student in evacuated)
                    / evacuated_count,
                    2,
                )
                if evacuated_count
                else None
            ),
            'max_exit_time_s': (
                round(max(student['exit_time'] for student in evacuated), 2)
                if evacuated_count
                else None
            ),
            'avg_walk_distance_m': (
                round(
                    sum(student['distance'] for student in evacuated)
                    / evacuated_count,
                    2,
                )
                if evacuated_count
                else None
            ),
            'max_exit_queue': self.max_exit_queue,
            'reroutes': self.reroutes,
            'classroom_group_routes': len(self.initial_group_routes),
            'blocked_edges': ';'.join(sorted(self.blocked)),
            'incident_log': '; '.join(self.events),
            'speed_mps': self.config['speed'],
            'corridor_flow_pps': self.config['corridor_flow'],
            'exit_capacity_pps': self.config['exit_capacity'],
            **{
                'population_' + room: self.config['population'][room]
                for room in ROOMS
            },
            **{
                'exit_' + exit_node: self.exit_counts[exit_node]
                for exit_node in EXITS
            },
        }

    def snapshot(self):
        with self.lock:
            waiting, _ = self.queues()
            self.route_cache = {}
            network = self.adjacency()
            routes = {}
            signs = {}

            for node in NODES:
                if node in EXITS:
                    continue
                path, cost = self.route(node, count=False, network=network)

                if node in ROOMS and self.group_plans_locked:
                    assigned_path = self.initial_group_routes.get(node, [])
                    if (
                        len(assigned_path) > 1
                        and edge_key(node, assigned_path[1]) not in self.blocked
                    ):
                        shown_next = assigned_path[1]
                    else:
                        shown_next = path[1] if len(path) > 1 else None
                    shown_source = (
                        'initial group'
                        if shown_next and shown_next in assigned_path[1:2]
                        else 'adaptive'
                    )
                else:
                    shown_next = path[1] if len(path) > 1 else None
                    shown_source = 'current route'

                signs[node] = {'next': shown_next, 'source': shown_source}
                if node in ROOMS:
                    routes[node] = {
                        'path': path,
                        'cost': round(cost, 2) if cost is not None else None,
                        'initial_path': self.initial_group_routes.get(node, []),
                    }

            edges = []
            for edge in EDGES:
                base_cost = self.length(edge) / self.config['speed']
                node_a, node_b = edge['a'], edge['b']
                active_count = sum(
                    1
                    for student in self.students
                    if student['state'] == 'moving'
                    and edge_key(student['src'], student['dst']) == edge['id']
                )
                edges.append({
                    **edge,
                    'length': round(self.length(edge), 2),
                    'blocked': edge['id'] in self.blocked,
                    'cost_ab': round(
                        base_cost
                        + waiting[(node_a, node_b)]
                        / self.config['corridor_flow'],
                        2,
                    ),
                    'cost_ba': round(
                        base_cost
                        + waiting[(node_b, node_a)]
                        / self.config['corridor_flow'],
                        2,
                    ),
                    'active': active_count,
                })

            metrics = self.summary(self.run_recorded)
            return {
                'time': round(self.t, 2),
                'complete': self.run_recorded,
                'algorithm': self.algorithm,
                'c_available': any(
                    router.available() for router in C_ROUTERS.values()
                ),
                'nodes': NODES,
                'edges': edges,
                'students': [
                    {
                        key: student[key]
                        for key in (
                            'id',
                            'origin',
                            'node',
                            'src',
                            'dst',
                            'state',
                            'progress',
                            'in_class_group',
                        )
                    }
                    for student in self.students
                    if student['state'] != 'evacuated'
                ],
                'routes': routes,
                'signs': signs,
                'initial_group_routes': self.initial_group_routes,
                'exit_counts': dict(self.exit_counts),
                'exit_queues': {
                    exit_node: len(self.exit_queues[exit_node])
                    for exit_node in EXITS
                },
                'metrics': metrics,
                'config': self.config,
                'history': self.completed[-8:],
                'events': self.events[-12:],
            }

    def set_config(self, config):
        with self.lock:
            previous_config = self.config
            population = {
                room: int(clamp(
                    int(
                        config.get('population', {}).get(
                            room,
                            previous_config['population'][room],
                        )
                    ),
                    0,
                    150,
                ))
                for room in ROOMS
            }

            lengths = {}
            for edge_id, value in config.get('lengths', {}).items():
                if edge_id in EDGE_INDEX and value not in (None, ''):
                    length = float(value)
                    if not math.isfinite(length):
                        raise ValueError('Distance must be finite')
                    lengths[edge_id] = clamp(length, 0.1, 500)

            speed = float(config.get('speed', previous_config['speed']))
            corridor_flow = float(
                config.get('corridor_flow', previous_config['corridor_flow'])
            )
            exit_capacity = float(
                config.get('exit_capacity', previous_config['exit_capacity'])
            )
            if not all(math.isfinite(value) for value in (
                speed,
                corridor_flow,
                exit_capacity,
            )):
                raise ValueError('Parameters must be finite')

            self.config = {
                'population': population,
                'speed': clamp(speed, 0.2, 3.0),
                'corridor_flow': clamp(corridor_flow, 0.2, 20.0),
                'exit_capacity': clamp(exit_capacity, 0.2, 20.0),
                'lengths': lengths,
            }
            self.reset()

    def toggle_edge(self, key):
        with self.lock:
            if key not in EDGE_INDEX:
                raise ValueError('Unknown connection')

            if key in self.blocked:
                self.blocked.remove(key)
                status = 'reopened'
            else:
                self.blocked.add(key)
                status = 'blocked'

            self.events.append(f'{self.t:.1f}s — {key} {status}')
            self.route_cache = {}

    def select_algorithm(self, name):
        if name not in ('dijkstra', 'bidirectional') and name not in C_ROUTERS:
            raise ValueError('Unknown routing algorithm')

        if name in C_ROUTERS:
            C_ROUTERS[name].compile()

        with self.lock:
            self.algorithm = name
            self.reset()

    def export_csv(self):
        with self.lock:
            rows = self.completed[:]
            if self.t > 0 and not self.run_recorded:
                rows.append(self.summary(False))

            output = io.StringIO()
            writer = csv.DictWriter(output, fieldnames=list(self.summary()))
            writer.writeheader()
            writer.writerows(rows)
            return output.getvalue().encode('utf-8-sig')


SIM = Simulation()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def send_bytes(self, code, value, mime='application/json'):
        if isinstance(value, bytes):
            body = value
        else:
            body = json.dumps(
                value,
                ensure_ascii=False,
                allow_nan=False,
            ).encode('utf-8')

        self.send_response(code)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control','no-store')
        if mime.startswith('text/csv'):
            self.send_header('Content-Disposition','attachment; filename="evacuation_results.csv"')
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path in ('/', '/index.html'):
            self.send_bytes(
                200,
                (ROOT / 'index.html').read_bytes(),
                'text/html; charset=utf-8',
            )
        elif self.path == '/assets/third_floor_clean.png':
            image_path = ROOT / 'assets' / 'third_floor_clean.png'
            self.send_bytes(200, image_path.read_bytes(), 'image/png')
        elif self.path == '/api/state':
            self.send_bytes(200, SIM.snapshot())
        elif self.path == '/api/export':
            self.send_bytes(
                200,
                SIM.export_csv(),
                'text/csv; charset=utf-8',
            )
        elif self.path == '/graph.json':
            self.send_bytes(200, GRAPH)
        else:
            self.send_bytes(404, {'error': 'Not found'})

    def do_POST(self):
        try:
            content_length = int(self.headers.get('Content-Length', '0'))
            if not 0 <= content_length <= 200000:
                raise ValueError('Request too large')

            body = (
                json.loads(self.rfile.read(content_length).decode('utf-8'))
                if content_length
                else {}
            )
            if self.path == '/api/step':
                step_count = int(clamp(int(body.get('steps', 1)), 1, 20))
                for _ in range(step_count):
                    SIM.step()
            elif self.path == '/api/reset':
                SIM.reset()
            elif self.path == '/api/config':
                SIM.set_config(body)
            elif self.path == '/api/algo':
                SIM.select_algorithm(body['algorithm'])
            elif self.path == '/api/block':
                SIM.toggle_edge(str(body['key']))
            else:
                return self.send_bytes(404, {'error': 'Not found'})

            self.send_bytes(200, SIM.snapshot())
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            self.send_bytes(400, {'error': str(exc)})
        except Exception as exc:
            self.send_bytes(500, {'error': 'Server error: ' + str(exc)})


if __name__ == '__main__':
    print('Third-floor Evacuation Simulator: http://127.0.0.1:8000')
    try:
        ThreadingHTTPServer(('127.0.0.1', 8000), Handler).serve_forever()
    except KeyboardInterrupt:
        print('\nStopped')
