from atlas_core.scheduling.executable_module import ExecutableModule


class WorkflowStep:

    def __init__(self, name: str, parameters, executable_module: ExecutableModule, input_marker = None):
        self.name = name
        self.input_marker = input_marker
        self.parameters = parameters
        self.output_marker = None
        self.module = executable_module

    def execute_step(self):
        self.output_marker = self.module.execute(self.parameters, self.input_marker)