# Fortress eFlex Dashboard

This project is a collection of scripts and dashboard that can be used to capture data from Fortress Power eFlex batteries for tracking and visualization in InfluxDB and Grafana.

DISCLAIMER: This project is in no way affiliated with Fortress Power. It comes with no warrantees or guarantees. Use at your own risk.

CAUTION: This project is a work in progress.

## Running the eflexcan2mqtt script

To run this script, you will need a canbus interface and channel, along with a mosquitto MQTT server.

Suggested setup:

1. Linux computer/server 
2. can-tools installed, if testing or developing
3. CAN hardware natively supported by socketcan

For real hardware:

```bash
$ sudo ip link set can0 up type can bitrate 250000
```

```bash
$ python3 eflexcan2mqtt.py --mqtt_host localhost --mqtt_port 1883 --mqtt_topic eflexbatteries --can_interface socketcan --can_channel can0
```


For testing and development, use socketcan and a virtual can channel.

```bash
$ sudo modprobe vcan
$ sudo ip link add dev vcan0 type vcan
$ sudo ip link set vcan0 up
$ python3 eflexcan2mqtt.py --mqtt_host localhost --mqtt_port 1883 --mqtt_topic eflexbatteries --can_interface socketcan --can_channel vcan0
```

Then, use canplayer to playback a can log of real eflex battery messages:

```bash
$ canplayer -I eflex-test-msgs.log vcan0=can0

```


## Running the mqtt2influxdb script

```bash
$ python3 mqtt2influxdb.py --mqtt_host localhost --mqtt_port 1883 --mqtt_topic eflexbatteries --influxdbhost http://localhost:8086 --influxdbtoken influxdb-api-token --influxdborg eflex_data --influxdbbucket eflex_data
```


## Flux Data Query examples

### Lookup basic battery measurements

```
from(bucket:"eflex_data")
|>range(start:-1w)
|>filter(fn: (r) => r._measurement == "battery_measurements" )
```

### Lookup cell voltages

```
from(bucket:"eflex_data")
|>range(start:-1w)
|>filter(fn: (r) => r._measurement == "battery_cell_voltages" )
```

```
from(bucket:"eflex_data")
|>range(start:-1w)
|>filter(fn: (r) => r._measurement == "battery_cell_voltages" and r.battery_id == "2205054E9999")
```

