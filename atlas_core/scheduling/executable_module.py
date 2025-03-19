from abc import ABC, abstractmethod

class ExecutableModule(ABC):
    @abstractmethod
    def execute(self, parameters, input_marker):
        pass