from printer_status.status_recorder import StatusRecorder
from .printer import Printer as BasePrinter
from enum import StrEnum, Enum
import paho.mqtt.client as mqtt
import json
from logging import getLogger
from urllib import request
from urllib.parse import quote as url_quote
import math


# the voron is configured with:
# [mqtt]
# instance_name: voron
# status_objects:
#     print_stats
#     display_status
# status_interval: 5
# publish_split_status: False


class State(StrEnum):
    Standby = "standby"
    Printing = "printing"
    Paused = "paused"
    Complete = "complete"
    Error = "error"
    Cancelled = "cancelled"


class ParseMode(Enum):
    Normal = 1
    File = 2


class Printer(BasePrinter):
    # Status
    client: mqtt.Client
    topic_base: str
    status_topic: str

    prev_on_connect = mqtt.CallbackOnConnect

    state: State
    file: str
    total_duration_secs: float | None
    percent_progress: int
    username: str | None

    def __init__(self, config: dict[str, str | int], client: mqtt.Client):
        self.client = client
        self.topic_base = str(config["mqtt_topic_base"])
        self.status_topic = f"{self.topic_base}/klipper/status"
        self.led_topic = f"{self.topic_base}/leds"
        self.logger = getLogger(str(config["name"]))

        self.state = State.Standby
        self.file = "unknown"
        self.username = None
        self.total_duration_secs = None
        self.percent_progress = 0

        if client.on_connect is not None:
            self.prev_on_connect = client.on_connect
        client.on_connect = self.on_connect
        if client.is_connected():
            client.subscribe(self.status_topic)
            client.subscribe(self.led_topic)

        self.api_base = config["api_base"]
        with open(config["api_key_file"]) as f:
            self.api_key = f.read().strip()

        client.message_callback_add(self.status_topic, self.on_message)
        client.message_callback_add(self.led_topic, self.on_led_message)

    def on_connect(self, client: mqtt.Client, _userdata, _flags, _rc):
        if self.prev_on_connect is not None:
            (self.prev_on_connect)(client, _userdata, _flags, _rc)  # type:ignore

        if client.is_connected():
            client.subscribe(self.status_topic)
            client.subscribe(self.led_topic)

    def main_loop(self, recorder: StatusRecorder):
        recorder.not_printing()
        self.recorder = recorder
        pass  # rest handled by on_message

    def on_message(self, client, _userdata, msg: mqtt.MQTTMessage):
        payload = msg.payload.decode("utf-8")
        self.logger.debug(f"RECV: {payload}")

        payload = json.loads(payload)
        if "status" not in payload:
            return

        status = payload["status"]

        if "print_stats" in status:
            print_stats = status["print_stats"]

            if "filename" in print_stats:
                self.file = print_stats["filename"]
                self.username = (
                    self.file.split("/")[0] if len(self.file.split("/")) > 1 else None
                )

            if "state" in print_stats:
                old_state = self.state
                self.state = print_stats["state"]
                self.re_record(old_state)

        if "display_status" in status:
            display_status = status["display_status"]
            progress = display_status["progress"]
            percent_progress = int(float(progress) * 100.0)
            if percent_progress != self.percent_progress:
                self.percent_progress = percent_progress
                self.re_record(self.state)

    def re_record(self, old_state: State):
        match self.state:
            case State.Error | State.Cancelled | State.Standby | State.Complete:
                self.total_duration_secs = None
                self.percent_progress = 0
                if old_state == State.Printing:
                    self.on_complete()
                else:
                    self.recorder.not_printing()
            case State.Paused:
                self.recorder.paused()
            case State.Printing:
                if self.total_duration_secs is None:
                    try:
                        file_metadata = self.api_request(
                            f"server/files/metadata?filename={self.file}"
                        )
                        self.total_duration_secs = file_metadata["result"][
                            "estimated_time"
                        ]
                        self.logger.debug(
                            f"total duration in seconds: {self.total_duration_secs}"
                        )
                    except Exception as e:
                        self.logger.warning(f"unable to determine file total time: {e}")
                        self.total_duration_secs = 60 * 60

                assert self.total_duration_secs is not None
                time_remaining_mins = math.ceil(
                    (100.0 - float(self.percent_progress))
                    / 100.0
                    * float(self.total_duration_secs)
                    / 60.0
                )
                self.recorder.printing(
                    self.file, self.percent_progress, time_remaining_mins
                )

    def on_complete(self):
        self.recorder.print_finished()
        if self.username is not None:
            self.logger.info(f"attempting to find identity file for {self.username}")
            try:
                dir_api_resp = self.api_request(
                    f"server/files/directory?path=gcodes/{self.username}"
                )
                for file_json in dir_api_resp["result"]["files"]:
                    name = file_json["filename"]
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

    def api_request(self, url):
        req = request.Request(
            f"{self.api_base}/{url}",
            headers={"x-api-key": self.api_key},
        )
        resp = request.urlopen(req)
        return json.load(resp)

    def on_led_message(self, client, _userdata, msg: mqtt.MQTTMessage):
        msg = msg.payload.decode("utf-8")
        if msg == "1":
            script = "SET_FAN_SPEED FAN=caselight SPEED=0.5"
        else:
            script = "SET_FAN_SPEED FAN=caselight SPEED=0"
        self.api_request(f"printer/gcode/script?script={url_quote(script)}")
