from abc import ABC, abstractmethod

from printer_status.status_recorder import StatusRecorder


class Printer(ABC):
    @abstractmethod
    def main_loop(self, recorder: StatusRecorder):
        pass
