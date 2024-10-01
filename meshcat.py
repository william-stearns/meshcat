#!/usr/bin/env python3
"""meshcat: Connect to a meshtastic node, then route all incoming lines of text to it and display all lines coming back from it."""

#Copyright 2023 William Stearns <william.l.stearns@gmail.com>
#Released under the GPL


__version__ = '0.0.6'

__author__ = 'William Stearns'
__copyright__ = 'Copyright 2024, William Stearns'
__credits__ = ['William Stearns']
__email__ = 'william.l.stearns@gmail.com'
__license__ = 'GPL 3.0'
__maintainer__ = 'William Stearns'
__status__ = 'Development'					#Prototype, Development or Production


#Sample uses:
# meshcat.py							#Directly send messages to and listen to messages from the mesh
# meshcat.py -w 1.2.3.4						#Directly send messages to and listen to messages from the mesh using a meshtastic node at 1.2.3.4
# ( echo 'Please reply with your names' ; sleep 60 ) | meshcat.py	#Ask a question and wait for up to 60 seconds for replies


#======== External libraries
import sys							#Used for reading from stdin/writing to stdout
from typing import Optional
try:
    from meshtastic import BROADCAST_NUM
    from meshtastic.util import convert_mac_addr
    import meshtastic.serial_interface
    import meshtastic.tcp_interface
    import meshtastic.ble_interface
except ImportError:
    print("Missing meshtastic module; perhaps 'sudo port install meshtastic' or 'sudo -H pip install meshtastic' ?  Exiting.")
    raise

try:
    from pubsub import pub
except ImportError:
    print("Missing pubsub module; perhaps 'sudo port install pubsub' or 'sudo -H pip install pubsub' ?  Exiting.")
    raise


#======== Global variables
Devel = True


#======== Functions
def Debug(DebugStr: str) -> None:
    """Prints a note to stderr"""

    if Devel:
        sys.stderr.write(DebugStr + '\n')


def onReceive(packet, interface) -> None:			# pylint: disable=unused-argument
    """Process a packet that arrived from the meshtastic node."""

    try:
        node_id = packet.get('id', 'N/A')
        from_num = packet.get('from', 0)
        if (remote_num and from_num == remote_num) or not remote_num:	# pylint: disable=possibly-used-before-assignment
            if 'decoded' in packet:
                port = packet['decoded'].get('portnum', 'N/A')
                if port == 'NODEINFO_APP':
                    node_info = packet['decoded'].get('user', {})
                    long_name = node_info.get('longName', 'N/A')
                    short_name = node_info.get('shortName', 'N/A')
                    mac_addr = convert_mac_addr(node_info.get('macaddr', '/'))
                    hw_model = str(node_info.get('hwModel', 'N/A'))
                    sys.stderr.write('__nodeinfo: ' + long_name + '/' + short_name + '/' + mac_addr + '/' + hw_model)
                    sys.stderr.flush()
                elif port == 'POSITION_APP':
                    if 'position' in packet['decoded']:
                        lat = packet['decoded']['position'].get('latitudeI', 'N/A')
                        if lat != 'N/A':
                            lat = lat / 10000000
                        lon = packet['decoded']['position'].get('longitudeI', 'N/A')
                        if lon != 'N/A':
                            lon = lon / 10000000
                        sys.stderr.write('__position: ' + str(node_id) + ': ' + str(lat) + ', ' + str(lon))
                        sys.stderr.flush()
                elif port == 'ROUTING_APP':
                    pass
                elif port == 'TELEMETRY_APP':
                    pass
                elif port == 'TEXT_MESSAGE_APP':
                    message_bytes = packet['decoded']['payload']
                    message_string = message_bytes.decode('utf-8')
                    print(f"{message_string}")
                    sys.stdout.flush()
                else:
                    print()
                    print("Decoded packet: " + str(packet))
                    print()
            else:
                pass
                #print()
                #print("Undecoded packet: " + str(packet))
                #print()
    except KeyError as e:
        Debug(f"Error processing packet: {e}")


def send_data(raw_data: bytes, remid:Optional[int], mt_h) -> None:
    """Send raw data that arrived on stdin out onto the mesh."""

    if remid is not None:
        mt_h.sendData(raw_data, destinationId=remid)
    else:
        mt_h.sendData(raw_data, destinationId=BROADCAST_NUM)


def send_message(message: str, remid:Optional[int], mt_h) -> None:
    """Send a text message line that arrived on stdin out onto the mesh."""

    if remid is not None:
        mt_h.sendText(message, destinationId=remid)
    else:
        mt_h.sendText(message, destinationId=BROADCAST_NUM)


max_binary_read_bytes: int = 200


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='meshcat.py version ' + str(__version__) + ': This passes stdin data to a meshtastic net, and sends incoming data from that net to stdout.')
    parser.add_argument('-b', '--binary', help='Binary/raw input', required=False, default=False, action='store_true')
    parser.add_argument('-r', '--remote', help='ID of a single remote node to send to/receive from (nodeId or nodeNum in single quotes; get the nodeId from "meshtastic --nodes" in the "ID" column, or the "Node Number" in the node detail in the smartphone app)', required=False, default='')
    parser.add_argument('-w', '--wifi', help='Hostname or IP of the meshtastic radio if connecting over WIFI', required=False, default='')
    parser.add_argument('--bluetooth', help='Address of the meshtastic radio if connecting over Bluetooth (get address from "meshtastic --ble-scan")', required=False, default='')
    args = vars(parser.parse_args())

    if args['wifi']:
        mt_interface = meshtastic.tcp_interface.TCPInterface(hostname=args['wifi'])
    elif args['bluetooth']:
        mt_interface = meshtastic.ble_interface.BLEInterface(args['bluetooth'])
    else:
        mt_interface = meshtastic.serial_interface.SerialInterface()

    remote_num: Optional[int] = None
    if args['remote']:
        if args['remote'][0] == '!':
    	    remote_num = int(args['remote'].replace('!', ''), 16)
        else:
            remote_num = int(args['remote'])

    pub.subscribe(onReceive, 'meshtastic.receive')

    must_exit: bool = False
    in_bytes: bytes
    one_line: str

    while not must_exit:
        try:
            if args['binary']:
                in_bytes = sys.stdin.buffer.read(max_binary_read_bytes)
                if len(in_bytes) == 0:
                    must_exit = True
                else:
                    send_data(in_bytes, remote_num, mt_interface)
            else:
                for one_line in sys.stdin:
                    send_message(one_line.rstrip(), remote_num, mt_interface)	# We use rstrip since .sendText() adds a linefeed.
        except KeyboardInterrupt:
            must_exit = True

    if mt_interface:
        try:
            mt_interface.close()
        except AttributeError:					# Shows up when no serial interface detected, so there's no problem if we can't close it.
            pass
