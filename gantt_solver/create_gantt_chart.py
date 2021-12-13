from __future__ import annotations

# Import libraries
import collections
import ortools.sat.python.cp_model
from ortools.sat.python.cp_model import CpModel, CpSolverSolutionCallback
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from typing import List, Dict
from graphlib import TopologicalSorter
from dataclasses import dataclass, field
import json
import jsons
import sys
import argparse
import jsonschema
import heapq

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

@dataclass
class ProjectSchedule:
    project_id: str
    project_name: str
    num_resources: int
    start: int
    end: int

@dataclass(order=True)
class ProjectSchedulingSolution:
    total_duration: int
    project_schedules: List[ProjectSchedule] = field(compare=False)

class SolutionCollector(CpSolverSolutionCallback):
    def __init__(self, projects: Dict[str, Project], limit: int):
        CpSolverSolutionCallback.__init__(self)
        self.__projects = projects
        self.__solution_count = 0
        self.__solution_limit = limit
        self.__solutions = []

    def on_solution_callback(self):
        self.__solution_count += 1

        total_duration = self.ObjectiveValue()

        project_schedules = []
        for project_id, project in self.__projects.items():
            project_schedules.append(ProjectSchedule(
                project_id,
                project.name,
                self.Value(project.num_resources),
                self.Value(project.start),
                self.Value(project.end),
            ))

        # Treat __solutions as a heap insert with schedules with shortest durations at head of list
        heapq.heappush(
            self.__solutions,
            ProjectSchedulingSolution(int(total_duration), project_schedules))

    def solution_count(self) -> int:
        return self.__solution_count
    
    def top_solutions(self) -> List[ProjectSchedulingSolution]:
        """
        Return the first {self.__solution_limit} solutions ordered by total duration of the schedule

        TODO: If storing all solutions in memory is ever an issue can
              use heapq.nsmallest to trucate heap in on_solution_callback if the
              heap exeeds {self.__solution_limit}. We can do this because it's a min
              heap and we know that the smallest item we could have discarded would
              still be greater than the largest item in the heap
        """
        return heapq.nsmallest(self.__solution_limit, self.__solutions)



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

def save_solution_json(project_scheduling_solution: ProjectSchedulingSolution, output_file: str):
    with open(output_file, mode="w") as f:
        f.write(jsons.dumps(project_scheduling_solution, indent=True))

def create_gantt_chart(project_scheduling_solution: ProjectSchedulingSolution, output_file: str):
    bars = []

    project_schedules_ordered_by_start = project_scheduling_solution.project_schedules
    project_schedules_ordered_by_start.sort(key=lambda p: p.start, reverse=True)

    for project_schedule in project_schedules_ordered_by_start:
        project_start = project_schedule.start
        # project_end = project_schedule.end
        num_resources = project_schedule.num_resources
        bars.append((project_schedule.project_name,num_resources, (project_start, project_schedule.end - project_schedule.start)))

    # Plot gantt chart
    fig, gnt = plt.subplots(figsize=(12, 8))
    fig.suptitle('Gantt Chart', fontsize=16)
    gnt.set_xlabel('Start/Duration') 
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
        gnt.broken_barh([bars[i][2]], (10 + i * 10, 4), facecolors=(allcolors[i % len(allcolors)], 'tab:grey'))
        j = 0
        for x1, x2 in [bars[i][2]]:
            gnt.text(x=x1 + x2/2, y= 12 + i * 10, s=bars[i][1], ha='center', va='center', color='white')
            j += 1

    # save the plot
    plt.savefig(output_file)


def main():
    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument("input_file", help="JSON file with project definitions")
    arg_parser.add_argument("output_file", help="Prefix for solution JSON files and Gantt chart PNGs")
    arg_parser.add_argument("--timeout", default=30, type=int, help="Maximum time (in seconds) to allow gantt solver to run")
    arg_parser.add_argument("--max-solutions", default=5, type=int, help="Maximum number of solutions to find before stopping")
    arg_parser.add_argument("--max-duration", default=0, type=int,
        help = "Constraint for maximum total duration of projects.For a solution to be valid total duration must be less than or equal to this number.")
    args = arg_parser.parse_args()
    inpput_json_file = args.input_file
    output_file = args.output_file
    maximum_time_to_run = args.timeout
    maximum_num_solutions = args.max_solutions
    maximum_duration = args.max_duration

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
    
    # We can only use up to max resources at a time
    # Add a constraint that for every project interval sum num resources
    # required by the project. Ensures that at no singular point in the 
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

    # If a max duration was set then add a constraint for max duration
    total_duration = model.NewIntVar(0, horizon, 'total_duration')
    model.AddMaxEquality(total_duration, [project.end for project in projects.values()])

    if maximum_duration > 0:
        model.Add(total_duration <= maximum_duration)

    # OBJECTIVE
    # We want to find solutions that minimize total_duration of all projects
    # We can find total_duration by taking the max project end time and add a minimizing
    # objective to our model. This will rate solutions with a shorter 
    # total duration as better solutions
    model.Minimize(total_duration)

    # FIND A SOLUTION
    solver = ortools.sat.python.cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = maximum_time_to_run
    solution_collector = SolutionCollector(projects, maximum_num_solutions)
    status = solver.Solve(model, solution_collector)

    # Print output if the solution is optimal/feasible
    if solution_collector.solution_count() > 0:
        print(f"Found solutions! Status = {solver.StatusName(status)}")
        for i, solution in enumerate(solution_collector.top_solutions()):
            json_file = f"{output_file}.solution{i}.json"
            chart_file = f"{output_file}.solution{i}.png"
            save_solution_json(solution, json_file)
            create_gantt_chart(solution, chart_file)
            print(f"Solution {i}:")
            print(f"---- {json_file}")
            print(f"---- {chart_file}")
    else:
        raise RuntimeError("No feasible solution found!")


# Tell python to run main method
if __name__ == '__main__': main()