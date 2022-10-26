# TODO: ONLY SUPPORT NETWORK EXPORTER FOR NOW!
Use
```yaml
aurora_custom:
  serial_device: /dev/ttyUSB0
  inverter_addresses:
    - 2
    - 3
```
or(!):
```yaml
aurora_custom:
  exporter: http://127.0.0.1:8000
  inverter_addresses:
    - 2
    - 3
```
