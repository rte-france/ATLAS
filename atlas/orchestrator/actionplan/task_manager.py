import heapq
from typing import cast

from pendulum import DateTime

from atlas.orchestrator.actionplan.parameters import Task


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
        self.priority_queue: list[TaskIterator] = []
        for task in tasks:
            self._push(TaskIterator(task))

    def _pop(self) -> TaskIterator:
        return heapq.heappop(self.priority_queue)

    def _push(self, task: TaskIterator) -> None:
        heapq.heappush(self.priority_queue, task)

    def __iter__(self):
        return self

    def __next__(self) -> tuple[Task, DateTime]:
        """
        Return the next Task with the associated execution date.
        """
        while len(self) > 0:
            priority_task_itr = self._pop()
            task, date_time = next(priority_task_itr, (None, None))
            if (task, date_time) != (None, None):
                self._push(priority_task_itr)
                return cast(tuple[Task, DateTime], (task, date_time))

        raise StopIteration

    def __len__(self):
        """Return the number of items in the queue."""
        return len(self.priority_queue)
