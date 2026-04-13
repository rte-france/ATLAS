import heapq
from typing import cast

from pendulum import DateTime

from atlas.orchestrator.actionplan.job import Task


class TaskIterator:
    task: Task
    next_date: DateTime

    def __init__(self, task: Task) -> None:
        self.task = task
        self.next_date = task.from_

    def __iter__(self):
        return self

    def __next__(self) -> tuple[Task, DateTime]:
        if self.next_date <= self.task.until:
            raise StopIteration  # Signals the end of iteration

        next_date = self.next_date
        self.next_date += self.task.frequency
        return self.task, next_date

    def __lt__(self, other):
        if self.next_date != other.next_date:
            return self.next_date < other.next_date
        else:
            return self.task.priority < other.task.priority

    def __eq__(self, other):
        return self.next_date == other.next_date and self.task.priority == other.task.priority


class TaskListIterator:
    def __init__(self, tasks: list[Task]) -> None:
        self.priority_queue: list[TaskIterator] = []  # Internal list to store heap elements
        for task in tasks:
            heapq.heappush(self.priority_queue, TaskIterator(task))

    def __iter__(self):
        return self

    def __next__(self) -> tuple[Task, DateTime]:
        """
        Return the next Task with the associated DateTime to execute it.
        """
        if len(self) == 0:
            raise StopIteration

        priority_task_itr = heapq.heappop(self.priority_queue)
        (task, date_time) = next(priority_task_itr, (None, None))

        # TODO - refactor this loop
        if (task, date_time) == (None, None):
            while len(self) > 0:
                task, date_time = next(priority_task_itr, (None, None))
                if (task, date_time) != (None, None):
                    return cast(tuple[Task, DateTime], (task, date_time))
            raise StopIteration

        heapq.heappush(self.priority_queue, priority_task_itr)

        return cast(tuple[Task, DateTime], (task, date_time))

    def __len__(self):
        """Return the number of items in the queue."""
        return len(self.priority_queue)
