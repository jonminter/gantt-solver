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
import json
import sys
import argparse
import jsonschema

@dataclass
class Project:
    id: str
    name: str
    duration: int
    num_resources: object
    start: object
    interval: object
    end: object
    dependencies: List[Dependency]


@dataclass
class Dependency:
    project: Project
    lag_time: object


INPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["max_resources_in_parallel", "projects"],
    "properties": {
        "max_resources_in_parallel": {"type": "number"},
        "projects": {
            "type": "object",
            "additionalProperties": False,
            "patternProperties": {
                ".*": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["name", "num_resources", "duration", "dependencies"],
                    "properties": {
                        "name": {"type": "string"},
                        "num_resources": {"type": "number"},
                        "duration": {"type": "number"},
                        "dependencies": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": ["project_id", "lag_time"],
                                "properties": {
                                    "project_id": {"type": "string"},
                                    "lag_time": {"type": "number"},
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}


def main():
    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument("input_file", help="JSON file with project definitions")
    arg_parser.add_argument("output_file", help="PNG file to save gantt chart visualization to")
    arg_parser.add_argument("--timeout", default=30, type=int, help="Maximum time (in seconds) to allow gantt solver to run")
    args = arg_parser.parse_args()
    inpput_json_file = args.input_file
    output_png_file = args.output_file
    maximum_time_to_run = args.timeout

    # Input
    projects = {}
    projects_json = {}
    with open(inpput_json_file, encoding = 'utf-8') as f:
        projects_json = json.loads(f.read())

    jsonschema.validate(projects_json, INPUT_SCHEMA)

    # build dependency graph and sort topologically, just a trick so we can have
    # a dependency reference it's project instance. We can do this if we build the 
    # projects in topological order vs input defined order
    #
    # Note we could have used the project ID to define the dependencies
    # and look up the project instance from our map we build when we need it
    # but topo sort is cool
    projects_ordered_by_dependency = []
    project_dependency_graph = TopologicalSorter()
    for project_id, project in projects_json['projects'].items():
        project_dependency_graph.add(project_id, *[x['project_id'] for x in project['dependencies']])
    projects_ordered_by_dependency = [*project_dependency_graph.static_order()]

    # Compute horizon dynamically (sum of all durations we could never have a schedule 
    # longer than this as this is as if projects were done one after another)
    horizon = sum(project['duration'] for project in projects_json['projects'].values())
    
    model = ortools.sat.python.cp_model.CpModel()

    def create_dependency(model: CpModel, project_id: str, dependency_def: dict):
        dependency_lag_time = model.NewIntVar(dependency_def['lag_time'], dependency_def['lag_time'], f"depedency_lag_time_{project_id}_{dependency_def['project_id']}")  
        return Dependency(projects[dependency_def['project_id']], dependency_lag_time)

    # create model vars/depenencies for projects
    for project_id in projects_ordered_by_dependency:
        project = projects_json['projects'][project_id]
        suffix = project_id
        
        num_resources = model.NewConstant(project['num_resources'])
        start = model.NewIntVar(0, horizon, 'start' + suffix)
        end = model.NewIntVar(0, horizon, 'end' + suffix)
        interval = model.NewIntervalVar(start, project['duration'], end, 'interval' + suffix)
        
        deps = [create_dependency(model, project_id, dependency_def) for dependency_def in project['dependencies']]
        
        projects[project_id] = Project(project_id, project['name'], project['duration'], num_resources, start, interval, end, deps)

    # CONSTRAINTS
    # - A project can only be started after it's dependent projects are finished (+lag time/-lead time)
    for project_id, project in projects.items():
        for dependency in project.dependencies:
            model.Add(project.start >= dependency.project.end + dependency.lag_time)
    
    # We can only use max resources at a time
    # Add a constraint that for every project interval sum num resources
    # required the project. Ensures that at no singular point in the 
    # timeline are there projects active that require more resources
    # than we have available
    #
    # forall t from 0 to max interval end:
    #     sum(num_resources[i] if (project.start <= t <= project.end)) <= max_resources_at_a_time
    max_resources_at_a_time = projects_json['max_resources_in_parallel']
    model.AddCumulative(
        [project.interval for project in projects.values()],
        [project.num_resources for project in projects.values()],
        max_resources_at_a_time)

    # OBJECTIVE
    # We want to find solutions that minimize total_duration of all projects
    # We can find total_duration by taking the max project end time and add a minimizing
    # objective to our model. This will rate solutions with a shorter 
    # total duration as better solutions
    total_duration = model.NewIntVar(0, horizon, 'total_duration')
    model.AddMaxEquality(total_duration, [project.end for project in projects.values()])
    model.Minimize(total_duration)

    # FIND A SOLUTION
    solver = ortools.sat.python.cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = maximum_time_to_run
    status = solver.Solve(model)

    # Print output if the solution is optimal/feasible
    if (status == ortools.sat.python.cp_model.OPTIMAL or status == ortools.sat.python.cp_model.FEASIBLE):
        # Print the solution
        print('--- Final solution ---\n')
        print('Optimal Schedule Length: {0}\n'.format(solver.ObjectiveValue()))
        print('Schedules:')

        bars = []
        projects_sorted_by_start = list(projects.values())
        projects_sorted_by_start.sort(key=lambda p: solver.Value(p.start), reverse=True)

        for project in projects_sorted_by_start:
            project_start = solver.Value(project.start)
            project_end = solver.Value(project.end)
            num_resources = solver.Value(project.num_resources)
            bars.append((project.name,num_resources, (project_start, project.duration)))

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

        # Show or save the plot
        #plt.show()
        plt.savefig(output_png_file)
    else:
        print("No feasible solution found!")


# Tell python to run main method
if __name__ == '__main__': main()