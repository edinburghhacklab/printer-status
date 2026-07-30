import argparse
from time import sleep
from os import getenv
import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion
import json
import logging
import threading
from datetime import datetime

from .printers import mk3
from .status_recorder import MQTTStatusRecorder

logger = logging.getLogger()

name = None


def parse_args():
    p = argparse.ArgumentParser()

    p.add_argument("config", help="Path to a json config file")

    args = p.parse_args()

    return args.config


def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code.is_failure:
        logger.info(
            f"Failed to connect: {reason_code}. loop_forever() will retry connection"
        )
    else:
        logger.info("Connected to mqtt")


def on_disconnect(client, userdata, rc):
    if rc != 0:
        logger.error("Unexpected MQTT disconnection. Will auto-reconnect")


def main():
    client = mqtt.Client(callback_api_version=CallbackAPIVersion.VERSION2)
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.loop_start()
    client.connect("mqtt.hacklab")

    while not client.is_connected():
        sleep(0.2)

    logging.basicConfig(
        filename="log",
        level=logging.DEBUG if getenv("DEBUG", "") == "1" else logging.INFO,
    )
    sh = logging.StreamHandler()
    sh.formatter = logging.Formatter("%(levelname)s [%(name)s] %(message)s")
    logger.addHandler(sh)
    logger.info(f"START {datetime.now()}")

    config_path: str = parse_args()

    logger.info("Loading config")
    try:
        config = json.load(open(config_path))
    except Exception as err:
        logger.error(f"Could not load config: {err}")
        exit(-1)

    logger.info("Printer init")
    threads = []
    for printer_config in config["printers"]:
        recorder = MQTTStatusRecorder(
            client, printer_config["name"], printer_config["shortname"]
        )  # TODO
        match printer_config["type"]:
            case "mk3":
                printer = mk3.Printer(printer_config, recorder)
            case "disabled":
                continue
            case _:
                raise NotImplementedError(f"printer with type {printer_config['type']}")

        t = threading.Thread(target=printer.main_loop, args=(recorder,))
        threads.append(t)
        t.start()

    logger.info("Running")

    for t in threads:
        t.join()


if __name__ == "__main__":
    main()
