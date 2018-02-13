import socket
from timeit import default_timer as timer
import signal
import sys
import time
import subprocess
import threading
import struct
from PIL import Image
import io

status = 0
start_streaming = 0
stop = 0

gui1_socket = None
gui1_listening = None

server_socket = None
server_listening = None

image_socket = None
image_listening = None

image_recv_thread = None
gui1_conn_thread = None

def socket_close(client_socket):
    if client_socket != None:
        print "socket_close(): Closing", 
        try:
            client_socket.shutdown(socket.SHUT_RDWR)
            client_socket.close()
        except socket.error as e:
            print "signal(): socket error {} closing dest", format(e) 

def set_keepalive_linux(sock, after_idle_sec=1, interval_sec=3, max_fails=5):
    """Set TCP keepalive on an open socket.

    It activates after 1 second (after_idle_sec) of idleness,
    then sends a keepalive ping once every 3 seconds (interval_sec),
    and closes the connection after 5 failed ping (max_fails), or 15 seconds
    """
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, after_idle_sec)
    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, interval_sec)
    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, max_fails)

def signal_handler(signal, frame):
    global server_socket
    global server_listening

    global gui1_socket
    global gui1_listening

    global image_socket
    global image_listening

    global image_recv_thread
    global gui1_conn_thread

    global stop

    stop = 1

    print "Ctrl+C pressed. Client preparing to close..."
    print "Attempting to close threads"
    
    if (image_recv_thread != None):
        image_recv_thread.join()
    print "closed image_rcv_thread"

    socket_close(image_socket)
    socket_close(image_listening)
    socket_close(server_socket)
    socket_close(server_listening)
    socket_close(gui1_socket)
    socket_close(gui1_listening)
    print "closed all sockets"
    
    if (gui1_conn_thread != None):
        gui1_conn_thread.join()
    print "gui conn thread"

    sys.exit(0)

def reconnect(listening_socket):
    listening_socket.settimeout(1)

    rw_socket = None
    while not stop:
        try:
            rw_socket = listening_socket.accept()[0]
            set_keepalive_linux(rw_socket, 1, 3, 5)
        except Exception as exc:
            print "Socket reconnect accpet Exception"
        else:
            print "Socket reconnect done"
            break

    listening_socket.settimeout(None)

    print "connect(): Returning server file object for "
    return rw_socket 


def connect(port, mode):
    global stop

    while stop != 1:
        print "connect(): Entering while loop for", port
        try:
            sock = socket.socket()
            print "created ", port
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            print "provison for reuse address set ", port
            sock.bind(('0.0.0.0', port))
            print "binding on port ", port
            sock.listen(0)
            print "listening ", port
            rw_socket = sock.accept()[0]
            set_keepalive_linux(rw_socket, 1, 3, 5)
            print "connect(): Returning server file object for ", port
            return rw_socket, sock
        except socket.error as e:
            print port
            print ("connect(): socket error {} reconnecting".format(e))
            time.sleep(3)
    return

def connect_gui1(port, mode):
    global gui1_socket
    global gui1_listening
    global stop
    while stop != 1:
        print "connect(): Entering while loop"
        try:
            gui1_listening = socket.socket()
            gui1_listening.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            gui1_listening.bind(('0.0.0.0', port))
            gui1_listening.listen(0)
            gui1_socket = gui1_listening.accept()[0]
            print "connect(): Returning server file object for ", port
            return
        except socket.error as e:
            print ("connect(): socket error {} reconnecting".format(e))
            time.sleep(3)
    return




def check_status():
    print  """check_status(): Listening to status update from Pi"""
 
    global image_socket
    global status
    global start_streaming
    global stop

    while stop != 1:
        try:
            status_length = recvall(image_socket, struct.calcsize('<L'))
            if not len(status_length):
                image_socket.close()
                image_socket = reconnect(image_listening)
            if status_length:
                status = struct.unpack('<L', status_length)[0]
                if (status == 1):
                    start_streaming = 1
                elif (status == 2):
                    receive_event_image()
                elif (status == 3):
                    print "check_status(): SEQUENCE Complete. Waiting for next button press..."
        except socket.error as e:
            print ("main(): socket error {} reconnecting".format(e))
            image_socket.close()
            image_socket = reconnect(image_listening)
    
    print "Going to return from check_status"
    return

