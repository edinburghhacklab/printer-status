from printer_status.printers.printcore import PrintCorePrinter
from printer_status.status_recorder import StatusRecorder
import re
from enum import StrEnum, Enum

status_regex = re.compile(r"done: ([0-9]*).+?mins: ([0-9]*)")


class State(StrEnum):
    Paused = "paused"
    Printing = "printing"
    Idle = "complete"


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

    recorder: StatusRecorder

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

    def handle_msg(self, line: str):
        line = line.rstrip("\n")
        self.logger.debug(f"M: {self.mode} RECV: {line}")

        # Normal mode
        if self.mode == ParseMode.Normal:
            # Print Status echo: 'NORMAL MODE: Percent done: 32; print time remaining in mins: 8; Change in mins: -1'
            if line[0:11] == "NORMAL MODE":
                stats: regex.Match[str] = status_regex.search(line)  # type: ignore
                self.logger.debug(f"{stats.group(1)}, {stats.group(2)}")

                self.percent_done = int(stats.group(1))
                self.time_remaining_mins = int(stats.group(2))

                if self.percent_done == 0 and self.time_remaining_mins == 0:
                    self.recorder.preprint(self.file)
                else:
                    self.state = State.Printing
                    self.recorder.printing(
                        self.file, self.percent_done, self.time_remaining_mins
                    )

            # File opened: /JACOB/0.4/Cali-Dragon-Tiny_PLA.gcode Size: 467996
            elif line[0:12] == "File opened:":
                file_name = line[13:-1].split(" ")[0]
                self.state = State.Printing
                self.file = file_name
                self.username = (
                    file_name.split("/")[1] if len(file_name.split("/")) > 2 else None
                )
                self.recorder.preprint(self.file)

            # File Finished: 'Done printing file'
            elif line == "Done printing file":
                self.state = State.Idle
                self.percent_done = 100
                self.time_remaining_mins = 0
                # Don't clear file and CWD yet so we can try and ping the user on discord
                self.on_complete()

            # Print manually paused: '//action:paused'
            # Print paused automatically: 'echo:busy: paused for user'
            elif (
                line == "//action:paused"
                or line == "echo:busy: paused for user"
                and self.state != State.Paused
            ):
                self.state = State.Paused
                self.recorder.paused()
                self.on_complete()

            # Print cancelled
            elif line == "//action:cancel":
                self.state = State.Idle
                self.on_complete()

            elif line.startswith("Begin file list"):
                self.mode = ParseMode.File
                self.in_username_dir = False
                self.dir_depth = 0
            else:
                self.logger.debug(f"Unknown Recv")

        # File list mode
        elif self.mode == ParseMode.File:
            if line == "End file list":
                self.mode = ParseMode.Normal
                self.in_username_dir = False
                self.dir_depth = 0
            elif line.startswith("DIR_ENTER"):  # DIR_ENTER: /JACOB/ "jacob"
                self.dir_depth += 1
                if self.username is not None and self.username.lower() in line.lower():
                    self.logger.debug("in username dir")
                    self.in_username_dir = True
            elif line.startswith("DIR_EXIT"):
                self.dir_depth -= 1
                if self.dir_depth <= 0:
                    self.logger.debug("leaving username dir")
                    self.in_username_dir = False
                    self.dir_depth = 0
            elif self.in_username_dir and "config.discord..." in line:
                self.logger.debug(f"encountered identity file: {line}")
                _, _, long_name = line.split(" ")
                long_name = long_name.removeprefix('"').removesuffix('"')
                if long_name.startswith("config.discord..."):
                    self.logger.debug(f"found discord filename: {long_name}")
                    username = long_name.removeprefix("config.discord...").removesuffix(
                        ".gcode"
                    )
                    self.recorder.print_finished_found_discord_username(
                        username, self.file
                    )

    def on_complete(self):
        self.recorder.print_finished()
        if self.username is not None:
            self.logger.info(f"attempting to find identity file for {self.username}")
            self.printer.send_now("M20 L")
