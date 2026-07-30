from printrun.printcore import printcore
from logging import Logger, getLogger

from printer_status.status_recorder import StatusRecorder
from .printer import Printer as BasePrinter

from abc import abstractmethod


class PrintCorePrinter(BasePrinter):
    printer: printcore
    connected: bool

    name: str
    serial: str
    baud: int
    logger: Logger

    def __init__(self, config: dict[str, str | int]):
        self.name = str(config["shortname"])
        self.serial = str(config["serial"])
        self.baud = int(config["baud"])
        self.logger = getLogger(self.name)

    def main_loop(self, recorder: StatusRecorder):
        self.recorder = recorder
        recorder.not_printing()
        while True:
            self.connect()
            if self.printer.read_thread:
                self.printer.read_thread.join()
            if self.printer.send_thread:
                self.printer.send_thread.join()

    def connect(self) -> bool:
        self.logger.info(f"Connecting to printer {self.name}")
        # Connect
        try:
            # Connect to printer
            self.printer = printcore(port=self.serial, baud=self.baud)
            self.connected = True

        except Exception as err:
            self.logger.error(f"Could not connect to printer {self.name}: {err}")
            self.connected = False

        # Setup
        try:
            # Setup recieve callback
            self.printer.recvcb = self.handle_msg  # type: ignore
            self.printer.event_handler

        except Exception as err:
            self.logger.error(f"Could not setup printer {self.name}: {err}")
            self.connected = False

        return self.connected

    @abstractmethod
    def handle_msg(self, line: str):
        pass
