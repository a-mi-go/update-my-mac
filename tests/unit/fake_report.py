"""A report that prints whatever a test hands it."""


class FakeReport:
    def __init__(self, print_to):
        self.print_to = print_to
        self.printed = False
