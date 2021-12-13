# gantt-solver
Scripts to generate Gantt charts given set of tasks with constraints

## Run example
```
python3 -m venv .venv
source .venv/bin/activate
pip3 install -r requirements.txt
python3 gantt_solver/create_gantt_chart.py example-input.json example-output.png
open example-output.png
```