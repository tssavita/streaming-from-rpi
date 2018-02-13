import socket
import time
import io
import struct
from PIL import Image
import picamera
import sys
import os
import threading
import adxl
import signal
import logging

# Counter and status variables
stop_signal = False 
button_press = False
counter = 0
stop = 0

# Variables to detect if an event has been detected 
event_detected = 0

# Variable to check if the image captured during the event has been successfully sent to the server
image_sent = 0

# Global socket objects and corresponding file objects
stream_socket = None
image_socket = None
stream_file = None 
image_file = None 

# Object for Camera module
camera = picamera.PiCamera()

# Object for accelerometer class, from adxl.py
adxl345 = adxl.ADXL345()

event_thread = None
streaming_thread = None
threads = []
timer_threads = []

class EventDetection(threading.Thread):
    def __init__(self, target, args=()):
        self.target = target
        self.args = args
        threading.Thread.__init__(self)
        # A flag to notify the thread that it should finish up and exit
        self.kill_received = False
        
    def run(self):
        self.target()


def connect(host, port, mode):
    print("Creating a socket and corresponding file object to connect to %s:%s", host, port)
    # logging.info("Creating a socket and corresponding file object to connect to %s:%s", host, port)

    global stop

    while stop != 1:
        try:
            # Connect a client socket to host:port 
            client_socket = socket.socket()
#            client_socket.timeout(10)
            print "Creating socket"
            client_socket.connect((host,port))
            print "Connecting with ", host, "and ", port
            # Making a file like object from the socket
            socket_file = client_socket.makefile(mode)
            print("Returning a socket and file object %d", port)
            # Returning the created socket and file object made out of socket
            return client_socket, socket_file
        except socket.error as e:
            print("connect(): socket error %s reconnecting", format(e))
            print "trying to reconnect...", stop
            logging.error("socket error %s reconnecting", format(e))
            logging.info("trying to reconnect...", stop)
            time.sleep(3)

def event_detection():
    global camera
    global image_file
    global image_socket
    global event_detected
    global image_sent
    global stop

    logging.info("Looking for an event occurrence")
    print("Looking for an event occurrence")

    stream = io.BytesIO()
    while stop != 1 and counter == 1: 
        axes = adxl345.getAxes(True)
        if (axes['x'] > 0.15):
            event_detected = 1
            break
        elif (counter != 1) or stop == 1:
            print("Returning from event_detection while loop")
            logging.info("Returning from event_detection while loop")
            return
    
    print("Event capturing")
    logging.debug("Event capturing")
    while stop != 1:
        try:
            camera.capture(stream, format='jpeg', use_video_port=True)
        except picamera.PiCameraError:
            continue
        break
        
    print("Image captured")
    logging.debug("Image captured")

    print "stream.tell", stream.tell()
    
    image_len = stream.tell()
    stream.seek(0)
    image = Image.open(stream)
    image.save('/home/pi/test.jpeg', 'JPEG')
#    print "image size", image.size()
    while stop != 1 and counter == 1:
        try:
            image_file.write(struct.pack('<L', 2))
            image_file.flush()

            print("Sent status update 2 to server: Starting to send image")
            logging.info("Sent status update 2 to server: Starting to send image")

            print "Image lenth, image_len"
            image_file.write(struct.pack('<L', stream.tell()))
            image_file.flush()

#            print "Image length sending", stream.tell()
            logging.info("Image length sending")
   
            stream.seek(0)
            image_file.write(stream.read())
            image_file.flush()

            print "Image sent"

            stream.seek(0)
            stream.truncate()
            image_file.write(struct.pack('<L', 0))
            image_file.flush()
    
            image_sent = 1

            print("Image sent")
            print("Exiting from the function")
            logging.debug("Exiting from the function")
            logging.debug("Exiting from the function")
    
            return 

        except socket.error as e: 
            print("socket error %s reconnecting", format(e))
            logging.error("socket error %s reconnecting", format(e))
            image_socket.close()
            image_socket, image_file = connect('192.168.0.12', 8005, 'wb')


def socket_close(server_socket, socket_file):
    if socket_file != None:
        print "signal(): Closing dest file object"
        try:
            socket_file.close()
            """This try-except block and replaced if signal(SIGPIPE, SIG_DFL) is used."""
        except IOError as e:
            print "signal(): file object error {}  closing".format(e)

    if server_socket != None:
        print "socket_close(): Closing ", server_socket
        try:
            server_socket.shutdown(socket.SHUT_RDWR)
            server_socket.close()
        except socket.error as e:
            print "signal(): socket error {} closing dest socket".format(e)
    return


# Function for signal - SIGINT 
def signal_handler(signal, frame):
    global camera
    
    global stream_socket
    global image_socket

    global stream_file
    global image_file

    global threads
    global stop

    stop = 1
    
    print "Ctrl+C pressed. Client preparing to close..."

    print "Attempting to close threads"
    for t in threads:
        print "Name of thread", t.getName()
#        t.kill_received = True
        t.join(1)
        print "Closed"
    print "Closing threads. Number of threads active ", threading.active_count()

    for t in timer_threads:
        t.cancel()
    print "Closing threads. Number of threads active ", threading.active_count()
    
    socket_close(stream_socket, stream_file)
    socket_close(image_socket, image_file)
    
    sys.exit(0)

    return
        
