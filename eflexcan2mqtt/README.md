# Fortress Power eFlex CAN 2 MQTT Publisher

This python script can be used to publish eFlex battery data to a Mosquitto MQTT server.

NOTE: Not all data has been decoded yet.

## Running the Script


```
$ python can2mqtt.py --mqtt_host localhost --mqtt_port 1883 --mqtt_topic eflexbatterydata
```

## Run eFlex CAN bus data, mapping can0 to vcan (requires can-utils on Linux)

```
$ canplayer -I eflex-can-network-data.log vcan0=can0
```

