import argparse
import json
import sys
import requests
import threading
import time
import logging
from datetime import datetime

from src.consumer import ConsumerKafka, ConsumerFile, ConsumerFileKafka

from multiprocessing import Process


def ping_watchdog(process: Process) -> None:
    """
    Function to ping the watchdog at regular intervals.

    Args:
        process (Process): The child process to monitor.

    Returns:
        None
    """
    interval = 30 # ping interval in seconds
    url = "localhost"
    port = 5001
    path = "/pingCheckIn/Data adapter"

    while(process.is_alive()):
        print("{}: Pinging.".format(datetime.now()))
        try:
            r = requests.get("http://{}:{}{}".format(url, port, path))
        except requests.exceptions.RequestException as e:  # This is the correct syntax
            logging.warning(e)
        else:
            logging.info('Successful ping at ' + time.ctime())
        time.sleep(interval)

def start_consumer(args: argparse.Namespace) -> None:
    """
    Function to start the consumer based on the command line arguments.

    Args:
        args (argparse.Namespace): Parsed command line arguments.

    Returns:
        None
    """
    if(args.data_file):
        consumer = ConsumerFile(configuration_location=args.config)
    elif(args.data_both):
        consumer = ConsumerFileKafka(configuration_location=args.config)
    else:
        consumer = ConsumerKafka(configuration_location=args.config)

    print("=== Service starting ===", flush=True)
    consumer.read()

def main() -> None:
    """
    Main entry point of the program.

    Returns:
        None
    """
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s', datefmt='%d-%b-%y %H:%M:%S')
    parser = argparse.ArgumentParser(description="consumer")

    parser.add_argument(
        "-c",
        "--config",
        dest="config",
        default="config1.json",
        help=u"Config file located in ./config/ directory."
    )

    parser.add_argument(
        "-f",
        "--file",
        dest="data_file",
        action="store_true",
        help=u"Read data from a specified file on specified location."
    )

    parser.add_argument(
        "-fk",
        "--filekafka",
        dest="data_both",
        action="store_true",
        help=u"Read data from a specified file on specified location and then from kafka stream."
    )

    parser.add_argument(
        "-w",
        "--watchdog",
        dest="watchdog",
        action='store_true',
        help=u"Ping watchdog",
    )

    # Display help if no arguments are defined
    if (len(sys.argv) == 1):
        parser.print_help()
        sys.exit(1)

    # Parse input arguments
    args = parser.parse_args()

    # Ping watchdog every 30 seconds if specfied
    if (args.watchdog):
        # Run and save a parelel process
        # Start periodic download
        process = Process(target=start_consumer, args=(args,))
        process.start()

        # On the main thread ping watchdog if child process is alive
        print("=== Watchdog started ==", flush=True)
        ping_watchdog(process)
    else:
        start_consumer(args)




if (__name__ == '__main__'):
    main()
