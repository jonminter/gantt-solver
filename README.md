# gantt-solver
Scripts to generate Gantt charts given set of tasks with constraints

## Run example
```
python3 -m venv .venv
source .venv/bin/activate
pip3 install -r requirements.txt
cd examples
python3 ../gantt_solver/create_gantt_chart.py example-input.json example-output
open example-output.solution0.png
```
![Example Gantt Chart](./examples/example-out.solution0.png)
