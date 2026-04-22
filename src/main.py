import argparse
import time
import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion
import json
import logging
from datetime import datetime

from printers.printer import Printer

client = mqtt.Client(callback_api_version=CallbackAPIVersion.VERSION2)
client.connect("mqtt.hacklab")

logger = logging.getLogger()

name = None

printers = []


def parse_args():
    p = argparse.ArgumentParser()

    p.add_argument("config", help="Path to a json config file")

    args = p.parse_args()

    return args.config


def main():
    # Write to log file
    logging.basicConfig(filename="log", level=logging.DEBUG)
    # Write to stderr
    sh = logging.StreamHandler()
    sh.formatter = logging.Formatter("%(levelname)s:%(name)s:%(message)s")
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

    for printer_config in config["printers"]:
        printer = Printer(printer_config, client)
        printer.connect()
        printers.append(printer)

    logger.info("Running")

    while True:
        time.sleep(10)


if __name__ == "__main__":
    main()
