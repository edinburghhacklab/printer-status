from printrun.printcore import printcore
from printers.status_packet import Status
import re
from logging import Logger, getLogger
from paho.mqtt.client import Client
import json
from enum import Enum

status_regex = re.compile(r"done: ([0-9]*).+?mins: ([0-9]*)")


class State(str, Enum):
    Paused = "Paused"
    Cancelled = "Cancelled"
    Printing = "Printing"
    Complete = "Complete"

class Printer:
    printer: printcore

    # Config
    name: str
    model: str
    colour: str
    serial: str
    baud: int

    # Status
    connected: bool
    state: State
    file: str
    cwd: str
    percent_done: int
    time_remaining_mins: int

    # Internal
    mode = 'n' # n = normal, f = file list

    logger: Logger
    client: Client

    def __init__(self, config: dict[str, str | int], client: Client):
        self.name = str(config["name"])
        self.shortname = str(config["shortname"])
        self.model = str(config["model"])
        self.colour = str(config["colour"])
        self.serial = str(config["serial"])
        self.baud = int(config["baud"])

        self.logger = getLogger(self.name)
        self.client = client

        self.state = State.Complete
        self.time_remaining_mins = 0
        self.percent_done = 0
        self.file = "None"
        self.cwd = "None"

        self.send_status_to_mqtt()

    def send_status_to_mqtt(self):
        # Show as idle when not connected
        if not self.connected:
            self.state = State.Complete

        self.publish(f"printers/{self.shortname}/state", str(self.state), retain=True)
        self.publish(
            f"printers/{self.shortname}/percent_done",
            str(self.percent_done),
            retain=True,
        )
        self.publish(
            f"printers/{self.shortname}/time_remaining_mins",
            str(self.time_remaining_mins),
            retain=True,
        )
        self.publish(
            f"printers/{self.shortname}/file",
            str(self.file),
            retain=True,
        )

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

    # Recieve callback
    def handle_msg(self, line: str):
        line = line.rstrip("\n")
        self.logger.debug(f"M: {self.mode} RECV: {line}")

        # Normal mode
        if self.mode == 'n':
            # Print Status echo: 'NORMAL MODE: Percent done: 32; print time remaining in mins: 8; Change in mins: -1'
            if line[0:11] == "NORMAL MODE":
                stats: regex.Match[str] = status_regex.search(line)  # type: ignore
                self.logger.debug(f"{stats.group(1)}, {stats.group(2)}")

                self.state = State.Printing
                self.percent_done = int(stats.group(1))
                self.time_remaining_mins = int(stats.group(2))
                self.send_status_to_mqtt()

            # File opened: /JACOB/0.4/Cali-Dragon-Tiny_PLA.gcode Size: 467996
            elif line[0:12] == "File opened:":
                file_name = line[13:-1].split(" ")[0]
                self.state = State.Printing
                self.file = file_name
                self.cwd = '/'.join(file_name.split('/')[0:-2])
                self.send_status_to_mqtt()

            # File Finished: 'Done printing file'
            elif line == "Done printing file":
                self.state = State.Complete
                self.percent_done = 100
                self.time_remaining_mins = 0
                # Don't clear file and CWD yet so we can try and ping the user on discord
                self.on_complete()
                self.send_status_to_mqtt()

            # Print manually paused: '//action:paused'
            # Print paused automatically: 'echo:busy: paused for user'
            elif line == "//action:paused" or line == "echo:busy: paused for user" and self.state != State.Paused:
                self.state = State.Paused
                self.send_status_to_mqtt()
                self.on_complete()

            # Print cancelled
            elif line == "//action:cancel":
                self.state = State.Cancelled
                self.send_status_to_mqtt()
                self.on_complete()

            elif line.startswith("Begin file list"):
                self.mode = 'f'
            else:
                self.logger.debug(f"Unknown Recv")

        # File list mode
        elif self.mode == 'f':
            if line == "End file list":
                self.mode = 'n'
            elif line.startswith(self.cwd) == self.cwd:
                self.logger.debug(f"Matched dir: {line}")
                _SD_path, _size, long_name = line.split(" ")
                if long_name.startswith("config.discord..."):
                    username = long_name.removeprefix("config.discord...").removesuffix(".gcode")

                    self.publish("irc/send", json.dumps({
                        "to": "#edinhacklab-things",
                        "message": f"@{username} print '{self.file}' complete on {self.name}"
                    }))

    def publish(self, topic: str, payload: str, retain=False):
        if not self.client.is_connected():
            self.client.connect("mqtt.hacklab")

        self.client.publish(topic, payload, retain=retain)


    def on_complete(self):
        self.printer.send_now("M20 L")
        self.publish(f"sound/g1/speak", f"Print finished on {self.name}")