def recvall(sock, size):

    """Read size amount of data from the connection"""
    sock.settimeout(5)   # pylint: disable=no-member
    output = ''
    
    while len(output) < size and stop != 1:
        try:
            buff = sock.recv(size - len(output))
        except socket.timeout as exc:
            continue
        except Exception as exc:
            output = ''
            break
        if not buff:
            output = ''
            break
        else:
            output += buff
    if len(output) != size:
        output = ''
    sock.settimeout(None)   # pylint: disable=no-member
    return output

def receive_event_image():

    global image_listening
    global image_socket

    print """receive_event_image(): Event detected, image being received"""
    while stop != 1 and status == 2:
        print "Image while"
        try:
            read_length = image_socket.recv(struct.calcsize('<L'))

            image_len = 0
            if not len(read_length):
                image_socket.close()
                image_socket = reconnect(image_listening)
            image_len = struct.unpack('<L', read_length)[0]
            print ('image_len %d' % image_len)
            image_stream = io.BytesIO( )

#            image_string = image_socket.recv(image_len)
            image_string = recvall(image_socket, image_len)
#            image_stream.write(image_socket.recv(image_len))
            image_stream.write(image_string)

#            while (image_stream.tell() < image_len):
#                more = image_len - image_stream.tell()
#                image_stream.append(image_socket.recv(more))a
#                
            if not image_stream.tell():
                image_socket.close()
                image_socket = reconnect(image_listening)
#            image_stream = io.BytesIO(image_string)
            image = Image.open(image_stream)
            image.save('test.jpeg', 'JPEG')
            # print('Image is %dx%x' % image.size)
            image.verify()
            print """receive_event_image(): Image is verified"""
            return
        except socket.error as e:
            print ("main(): socket error {} reconnecting".format(e))
            image_socket.close()
            print "checkstatus except, going to be 8005 created"
            image_socket = reconnect(image_listening) 
            print "receive_image: except body, 8005 created again"
    
    return

# def read_streaming():
#     while True:
#         if start_streaming == 1:
#             data = connection.read(1024)
#             if not data:
#                 break
#            gui1_conn.write(data)
#     return

def sending_gui1():
    global gui1_listening
    global gui1_socket
    global data
    global start_streaming

    while (start_streaming != 1):
        time.sleep(1)
    while True:
        time.sleep(0.5)
        if len(data):
            print "Entering in gui1 sending method ", len(data)
            try:
                gui1_socket.write(data)
                print "written to gui1"
                data_prev = data
            except socket.error as e: 
                print ("main(): gui_socket error {} reconnecting".format(e))
                gui1_socket.close()
                connect_gui1(8010, 'wb')

    return

signal.signal(signal.SIGINT, signal_handler)
gui1_conn_thread = threading.Thread(target = connect_gui1, args = (8010, 'wb'))
gui1_conn_thread.start()
server_socket, server_listening = connect(8001, 'rb')
image_socket, image_listening = connect(8005, 'rb') 
data = ""
    
image_recv_thread = threading.Thread(target = check_status, args = ())
image_recv_thread.start()

try:

    # sending_gui1_thread = threading.Thread(target = sending_gui1, args = ())
    # sending_gui1_thread.start()

    # Change this to something like, if image_connection is still open, then continue the streaming.
    while stop != 1:
        if (start_streaming == 1):
            try: 
                data = recvall(server_socket, 1024)
                if not data:
                    server_socket.close()
                    server_socket = reconnect(server_listening)
            except socket.error as e:
                print ("main(): conn_socket error {} reconnecting".format(e))
                server_socket.close()
                server_socket = reconnect(server_listening)
            if len(data):
                try:
                    gui1_socket.send(data)
                except socket.error as e:
                    gui1_socket.close()
                    gui1_socket = reconnect(gui1_listening)
    print """main() try: Exiting try block"""
finally:
    print """main(): finally: closing down event detection thread, as well as connections"""
    gui1_conn_thread.join()
    print "Closing gui thread"
    image_recv_thread.join()
    print """main(): number of threads active""", threading.active_count()
    print """main - finally: closing sockets"""
    gui1_listening.close()
    gui1_socket.close()
    server_socket.close()
    server_listening.close()
    image_socket.close()
    image_listening.close()

