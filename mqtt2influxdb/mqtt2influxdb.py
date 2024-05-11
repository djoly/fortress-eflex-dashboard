import paho.mqtt.client as mqtt
from influxdb_client.client import write_api
from influxdb_client import InfluxDBClient, Point
from datetime import datetime, timezone
import argparse
import logging, logging.handlers, os
import json

logFilename = os.getenv('LOG_FILENAME', '../logs/mqtt2influxdb.out')

logger = logging.getLogger(__name__)
handler = logging.handlers.RotatingFileHandler(logFilename, maxBytes=524288, backupCount=5)

formatter = logging.Formatter(
    '%(asctime)s [%(name)-12s] %(levelname)-8s %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(int(os.getenv("LOG_LEVEL", logging.DEBUG)))

parser = argparse.ArgumentParser(description="Fortress eFlex MQTT Data InfluxDB Publish Shell")
parser.add_argument("--mqtt_host",help="The hostname of the MQTT server", default="localhost")
parser.add_argument("--mqtt_port",help="The port of the MQTT server", type=int, default=1883)
parser.add_argument("--mqtt_topic",help="The topic prefix the battery data is published to", default="eflexbatteries")
parser.add_argument("--mqtt_client_id", help="MQTT client id", default="")
parser.add_argument("--mqtt_keepalive", help="MQTT keepalive time", type=int, default=60)
parser.add_argument("--influxdbhost",help="The hostname of InfluxDb", default="http://localhost:8086")
parser.add_argument("--influxdbtoken",help="The API token for InfluxDb", required=True)
parser.add_argument("--influxdborg",help="The InfluxDB organization", default="eflex_data")
parser.add_argument("--influxdbbucket",help="The InfluxDB bucket", default="eflex_data")
parser.add_argument("-t", help="Test JSON parsing and writing",action="store_const", const=True, default=False)
parser.add_argument("-d", help="Enable debug logging of received mqtt messages", action="store_const", const=True, default=False)
args = parser.parse_args()

logger.info(f"Running with args: {args}")

# Example JSON
# [{'time': 1715029936, 'battery_id': '225056E9999', 'battery_number': 2, 'batteries_in_system': 13, 'battery_soc': 84, 'battery_voltage': 54.9, 'battery_current': -0.3, 'system_average_voltage': 54.8, 'pre_volt': 55.0, 'insulation_resistance': 65535, 'software_version': 4004, 'hardware_version': 'a', 'lifetime_discharge_energy': 140067, 'cell_voltages': [3328, 3429, 3425, 3425, 3439, 3448, 3429, 3443, 3441, 3414, 3439, 3427, 3446, 3433, 3433, 3428]}]
def write_data(battery_data: dict, hosturl: str, bucket: str, org: str, token: str):
    try:
        with InfluxDBClient(url=hosturl, token=token, org=org) as _client:
            with _client.write_api(write_options=write_api.WriteOptions(flush_interval=1500)) as _write_client:

                for data in battery_data:
                    ts = datetime.fromtimestamp(data["time"], timezone.utc)

                    # Write battery module level values
                    _write_client.write(bucket, org, Point("battery_measurements")
                        .tag("battery_id", data["battery_id"])
                        .field("voltage", data["battery_voltage"])
                        .field("current", data["battery_current"])
                        .field("soc", data["battery_soc"])
                        .time(ts)
                        )
                    
                    # Write cell voltages
                    for cell_num, cell_voltage in enumerate(data["cell_voltages"]):
                        _write_client.write(bucket, org, Point("battery_cell_voltages")
                        .tag("battery_id", data["battery_id"])
                        .tag("cell_num", cell_num + 1)
                        .field("voltage", cell_voltage)
                        .time(ts)
                        )

                _write_client.flush()
    except:
        logger.error("Error saving data to influxdb.",exc_info=1)


# The callback for when the client receives a CONNACK response from the server.
def on_connect(client: mqtt.Client, userdata, flags, rc, properties):
    logger.info("Connected with result code "+str(rc))

    # Subscribing in on_connect() means that if we lose the connection and
    # reconnect then subscriptions will be renewed.
    client.subscribe(args.mqtt_topic)

# The callback for when a PUBLISH message is received from the server.
def on_message(client, userdata, msg):
    data = json.loads(msg.payload)

    logger.debug(f'Got mqtt message on topic {msg.topic}. Will write data {data}')

    write_data(data, args.influxdbhost, args.influxdbbucket, args.influxdborg, args.influxdbtoken)

    
def main():
    try:

        client = mqtt.Client(client_id=args.mqtt_client_id, callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
        client.on_connect = on_connect
        client.on_message = on_message

        client.connect(args.mqtt_host, args.mqtt_port, args.mqtt_keepalive)

        # Blocking call that processes network traffic, dispatches callbacks and
        # handles reconnecting.
        # Other loop*() functions are available that give a threaded interface and a
        # manual interface.
        client.loop_forever()

    except:
        logger.error("Unexpected error", exc_info=1)
        return -1
    return 0

if __name__ == "__main__":
    main()