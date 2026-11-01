# Evacuation Simulator

## 1. Technologies

| Component           | Technology            |
| ------------------- | --------------------- |
| Backend server      | Python                |
| Frontend            | HTML, CSS, JavaScript |
| Communication       | HTTP / JSON           |
| Routing algorithms  | Python and C          |
| C compiler          | GCC (MinGW-w64)       |
| Graph configuration | JSON                  |

The Python backend uses only standard-library modules, so no external Python dependencies are required.

## 2. Project Structure

```text
third-floor-evacuator/
│
├── server.py
├── index.html
├── graph.json
├── README.md
├── .gitignore
│
├── assets/
│   └── third_floor_clean.png
│
└── c_algorithm/
    └── test_routing.c
```

### Main files

- **`server.py`** — HTTP server, simulation engine, movement, dynamic weights, routing integration and statistics.
- **`index.html`** — Graphical interface, animation, controls and results visualization.
- **`graph.json`** — Nodes, edges, distances, coordinates and waypoints.
- **`assets/third_floor_clean.png`** — Third-floor background image.
- **`c_algorithm/test_routing.c`** — Temporary C routing implementation for integration testing.
- **`.gitignore`** — Excludes generated files and compiled executables.

## 3. Installation

### Requirements

- Python 3
- Git (to clone the repository)
- GCC (required for compiling the C algorithm)

### Start the server

On Windows:

```powershell
py server.py
```

Alternatively:

```powershell
python server.py
```

Open your browser and navigate to:

