import asyncio
import logging, logging.handlers, os
from typing import List

from struct import unpack 
import can
from can.notifier import MessageRecipient

# Add __lt__() function to can.Message to sort by first data byte
can.Message.__lt__ = lambda self, other: self.data[0] < other.data[0]


#logFilename = os.getenv('LOG_FILENAME', '/var/log/app/eflex-data-publisher.out')
logFilename = os.getenv('LOG_FILENAME', 'eflex-data-publisher.out')

logger = logging.getLogger(__name__)
handler = logging.handlers.RotatingFileHandler(logFilename, maxBytes=524288, backupCount=5)

formatter = logging.Formatter(
    '%(asctime)s [%(name)-12s] %(levelname)-8s %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(int(os.getenv("LOG_LEVEL", logging.INFO)))

# Message process interval in seconds
MESSAGE_PROCESS_INTERVAL = 30

# 0x10X messages are sent by each battery, 11 messages in a row.
MSG_ID_10X_COUNT = 11

# 0x60X messages are sent by each battery, 7 messages in a row.
MSG_ID_60X_COUNT = 7

MSG_TYPE_10 = '10'
MSG_TYPE_60 = '60'

# Contains the relevant bytes from the most recently aggregated messages. The keys are the arbitration id (i.e. 0x101, 0x601, etc) 
compiled_message10X_data = {}
compiled_message60X_data = {}

# Contains lists for each 0x10X and 0x60X messages. The message data is compiled and saved to 
# the compiled_message_data map when complete and the aggregation list cleared.
# 
aggregated_messages = {}

#Timestamp of last aggregated messages. Key is the node_id or battery number.
timestamps: dict[str, float] = {}

# Timestamp of the last publish time for a given node id. This is used as a sanity check to
# ensure messages are not needlessly being republished if there's an interruption in the CAN
# messages.
published_timestamps: dict[str, float] = {}

# Message as logged: 101#08221100544603BB
# Bytes passed to this function: 2-8
# Message 8 of 0x10X messages contains the serial number.
#  - Byte 2: 22 -> 22
#  - Byte 3: 11 -> 11
#  - Byte 4: 00 -> 0
#  - Byte 5: 54 -> 54
#  - Byte 6: char value
#  - Bytes 7-8: parsed as two byte unsigned short/integer and zero filled to a length of four. 
def parse_serial(serial_bytes: List) -> str:
    parts = unpack(">cH", bytearray(serial_bytes[4:8]))
    return (hex(serial_bytes[0]).removeprefix('0x') 
    + hex(serial_bytes[1]).removeprefix('0x')
    + str(serial_bytes[2])
    + hex(serial_bytes[3]).removeprefix('0x')
    + str(parts[0], "UTF-8") 
    + str(parts[1]).zfill(4)
    )

# CAN Notifier callback listener. Handles messages, aggregates and compiles the data when all are
# received into a single array of bytes for processing.
# The battery number can be reliably determined by the last character of hexidecimal arbitration id.
#  - 0x101 is battery number 1 (or node id 1). 0x10D is battery number 13, etc.
#  - The battery number or node id is NOT the serial number, which should be used as the battery unique id, in case
#    battery order changes. Changing the order of the batteries in the battery network will cause battery numbers to
#    change.
def handle_message(msg: can.Message) -> None:

    message_id = hex(msg.arbitration_id)[2:5]
    node_id = str(int(message_id[-1], base=16))
    message_type = message_id[0:2]
    
    # If this is not a 10X or 60X message, ignore it.
    if (message_type != MSG_TYPE_10 and message_type != MSG_TYPE_60):
        return


    # Initialize a list for this message id if one doesn't exist yet.
    if (message_id not in aggregated_messages):
        aggregated_messages[message_id] = []

    aggregated_messages[message_id].append(msg)

    message_count = len(aggregated_messages[message_id])

    if (message_type == MSG_TYPE_10 and message_count == MSG_ID_10X_COUNT
        or message_type == MSG_TYPE_60 and message_count == MSG_ID_60X_COUNT
        ):

        # Ensure messages are sorted by the first data byte
        sorted_messages = sorted(aggregated_messages[message_id])
        compiled_data = []

        # Compile data bytes into single list and update compiled message data for the node id.
        for message in sorted_messages:
            compiled_data += message.data[1:8]

        # TODO: validate first bytes to ensure each message is there
        if (message_type == MSG_TYPE_10):
            compiled_message10X_data[node_id] = compiled_data

        if (message_type == MSG_TYPE_60):
            compiled_message60X_data[node_id] = compiled_data
            timestamps[node_id] = msg.timestamp

        # Reset aggregated message list to empty
        aggregated_messages[message_id] = []

    return

# Publishes battery data
def publish_battery_data(node_id: str, battery_data: dict, timestamp: float):

    if (node_id in published_timestamps and published_timestamps[node_id] == timestamp):
        logger.warning(f'Most recent data for battery {node_id} was already published at timestamp {timestamp}. Won\'t republish.')
        return

    print(battery_data)
    published_timestamps[node_id] = timestamp
    return

# Processes and formats the battery data from the raw compiled message bytes.
def process_battery_data(data10, data60) -> dict:
    battery_number, batteries_in_system, battery_voltage, battery_current, battery_soc = unpack('>BBHhB', bytearray(data10[0:7]))
    average_system_voltage, = unpack(">H", bytearray(data10[10:12]))
    software_version, hardware_version = unpack('>Hc', bytearray(data10[46:49]))
    cell_voltages = list(unpack('>HHHHHHHHHHHHHHHH', bytearray(data60[1:33])))
    pre_volt, insulation_resistance = unpack(">HH", bytearray(data10[35:39]))

    return {
        'battery_id': parse_serial(data10[49:56]),
        'battery_number': battery_number, 
        'batteries_in_system': batteries_in_system,
        'battery_soc': battery_soc,
        'battery_voltage': battery_voltage/10,
        'battery_current': battery_current/10,
        'system_average_voltage': average_system_voltage/10,
        'pre_volt': pre_volt/10,
        'insulation_resistance': insulation_resistance,
        'software_version' : software_version,
        'hardware_version' : str(hardware_version, 'UTF-8'),
        'lifetime_discharge_energy' : unpack('>I', bytearray(data10[31:35]))[0],
        'cell_voltages' : [ cell_voltages[15]] + cell_voltages[0:15 ] #Fortress eFlex BMS software appears to send the first cell last. Cells 2-16 are in order.
    }

# Processes data where both type 10X and type 60X messages have been aggregated and compiled.
def process_message_data(): 
    for node_id, data10 in compiled_message10X_data.items():
        if (node_id in compiled_message60X_data):
            battery_data = process_battery_data(data10, compiled_message60X_data[node_id])
            publish_battery_data(node_id, battery_data, timestamps[node_id])

    return

async def main() -> None:
    with can.Bus(
        interface="socketcan", channel="vcan0"
    ) as bus:
        reader = can.AsyncBufferedReader()
        logger = can.Logger("logfile.asc")

        listeners: List[MessageRecipient] = [
            handle_message,  # Callback function
            reader,  # AsyncBufferedReader() listener
            logger,  # Regular Listener object
        ]
        # Create Notifier with an explicit loop to use for scheduling of callbacks

            
        loop = asyncio.get_running_loop()
        notifier = can.Notifier(bus, listeners, loop=loop)
        
        while True:
            await asyncio.sleep(MESSAGE_PROCESS_INTERVAL)
            process_message_data()


        #Clean-up
        #notifier.stop()


if __name__ == "__main__":
    asyncio.run(main())
