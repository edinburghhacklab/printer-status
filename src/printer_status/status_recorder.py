from abc import ABC, abstractmethod
from paho.mqtt import client as mqtt
import json
import random


class StatusRecorder(ABC):
    @abstractmethod
    def print_finished(self):
        pass

    @abstractmethod
    def print_finished_found_discord_username(self, username: str, file: str):
        pass

    @abstractmethod
    def paused(self):
        pass

    @abstractmethod
    def not_printing(self):
        pass

    @abstractmethod
    def preprint(
        self,
        filename: str | None,
    ):
        pass

    @abstractmethod
    def printing(
        self,
        filename: str | None,
        percent_done: int | None,
        time_remaining_mins: int | None,
    ):
        pass


class MQTTStatusRecorder(StatusRecorder):
    short_name: str
    client: mqtt.Client

    def __init__(self, client: mqtt.Client, name: str, short_name: str):
        self.name = name
        self.short_name = short_name
        self.debug = DebugStatusRecorder(short_name)
        self.client = client

    def print_finished(self):
        # Make the TTS happy
        SUBSTITUTIONS = {
            "voron": "vore on",
            "prusheen": "proosheen",
            "blusa": "bloosha",
            "pink prusa club": "pink proosha club",
        }
        name = SUBSTITUTIONS.get(self.name.lower(), self.name.lower())

        message = random.choices(
            [
                f"Print finished on {name}",
                f"Spaghetti detected on {name}",
                f"Bo gos binted on {name}",
                f"{name} has completed the work, my liege",
                f"Wavelength pattern blue on {name}",
                f"A process has occured on {name}",
                f"Replicator reports job complete captain",
                f"Mr president, a second print has hit the {name}",
            ],
            weights=[
                6.5,
                1,
                1,
                1,
                1,
                1,
                1,
                0.5,
            ],
            k=1,
        )[0]
        self.client.publish(f"sound/g1/announce", message)
        self.not_printing()

    def print_finished_found_discord_username(self, username: str, file: str):
        self.debug.print_finished_found_discord_username(username, file)
        self.client.publish(
            "irc/send",
            json.dumps(
                {
                    "to": "#edinhacklab-things",
                    "message": f"@{username} print '{file}' complete on {self.name}",
                }
            ),
        )

    def paused(self):
        self.debug.paused()
        self.client.publish(f"printers/{self.short_name}/state", "Paused", retain=True)

    def not_printing(self):
        self.debug.not_printing()
        self.client.publish(f"printers/{self.short_name}/state", "Idle", retain=True)
        self.client.publish(
            f"printers/{self.short_name}/percent_done", str(0), retain=True
        )
        self.client.publish(
            f"printers/{self.short_name}/time_remaining_mins", str(0), retain=True
        )
        self.client.publish(f"printers/{self.short_name}/file", "unknown", retain=True)

    def preprint(
        self,
        filename: str | None,
    ):
        self.debug.preprint(filename)
        self.client.publish(
            f"printers/{self.short_name}/state", "Preprint", retain=True
        )
        self.client.publish(
            f"printers/{self.short_name}/percent_done", str(0), retain=True
        )
        self.client.publish(
            f"printers/{self.short_name}/time_remaining_mins", str(0), retain=True
        )
        self.client.publish(
            f"printers/{self.short_name}/file", filename or "unknown", retain=True
        )

    def printing(
        self,
        filename: str | None,
        percent_done: int | None,
        time_remaining_mins: int | None,
    ):
        self.debug.printing(filename, percent_done, time_remaining_mins)
        self.client.publish(
            f"printers/{self.short_name}/state", "Printing", retain=True
        )
        self.client.publish(
            f"printers/{self.short_name}/percent_done",
            str(percent_done or 0),
            retain=True,
        )
        self.client.publish(
            f"printers/{self.short_name}/time_remaining_mins",
            str(time_remaining_mins or 0),
            retain=True,
        )
        self.client.publish(
            f"printers/{self.short_name}/file", filename or "unknown", retain=True
        )


class DebugStatusRecorder(StatusRecorder):
    name: str

    def __init__(self, name: str):
        self.name = name

    def preprint(
        self,
        filename: str | None,
    ):
        print(f"{self.name}: preparing to print {filename}")

    def print_finished(self):
        print(f"{self.name}: finished")
        self.not_printing()

    def print_finished_found_discord_username(self, username: str, file: str):
        print(f"{self.name}: finished {file} for {username}")

    def paused(self):
        print(f"{self.name}: paused")

    def not_printing(self):
        print(f"{self.name}: not printing")

    def printing(
        self,
        filename: str | None,
        percent_done: int | None,
        time_remaining_mins: int | None,
    ):
        print(
            f"{self.name}: printing {filename} - {percent_done}% done with {time_remaining_mins}m remaining"
        )