**[http://127.0.0.1:8000](http://127.0.0.1:8000)**

Press `Ctrl + C` in the terminal to stop the server.

## 4. Routing Algorithms

The simulator currently includes three routing options.

| Algorithm              | Language | Description                                                                |
| ---------------------- | -------- | -------------------------------------------------------------------------- |
| Dijkstra               | Python   | Calculates shortest paths using dynamic edge weights                       |
| Bidirectional Dijkstra | Python   | Searches from both ends of a route                                         |
| Test Dijkstra          | C        | Temporary implementation used to test communication with the Python server |

### Compiling the C algorithm

Install GCC using [MSYS2](https://www.msys2.org/).

In the MSYS2 UCRT64 terminal:

```bash
pacman -S --needed mingw-w64-ucrt-x86_64-gcc
```

Add `C:\msys64\ucrt64\bin` to Windows PATH.

Verify the installation:

```powershell
gcc --version
```

From the project directory, compile the C file:

```powershell
gcc -O2 -std=c11 .\c_algorithm\test_routing.c -o .\c_algorithm\test_routing.exe
```

The Python server also supports automatic compilation when the C algorithm is selected and the executable is missing or outdated.

## 5. System Architecture

The simulator consists of three components:

```text
Browser Interface
        |
        | HTTP / JSON
        v
   Python Server
        |
        | stdin / stdout
        v
    C Algorithm
```

### Browser and Python communication

The browser communicates with `server.py` using HTTP requests.

The frontend sends commands using JavaScript's `fetch()` function, while Python processes requests through its built-in `http.server` module.

Examples of supported endpoints:

| Endpoint           | Purpose                    |
| ------------------ | -------------------------- |
| `GET /api/state`   | Retrieve simulation state  |
| `POST /api/step`   | Advance simulation         |
| `POST /api/reset`  | Reset simulation           |
| `POST /api/config` | Update parameters          |
| `POST /api/algo`   | Select algorithm           |
| `POST /api/block`  | Toggle blocked connections |
| `GET /api/export`  | Export results             |
| `GET /graph.json`  | Retrieve graph             |

The browser repeatedly requests simulation updates and redraws the interface using the returned information.

### Python and C communication

Python executes the compiled C program using `subprocess.run()`.

Communication occurs through standard input and output:

- **stdin:** Python sends the graph and routing request.
- **stdout:** C returns the calculated route as JSON.
- **stderr:** C reports errors.

## 6. EVAC1 Protocol

The Python server and C routing algorithms communicate using the **EVAC1 protocol**.

### Input

Python sends:

1. Protocol identifier (`EVAC1`)
2. Number of nodes, directed arcs and exits
3. Node identifiers
4. Exit identifiers
5. Directed connections and dynamic weights
6. Starting node and optional forbidden first neighbor

Example:

```text
EVAC1
4 4 1
K3
K2
A
U2
U2
K3 K2 17.500000000
K2 K3 17.500000000
K2 A 15.083333333
A U2 6.916666667
K3 _
```

### Output

The C algorithm returns JSON:

```json
{
  "path": ["K3", "K2", "A", "U2"],
  "cost": 39.5,
  "visited": 4,
  "relaxations": 3
}
```

The response contains the calculated path, total route cost, visited nodes and relaxation attempts.

Any future C implementation must support this protocol to communicate with the Python server without changing the current routing interface.

## 7. Adding New C Routing Algorithms

The Python server has been configured to support **multiple C routing algorithms** through the `C_ROUTERS` dictionary.

Each algorithm is registered with a unique identifier and linked to its corresponding C source file and executable.

### Step 1 — Add the new C algorithm

Place the new C source file inside the `c_algorithm` directory.

For example:

```text
c_algorithm/
├── test_routing.c
└── bidirectional_routing.c
```

### Step 2 — Register the algorithm in server.py

Open `server.py` and locate the `C_ROUTERS` dictionary - line 160.

The current implementation is:

```python
C_ROUTERS = {
    'c_test': CRouter(
        'test_routing',
        env_var='EVAC_C_EXECUTABLE'
    ),
}
```

Add the new algorithm:

```python
C_ROUTERS = {
    'c_test': CRouter(
        'test_routing',
        env_var='EVAC_C_EXECUTABLE'
    ),

    'c_bidirectional': CRouter(
        'bidirectional_routing'
    ),
}
```

In this example:

- **`c_bidirectional`** is the unique algorithm identifier used by the simulator.
- **`bidirectional_routing`** is the C source filename without the `.c` extension.

### Step 3 — Add the algorithm to index.html

Open `index.html` and find the algorithm dropdown - line 488: 

```html
<select id="algorithm" title="Routing algorithm">
  <!--DROPDOWN menu- ADD new algorithms here-->
  <option value="dijkstra">Python · Dijkstra</option>
  <option value="bidirectional">Python · Bidirectional Dijkstra</option>
  <option value="c_test">C · Test algorithm</option>
</select>
```

Add the new algorithm for exempel:

```html
<option value="c_bidirectional">C · Bidirectional Dijkstra</option>
```

**Important:** The value `c_bidirectional` must match the identifier registered in `C_ROUTERS`.


### Step 4 — Update the algorithm label in the statistics panel

In `index.html`, find the lable section - line 1084:

```javascript
$('algo-label').textContent = {
    dijkstra: 'Python Dijkstra',
    bidirectional: 'Python Bidirectional',
    c_test: 'C Test',
}[model.algorithm];
```

Add the new algorithm:

```javascript
$('algo-label').textContent = {
    dijkstra: 'Python Dijkstra',
    bidirectional: 'Python Bidirectional',
    c_test: 'C Test',
    c_bidirectional: 'C Bidirectional',
}[model.algorithm];
```

### Step 5 — Update the completed-runs comparison table

In `index.html`, locate this section - line 1145 :

```javascript
<td>${{
    dijkstra: 'Dijkstra',
    bidirectional: 'Bi-Dijkstra',
    c_test: 'C Test',
}[run.algorithm]}</td>
```

Add the new algorithm:

```javascript
<td>${{
    dijkstra: 'Dijkstra',
    bidirectional: 'Bi-Dijkstra',
    c_test: 'C Test',
    c_bidirectional: 'C Bidirectional',
}[run.algorithm]}</td>
```


### Step 6 — Compile the new C algorithm

Open a terminal in the main project directory.

Compile the new C file with GCC, this generates the executable that Python will use.

Manual compilation is optional if GCC is already installed and accessible to the Python server.

The `CRouter.compile()` method automatically checks whether the executable exists and whether the C source file has been modified since the last compilation.

If compilation is required, Python executes GCC automatically.


## 8. Simulation Results

The simulator collects metrics for evaluating both evacuation efficiency and routing performance.

### Evacuation metrics

- Total evacuation time
- Number of evacuated students
- Mean and maximum evacuation times
- Average distance walked
- Peak exit queue length
- Exit distribution between U1 and U2

### Algorithm metrics

- Number of routing requests
- Total routing time
- Average and maximum routing time
- Explored nodes
- Relaxation attempts
- Number of route changes

---

## License

No license has been specified for this project.


