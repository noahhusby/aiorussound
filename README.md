<div align="center">

# aiorussound

#### An async python package for interfacing with Russound RIO hardware

[**📖 Read the docs »**][docs]

[![](https://github.com/noahhusby/aiorussound/actions/workflows/publish.yml/badge.svg)](https://github.com/noahhusby/aiorussound/actions/workflows/build.yml)
[![](https://img.shields.io/github/license/noahhusby/aiorussound)](https://github.com/noahhusby/aiorussound/blob/main/LICENSE)
[![](https://img.shields.io/pypi/implementation/aiorussound
)](https://pypi.org/project/aiorussound/)
[![](https://img.shields.io/pypi/v/aiorussound
)](https://pypi.org/project/aiorussound/)
[![](https://img.shields.io/pypi/dm/aiorussound
)](https://pypi.org/project/aiorussound/)

</div>

This module implements a Python client for the Russound I/O (RIO) protocol used to control Russound audio controllers. RIO supports a superset of the RNET feature set, allows for push notifications of system changes and supports TCP/IP and RS232 communication.

## Supported Devices
- Russound MBX-PRE
- Russound MBX-AMP
- Russound MCA-C3
- Russound MCA-C5
- Russound MCA-66
- Russound MCA-88
- Russound MCA-88x
- Russound XSource (untested)
- Russound XZone4 (untested)
- Russound XZone70V (untested)
- Russound XStream-X5 (untested)
- Russound ACA-E5 (untested)

If your model is not on the list of supported devices, and everything works correctly then add it to the list by opening a pull request.

## Communication
The library supports the RIO protocol communication over TCP/IP or RS232 (Serial). 

### TCP/IP
The built-in ethernet port on the Russound device natively support the RIO protocol. **Note:** It is strongly recommended that the controller has a static IP address configured.

### RS232 (Serial)

The RS232 port must be configured to use the RIO protocol instead of the RNET protocol for the library to function properly. This can be configured using the SCS-C5 configuration tool or the controller's Web GUI.

## Acknowledgements
This is the continuation of the `russound_rio` package. This wouldn't be possible without the excellent work from [@wickerwaka](https://github.com/wickerwaka) and [@chphilli](https://github.com/chphilli).

[docs]: https://noahhusby.github.io/aiorussound/
