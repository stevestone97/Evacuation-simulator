// Recompile with:
// gcc -O2 -std=c11 .\c_algorithm\test_routing.c -o .\c_algorithm\test_routing.exe

#include <float.h>
#include <stdio.h>
#include <string.h>

#define MAX_NODES 64
#define MAX_EDGES 512
#define ID_LENGTH 16

typedef struct {
    int from;
    int to;
    double weight;
} Edge;

char node_names[MAX_NODES][ID_LENGTH];
char exit_names[MAX_NODES][ID_LENGTH];
int node_count;
int edge_count;
int exit_count;
Edge edges[MAX_EDGES];

static int find_node(const char *node_name)
{
    for (int i = 0; i < node_count; i++) {
        if (strcmp(node_names[i], node_name) == 0) {
            return i;
        }
    }

    return -1;
}

int main(void)
{
    char magic[24];
    char first_node[ID_LENGTH];
    char second_node[ID_LENGTH];

    if (scanf("%23s", magic) != 1 || strcmp(magic, "EVAC1") != 0) {
        return 2;
    }

    if (scanf("%d%d%d", &node_count, &edge_count, &exit_count) != 3 ||
        node_count < 1 || node_count > MAX_NODES ||
        edge_count < 0 || edge_count > MAX_EDGES ||
        exit_count < 1 || exit_count > MAX_NODES) {
        return 3;
    }

    for (int i = 0; i < node_count; i++) {
        if (scanf("%15s", node_names[i]) != 1) {
            return 4;
        }
    }

    for (int i = 0; i < exit_count; i++) {
        if (scanf("%15s", exit_names[i]) != 1) {
            return 5;
        }
    }

    for (int i = 0; i < edge_count; i++) {
        double weight;

        if (scanf("%15s%15s%lf", first_node, second_node, &weight) != 3) {
            return 6;
        }

        edges[i].from = find_node(first_node);
        edges[i].to = find_node(second_node);
        edges[i].weight = weight;

        if (edges[i].from < 0 || edges[i].to < 0 ||
            weight < 0 || weight > 1e9) {
            return 7;
        }
    }

    char source_name[ID_LENGTH];
    char avoided_name[ID_LENGTH];

    if (scanf("%15s%15s", source_name, avoided_name) != 2) {
        return 8;
    }

    int start = find_node(source_name);
    int forbidden = find_node(avoided_name);

    if (start < 0) {
        return 9;
    }

    double distances[MAX_NODES];
    int previous[MAX_NODES];
    int visited[MAX_NODES];

    for (int i = 0; i < node_count; i++) {
        distances[i] = DBL_MAX;
        previous[i] = -1;
        visited[i] = 0;
    }

    distances[start] = 0;

    int explored_count = 0;
    int relaxation_count = 0;

    for (int iteration = 0; iteration < node_count; iteration++) {
        int current = -1;

        for (int i = 0; i < node_count; i++) {
            if (!visited[i] &&
                (current < 0 || distances[i] < distances[current])) {
                current = i;
            }
        }

        if (current < 0 || distances[current] == DBL_MAX) {
            break;
        }

        visited[current] = 1;
        explored_count++;

        for (int i = 0; i < edge_count; i++) {
            if (edges[i].from != current) {
                continue;
            }

            int neighbor = edges[i].to;

            if ((current == start && neighbor == forbidden) ||
                visited[neighbor]) {
                continue;
            }

            relaxation_count++;

            double candidate_distance =
                distances[current] + edges[i].weight;
            if (candidate_distance < distances[neighbor]) {
                distances[neighbor] = candidate_distance;
                previous[neighbor] = current;
            }
        }
    }

    int target = -1;

    for (int i = 0; i < exit_count; i++) {
        int exit_node = find_node(exit_names[i]);

        if (exit_node >= 0 &&
            (target < 0 || distances[exit_node] < distances[target])) {
            target = exit_node;
        }
    }

    if (target < 0 || distances[target] == DBL_MAX) {
        printf(
            "{\"path\":[],\"cost\":null,\"visited\":%d,"
            "\"relaxations\":%d}\n",
            explored_count,
            relaxation_count
        );
        return 0;
    }

    int reverse_path[MAX_NODES];
    int path_length = 0;

    for (int node = target; node >= 0 && path_length < node_count;
         node = previous[node]) {
        reverse_path[path_length++] = node;
        if (node == start) {
            break;
        }
    }

    if (reverse_path[path_length - 1] != start) {
        return 10;
    }

    printf("{\"path\":[");
    for (int i = path_length - 1; i >= 0; i--) {
        printf("%s\"%s\"", i == path_length - 1 ? "" : ",",
               node_names[reverse_path[i]]);
    }
    printf(
        "],\"cost\":%.8f,\"visited\":%d,\"relaxations\":%d}\n",
        distances[target],
        explored_count,
        relaxation_count
    );

    return 0;
}
