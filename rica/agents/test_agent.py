from rica.testrunner import TestRunner


class TestAgent:
    def __init__(self, project_dir: str):
        self.runner = TestRunner(project_dir)

    def find_tests(self, snapshot) -> list[str]:
        return self.runner.find_tests(snapshot)

    def run(self) -> dict:
        return self.runner.run()