# event_thread = threading.Thread(target=event_detection, args = (camera, ))

def send_finish_status():
    logging.debug("Entered finish status")
    print("Entered finish status")
    global counter 
    global streaming_thread
    global image_file
    global image_socket
    global camera
    global threads
    global event_thread
    global streaming_thread
    global image_sent
    global event_detected
    global stop

    # Resetting variables that are being tracked
    counter = 0
    event_deteced = 0
    image_sent = 0
    while stop != 1:
        try:
            image_file.write(struct.pack('<L', 3))
            image_file.flush()
            break
        except socket.error as e:
            print "signal(): socket error {} closing dest socket".format(e)
            image_socket.close()
            image_socket, image_file = connect('192.168.0.12', 8005, 'wb')

#    camera.stop_recording()

    event_thread.join()
    streaming_thread.join()
    logging.debug("Closing down threads")
    print("Returning from send_finish_status")
    return

def button_event():
    # Function called when button is pressed
    global stop
    global counter 
    if (stop != 1):
        val = counter
        counter = (counter + 1) % 3
        logging.info("Counter value changed from %s to %s", val, counter)
        print("Counter value changed from {} to {}", val, counter)
        if (counter == 2):
            send_finish_status()
    return

def start_streaming():
    # Start recording, sending the output to the connection for 180
    # seconds, then stop
    global stream_file
    global stream_socket
    global image_file
    global image_socket
    global camera
    global counter
    global image_sent 
    global event_detected
    global stop

    while stop != 1 and counter == 1:
        try:
            camera.start_recording(stream_file, format='h264')
            while stop != 1 and counter == 1:
                camera.wait_recording(1)
            camera.stop_recording()
        except socket.error as e:
#            camera.wait_recording()
#            camera.stop_recording()
            print "signal(): socket error {} closing dest socket".format(e)
            stream_socket.close()
            stream_socket, stream_file = connect('192.168.0.12', 8001, 'wb')
            return
        except IOError as e:
           if e.errno == errno.EPIPE:
               print "Broken pipe"
        except picamera.PiCameraError:
            print "Try to restart camera when already running"
            return
    return


signal.signal(signal.SIGINT, signal_handler)
stream_socket, stream_file = connect('192.168.0.12', 8001, 'wb')
image_socket, image_file = connect('192.168.0.12', 8005, 'wb')


try:
# camera.CAPTURE_TIMEOUT = 20
    camera.resolution = (1280, 720)
    camera.framerate = 24
    time.sleep(1)
    
    button_thread1 = threading.Timer(10,button_event,args=())
    timer_threads.append(button_thread1)
#    button_thread1.daemon = True
    button_thread1.start()

    button_thread2 = threading.Timer(70,button_event,args=())
    timer_threads.append(button_thread2)
#    button_thread2.daemon = True
    button_thread2.start()

    button_thread3 = threading.Timer(90,button_event,args=())
    timer_threads.append(button_thread3)
#    button_thread3.daemon = True
    button_thread3.start()

    button_thread4 = threading.Timer(150,button_event,args=())
    timer_threads.append(button_thread4)
#    button_thread4.daemon = True
    button_thread4.start()

    while counter == 0:
        time.sleep(1)
    
    while counter != 0:
        if (counter == 1):
            try:
                logging.debug("Button pressed 1st time")
                print("Button pressed 1st time")
                image_file.write(struct.pack('<L', 1))
                image_file.flush()
                logging.info("Sent status update 1 to server: Starting to stream")
                print("Sent status update 1 to server: Starting to stream")
 
                event_thread = threading.Thread(target=event_detection, name="event_detection", args=())
                event_thread.start()
                threads.append(event_thread)
                streaming_thread = threading.Thread(target=start_streaming, name="streaming_thread", args = ())
                streaming_thread.start()
                threads.append(streaming_thread)

                while (counter == 1):
                    print("Looping to wait till the button is pressed for 2nd time %s", counter)
                    logging.debug("Looping to wait till the button is pressed for 2nd time %s", counter)
                    time.sleep(1)

                logging.debug("Looping out of the counter = 1 loop")
                print("Looping out of the counter = 1 loop")
                print("Number of threads active %d", threading.active_count())
                event_thread.join()
                streaming_thread.join()
                logging.debug("Closed threads")
                print("Closed threads")
                i = 0
                while (counter == 0):
                    logging.debug("Looping to wait till the button is pressed for 1st time again %s", counter)
                    print("Looping to wait till the button is pressed for 1st time again %s", counter)
                    time.sleep(1)
#                    i += 1
#                    if (i > 20):
#                        break
                logging.debug("Number of active threads when continuing to next iteration %s""", threading.active_count())
                print("Number of active threads when continuing to next iteration %s""", threading.active_count())
            except socket.error as e:
                print "signal(): socket error {} closing dest socket".format(e)
                image_socket.close()
                image_socket, image_file = connect('192.168.0.12', 8005, 'wb')

        logging.debug("Main function has ended")
        print("Main function has ended")
finally:
    logging.debug("number of threads active %s", threading.active_count())
    print("number of threads active %s", threading.active_count())
    # event_thread.join()
#    for t in threads:
#        t.join()
#    image_file.close()
#    image_socket.close()
#    stream_file.close()
#    stream_socket.close()
