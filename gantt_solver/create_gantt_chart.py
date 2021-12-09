from __future__ import annotations

# Import libraries
import collections
import ortools.sat.python.cp_model
from ortools.sat.python.cp_model import CpModel
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from typing import List
from graphlib import TopologicalSorter
from dataclasses import dataclass
from functools import partial

@dataclass
class Project:
    id: str
    name: str
    time_in_weeks: int
    num_resources: object
    start: object
    interval: object
    end: object
    dependencies: List[Dependency]

@dataclass
class Dependency:
    project: Project
    lag_time: object



def main_projects():
    # Input
    projects = {}
    projects_json = {
        'max_resources_in_parallel': 3,
        'projects': {
            'take-out-the-trash': {
                'name': 'Take out the trash',
                'num_resources': 2,
                'time_in_weeks': 2,
                'dependencies': [{
                    'project_id': 'clean-the-sink',
                    'lag_time': 1,
                }]
            },
            'do-the-dishes': {
                'name': 'Do the dishes',
                'num_resources': 1,
                'time_in_weeks': 1,
                'dependencies': [{
                    'project_id': 'clear-the-table',
                    'lag_time': 0,
                }]
            },
            'clean-the-sink': {
                'name': 'Clean the sink',
                'num_resources': 1,
                'time_in_weeks': 2,
                'dependencies': [{
                    'project_id': 'do-the-dishes',
                    'lag_time': -1,
                }]
            },
            'sweep-the-floor': {
                'name': 'Sweep the floor',
                'num_resources': 2,
                'time_in_weeks': 1,
                'dependencies': []
            },
            'clear-the-table': {
                'name': 'Clear the table',
                'num_resources': 1,
                'time_in_weeks': 3,
                'dependencies': []
            },
            'vaccum-carpet': {
                'name': 'Vaccum Carpet',
                'num_resources': 1,
                'time_in_weeks': 5,
                'dependencies': []
            },
        },
    }

    # build dependency graph and sort topologically, just a trick so we can have dependency reference project instance
    # not completely necessary we could have used a map just didn't realize till now python3 has this graphlib
    sorted_projects = []
    project_dependency_graph = TopologicalSorter()
    for project_id, project in projects_json['projects'].items():
        project_dependency_graph.add(project_id, *[x['project_id'] for x in project['dependencies']])
    sorted_projects = [*project_dependency_graph.static_order()]

    # Compute horizon dynamically (sum of all durations)
    horizon = sum(project['time_in_weeks'] for project in projects_json['projects'].values())
    # Create a model
    model = ortools.sat.python.cp_model.CpModel()

    def create_dependency(model: CpModel, project_id: str, dependency_def: dict):
        dependency_lag_time = model.NewIntVar(dependency_def['lag_time'], dependency_def['lag_time'], f"depedency_lag_time_{project_id}_{dependency_def['project_id']}")  
        return Dependency(projects[dependency_def['project_id']], dependency_lag_time)

    # create model vars for projects
    for project_id in sorted_projects:
        project = projects_json['projects'][project_id]
        suffix = project_id
        # Create model variables
        num_resources = model.NewIntVar(project['num_resources'], project['num_resources'], 'num_resources' + suffix)
        start = model.NewIntVar(0, horizon, 'start' + suffix)
        end = model.NewIntVar(0, horizon, 'end' + suffix)
        interval = model.NewIntervalVar(start, project['time_in_weeks'], end, 'interval' + suffix)
        #dependencies
        deps = [*map(partial(create_dependency, model, project_id), project['dependencies'])]
        # Add a task
        projects[project_id] = Project(project_id, project['name'], project['time_in_weeks'], num_resources, start, interval, end, deps)

    # constraints
    # - A project can only be started after it's dependent projects are finished (+lag time/-lead time)
    for project_id, project in projects.items():
        for dependency in project.dependencies:
            model.Add(project.start >= dependency.project.end + dependency.lag_time)
    # We can only use max resources at a time
    model.Add

    # Create an objective function
    objective = model.NewIntVar(0, horizon, 'total_duration')
    model.AddMaxEquality(objective, [project.end for project in projects.values()])
    model.Minimize(objective)
    # Create a solver
    solver = ortools.sat.python.cp_model.CpSolver()
    # Set a time limit of 30 seconds.
    solver.parameters.max_time_in_seconds = 30.0
    # Solve the problem
    status = solver.Solve(model)
    # Print output if the solution is optimal/feasible
    if (status == ortools.sat.python.cp_model.OPTIMAL or status == ortools.sat.python.cp_model.FEASIBLE):
        # Print the solution
        print('--- Final solution ---\n')
        print('Optimal Schedule Length: {0}\n'.format(solver.ObjectiveValue()))
        print('Schedules:')

        bars = []
        for project_id, project in projects.items():
            project_start = solver.Value(project.start)
            project_end = solver.Value(project.end)
            num_resources = solver.Value(project.num_resources)
            bars.append((project.name,num_resources, (project_start, project.time_in_weeks)))

            print(project.name,':', project_start, ' -> ', project_end)
                
        
        # Plot gantt chart
        fig, gnt = plt.subplots(figsize=(12, 8))
        fig.suptitle('Gantt Chart', fontsize=16)
        gnt.set_xlabel('Start/Duration in Weeks') 
        gnt.set_ylabel('Projects') 
        gnt.set_yticks([12 + i * 10 for i in range(len(bars))]) 
        gnt.set_yticklabels([bar[0] for bar in bars]) 
        gnt.grid(True)
        allcolors=[
            'tab:orange',
            'tab:green',
            'tab:red',
            'tab:purple',
            'tab:blue',
            'tab:pink',
            'tab:black'
        ]
        # Loop bars
        for i in range(len(bars)):
            print("bar = ", bars[i])
            gnt.broken_barh([bars[i][2]], (10 + i * 10, 4), facecolors=(allcolors[i], 'tab:grey'))
            j = 0
            for x1, x2 in [bars[i][2]]:
                gnt.text(x=x1 + x2/2, y= 12 + i * 10, s=bars[i][1], ha='center', va='center', color='white')
                j += 1
        # Create a legend
        # labels = []
        # labels.append(mpatches.Patch(color='tab:orange', label='Task 0'))
        # labels.append(mpatches.Patch(color='tab:green', label='Task 1'))
        # labels.append(mpatches.Patch(color='tab:red', label='Task 2'))
        # plt.legend(handles=labels, loc=4)
        # Show or save the plot
        #plt.show()
        plt.savefig("schedule-gantt-projects.png")


# Tell python to run main method
if __name__ == '__main__': main_projects()