from printer_status.status_recorder import StatusRecorder
from .printcore import PrintCorePrinter
import re
from enum import StrEnum, Enum
from urllib import request
import json
from datetime import datetime, timedelta

status_regex = re.compile(r"done: ([0-9]*).+?mins: ([0-9]*)")

M27_INTERVAL = timedelta(seconds=5)


class State(StrEnum):
    Paused = "paused"
    Printing = "printing"
    Idle = "idle"


class ParseMode(Enum):
    Normal = 1
    File = 2


class Printer(PrintCorePrinter):
    # Status
    state: State
    file: str
    username: str | None
    percent_done: int
    time_remaining_mins: int

    # Internal
    mode: ParseMode

    in_username_dir: bool
    dir_depth: int

    last_m27: datetime

    def __init__(self, config: dict[str, str | int], recorder: StatusRecorder):
        super(Printer, self).__init__(config)

        self.recorder = recorder
        self.mode = ParseMode.Normal
        self.state = State.Idle
        self.time_remaining_mins = 0
        self.percent_done = 0
        self.file = "unknown"
        self.username = None
        self.in_username_dir = False
        self.dir_depth = 0
        self.last_m27 = datetime.now()
        self.api_base = config["api_base"]
        with open(config["api_key_file"]) as f:
            self.api_key = f.read().strip()

    def handle_msg(self, line: str):
        line = line.rstrip("\n")
        self.logger.debug(f"M: {self.mode} RECV: {line}")

        # Normal mode
        if self.mode == ParseMode.Normal:
            # X:12.50 Y:10.50 Z:2.00 E:-1.00 Count X:1250 Y:1050 Z:800
            # We need to send M27s periodically to get % info, so check if it's time to do that here
            if (
                line.startswith("X:")
                and (datetime.now() - self.last_m27 >= M27_INTERVAL)
                and self.state == State.Printing
            ):
                self.last_m27 = datetime.now()
                self.printer.send("M73")

            # echo: M73 Progress: 0%;
            elif (
                line.startswith("echo: M73 Progress:") and self.state == State.Printing
            ):
                _, pct = line.removesuffix(";").split("Progress: ")
                self.percent_done = int(pct.removesuffix("%"))
                self.recorder.printing(
                    self.file, self.percent_done, self.time_remaining_mins
                )

            #  Time left: 30m;
            elif line.startswith(" Time left:") and self.state == State.Printing:
                _, friendly = line.removesuffix(";").split(": ")
                # deal with eg 1h 30m
                self.time_remaining_mins = 0
                for section in friendly.split(" "):
                    if not section.endswith("h") and not section.endswith("m"):
                        self.logger.warning(
                            f"not sure how to parse section of time string: {section}"
                        )
                        continue

                    mult = 60 if section.endswith("h") else 1
                    self.time_remaining_mins += (
                        int(section.removesuffix("h").removesuffix("m")) * mult
                    )
                self.recorder.printing(
                    self.file, self.percent_done, self.time_remaining_mins
                )

            # File opened: /usb/ARIA/TEST~1.GCO Size:1280
            elif line[0:12] == "File opened:":
                file_name = line[13:-1].split(" ")[0]
                self.state = State.Printing
                self.file = file_name
                self.username = (
                    file_name.split("/")[2] if len(file_name.split("/")) > 3 else None
                )
                self.recorder.preprint(self.file)
                self.printer.send("M73")

            # Done printing file
            elif line.startswith("Done printing file"):
                if self.state == State.Printing:
                    self.on_complete()
                self.state = State.Idle

    def on_complete(self):
        self.recorder.print_finished()
        if self.username is not None:
            self.logger.info(f"attempting to find identity file for {self.username}")
            try:
                req = request.Request(
                    f"{self.api_base}/api/v1/files/usb/{self.username}",
                    headers={"x-api-key": self.api_key},
                )
                resp = request.urlopen(req)
                json_resp = json.load(resp)
                for child in json_resp["children"]:
                    name = child["display_name"]
                    self.logger.debug(f"has file: {name}")
                    if name.startswith("config.discord..."):
                        self.logger.debug(f"found discord filename: {name}")
                        username = name.removeprefix("config.discord...").removesuffix(
                            ".gcode"
                        )
                        self.recorder.print_finished_found_discord_username(
                            username, self.file
                        )
            except Exception as e:
                self.logger.info(f"failed to get identify file: {e}")
