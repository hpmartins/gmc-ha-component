# GMC Radiation Counter Integration for Home Assistant

A Home Assistant integration for GQ GMC Geiger Counter devices.

## Features

- Real-time radiation monitoring (CPM and µSv/h)
- Battery voltage monitoring
- Automatic unit conversion from CPM to µSv/h

## Supported Devices

- My GMC-300S
- Probably other GMC devices that follow the GQ-RFC1201 protocol specification

## Installation

1. Install via HACS:
   - Add this repository as a custom repository in HACS
   - Search for "GMC Radiation Counter" and install

2. Restart Home Assistant

3. Go to Settings -> Devices & Services -> Add Integration
   - Search for "GMC Radiation Counter"
   - Follow the setup wizard

## Configuration

The integration needs:
- Serial port (e.g., `/dev/ttyUSB0`)
- Baud rate (default: 57600)

## Sensors

- **CPM**: Counts per minute
- **Radiation Dose Rate**: Radiation level in µSv/h
- **Battery Voltage**: Device battery level in volts

## Support

For issues and feature requests, please use the [GitHub issue tracker](https://github.com/hpmartins/gmc-ha-component/issues).
