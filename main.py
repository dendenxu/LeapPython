# MIT License
# 
# Copyright (c) 2021 dendenxu
# 
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
# 
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.


# imports, don't change theses unless necessary
import json  # for some object communification
import time  # used for some timing and performance profiling

import threading
from threading import Thread, Lock  # Python-Mulitithreading. Though GIL (Global Interpreter Lock) exist, we can still utilize this for some multitasking and synchronization

from glumpy import app, gl, glm, gloo, __version__  # the easy to use python OpenGL framework

from hand import Hand  # Leap Motion Driver object: Hand, including arm
from beacon import Beacon  # Serial Communication beacon, for all in one serial control
from gesture import GestureParser  # Hand/Arm gesture parser, implements gestures to voltage/angle transformation

import asyncio  # used only for the websocket implementation
import websockets  # websocket interface
# Note: we've also tried the websocket-client (import websocket), but it performs so poorly that it's nearly unusable

from log import log  # for some timestamped logging
import numpy as np  # used here only to log the beacon


# Init Control, whether to simulate an Arduino device or not
ENABLE_BEACON = True


# Some multithreading intervals, should be careful not to busy wait too much considering GIL
READ_INTERVAL = 0  # global constant: extra time to wait after one reading loop


# Global Threading States, updated dynamically
# * main thread: renderer thread
stop_websocket = False  # used only once, to stop the websocket thread
stop_parser = False  # used only once, to stop the parser thread
stop_beacon = False  # used only once, to stop the reader thread
update_hand_obj = True  # can be used repeatedly, to pause or resume receiving WebSocket information from the Leap Motion Controller


# Device Control, updated dynamically
device_ready = False  # whether the MCU said he's ready after we've sent a command
arduino_fps = 0  # the loop time received from the MCU, updated upon receiving
parse_interval = 1/20  # extra time to wait after one parsing operation, updated with 1/parse_interval


# * the actual hand pool, stores global hand object, updated by sampler, used by renderer
hand_pool = [Hand() for _ in range(2)]  # the actual hand object
parser = [GestureParser(hand_pool[i], i) for i in range(2)]  # the gesture parsers
beacon = Beacon(port="COM8", baudrate=9600, enable=ENABLE_BEACON)  # the serial controller
log_file = open("output(decoded).txt", "w")  # used to log and debug outgoing device commands


def render(interactive=False):
    """
    The main thread rendering funciton for this application
    This takes care of the rendering, handling of window event
      - Console (information) update
      - Redrawing of the cubes representing the finger joints location
      - Resizing funcitons for all cubes (including debugging cube)
      - Handling of low-level OpenGL initialization / rendering
      - Key board event for some interesting interaction
      - Opening up the interactive python interpreter to give
        advanced user full control over the driver

    :param interactive: Whether the program should give user an 
    interactive python interpreter after the OpenGL window is loaded up
    """

    log.info(f"Runnning glfw renderer")

    app.use("glfw")  # setting OpenGL backend, you'll need glfw installed
    config = app.configuration.Configuration()
    config.samples = 16  # super sampling anti-aliasing
    console = app.Console(rows=32, cols=80, scale=3, color=(0.1, 0.1, 0.1, 1))  # easy to use info displayer
    global window  # to be used to close the window, declared as global var for interpreter to reference
    window = app.Window(width=console.cols*console.cwidth*console.scale, height=console.rows*console.cheight*console.scale, color=(1, 1, 1, 1), config=config)

    @window.timer(1/30.0)
    def timer(dt):
        # used every 1/30 second to update frame rate and stuff...
        console.clear()
        console.write("-------------------------------------------------------")
        console.write(" Glumpy version %s" % (__version__))
        console.write(" Window size: %dx%d" % (window.width, window.height))
        console.write(" Console size: %dx%d" % (console._rows, console._cols))
        console.write(" Backend: %s (%s)" % (window._backend.__name__,
                                             window._backend.__version__))
        console.write(" Actual FPS: %.2f frames/second" % (window.fps))
        console.write(" Arduino FPS: %.2f frames/second" % (arduino_fps))
        console.write(" Hit 'V' key to toggle bone view")
        console.write(" Hit 'P' key to pause or unpause")
        console.write("-------------------------------------------------------")
        for line in repr(window.config).split("\n"):
            console.write(" "+line)
        console.write("-------------------------------------------------------")

    @window.timer(1/30.0)
    def rotate(dt):
        # used every 1/30 to update the model matrix of all cubes, to check whether the program is frozen

        # Rotate cube
        for hand in hand_pool:
            model = hand.key_point.model
            glm.rotate(model, 1, 0, 0, 1)
            glm.rotate(model, 1, 0, 1, 0)
            hand.key_point.model = model

            model = hand.bone.model
            glm.rotate(model, 1, 0, 1, 0)
            hand.bone.model = model

    @window.event
    def on_draw(dt):
        # on every window refresh, redraw the OpenGL program on the screen
        window.clear()
        console.draw()
        parser[1].debug_cube.draw()

        for hand in hand_pool:
            hand.draw()

    @window.event
    def on_resize(width, height):
        # when the user resizes the window, update the OpenGL program
        parser[1].debug_cube.resize(width, height)
        for hand in hand_pool:
            hand.resize(width, height)

    @window.event
    def on_init():
        # init the OpenGL parameters
        gl.glEnable(gl.GL_DEPTH_TEST)  # enable depth buffer
        gl.glEnable(gl.GL_LINE_SMOOTH)  # enable line antialiasing
        gl.glPolygonOffset(1, 1)  # resize line polygon

    @window.event
    def on_close():
        # when the user press `ESC` or closed the window
        # kill all other threads
        kill()
        log.info("The user closed the renderer window")

    @window.event
    def on_character(text):
        # process keyboard information
        # like changing the display style
        # or changing pause the update of Hand object
        global update_hand_obj
        'A character has been typed'
        if text == "v":
            for hand in hand_pool:
                hand.show_type += 1
                hand.show_type %= 3
        elif text == 'p':
            update_hand_obj = not update_hand_obj
        # TODO: Update keyboard mapping here for WSAD

    window.attach(console)
    if interactive:
        log.info(f"Running in interactive mode, run Python here freely")
        log.info(f"Use 'app.__backend__.windows()[0].close()' to close the window")
        log.info(f"Use Ctrl+D to quit the Python Interactive Shell")
    app.run(framerate=60, interactive=interactive)

    log.info(f"The render function returned")


def thread_check():
    """
    Check whether this thread is the main thread
    Note: we don't want the thread to be main so we return True if it's not
    Return False if the check doesn't pass

    """
    curr_id = threading.get_native_id()
    main_id = threading.main_thread().native_id
    if curr_id == main_id:
        log.error(f"This functions should only be called from another thread.")
        return False
    else:
        return True


def sample():
    if not thread_check():
        return
    """
    The sampler thread is responsible for interacting with the WebSocket interface
    Uses websockets and asyncio to simplify the communication process
    """
    async def leap_sampler():
        global stop_websocket, update_hand_obj
        uri = "ws://localhost:6437/v7.json"  # this URL should be updated along with the SDK version

        while not stop_websocket:
            async with websockets.connect(uri) as ws:  # open the websocket connection, it's pretty hard to close manually...
                await ws.send(json.dumps({"focused": True}))  # focus on the Leap Motion device
                await ws.send(json.dumps({"background": True}))  # allow background running of the application
                await ws.send(json.dumps({"optimizeHMD": False}))
                log.info(f"Focused on the leap motion controller...")

                # initialize the performance counter
                end = start = previous = time.perf_counter()

                while not stop_websocket:
                    # always waiting for messages
                    msg = await ws.recv()
                    current = time.perf_counter()
                    if current - previous < end - start:
                        # if the time used to update the current window is longer than
                        # the currently accumulated time for reading the websocket, just wait until
                        # the next websocket information and skip the frame update

                        # this is for synchronizing the rendering thread and websocket thread better
                        continue

                    msg = json.loads(msg)  # hand object information comes with JSON format
                    if "timestamp" in msg:  # used to identity regular frame from some meta info update frame
                        start = time.perf_counter()  # starting time of the frame update

                        # the index of the left and right hand
                        left = [i for i in range(len(msg["hands"])) if msg["hands"][i]["type"] == "left"]
                        right = [i for i in range(len(msg["hands"])) if msg["hands"][i]["type"] == "right"]

                        # update the hand if there's some left/right hand present in the current websocket package
                        if len(left) > 0 and update_hand_obj:
                            i = left[0]
                            hand_pool[0].store_pos(msg, i)
                        else:
                            hand_pool[0].clean()

                        if len(right) > 0 and update_hand_obj:
                            i = right[0]
                            hand_pool[1].store_pos(msg, i)
                        else:
                            # else just clean up the hand object location
                            hand_pool[1].clean()

                        end = time.perf_counter()  # end time of the frame update
                    else:
                        log.info(f"Getting message: {msg}")  # log the meta message for the user

                    previous = time.perf_counter()  # only update the previous time log if the full loop is run successfully
                log.info("Reconnecting" if not stop_websocket else "Sampler terminated")

        log.info(f"Leap motion sampler is stopped")

    log.info(f"Running demo sampler from leap motion")
    loop = asyncio.new_event_loop()  # new thread has no event loop by default
    loop.run_until_complete(leap_sampler())  # run the Leap Motion Websocket sampler
    log.info(f"Sampler runner thread exited")


def parse():
    """
    Using global hand_pool, parse the gesture to custom package
    Then sent it through the beacon (Serial communication, bluetooth, etc)
    Parsing interval (to avoid busy waiting) is updated to match the "frame rate" of the MCU
    """
    if not thread_check():
        return

    def parse_and_send():
        # print("AAA")
        # log.info(f"Parsing position data...")
        signal0 = parser[0].parse()
        signal1 = parser[1].parse()

        log.info(f"Getting parser result: {signal0}")
        log.info(f"Getting parser result: {signal1}")

        # signal = {**signal0, **signal1}

        # signal = json.dumps(signal) + "\n"

        # signal = "".join([ f"{v:03.0f}" for v in signal1["voltage"]])

        signal = signal1 + signal0

        log.info(f"[Beacon] Send: {signal}")

        decoded = np.frombuffer(signal, dtype="uint8")
        decoded = "".join([f"{v:03.0f}" for v in decoded])
        print(decoded, file=log_file)

        beacon.send_raw(signal)

    log.info(f"Parser thread opened")
    start = time.perf_counter()
    global device_ready
    while not stop_parser:
        end = time.perf_counter()
        time.sleep(max(0, parse_interval - end + start))
        start = time.perf_counter()

        # the reader thread will update the device_ready flag
        if update_hand_obj and not stop_beacon and device_ready:
            parse_and_send()
            device_ready = False

    log.info(f"Parser thread exited")


def read():
    """
    Read messages sent by the MCU from the Serial beacon
    Update arduino_fps, parse_interval and device_ready flag if needed
    """
    if not thread_check():
        return

    # log.warning(f"Setting read timeout to None (indefinitely) and looping...")
    start = time.perf_counter()
    while not stop_beacon:
        end = time.perf_counter()
        time.sleep(max(0, READ_INTERVAL - end + start))
        start = time.perf_counter()
        global device_ready
        try: # sometimes the beacon send corrupted data, filter it by a try except block
            msg = beacon.readline()
            if ENABLE_BEACON:
                log.info(f"[Beacon] Echo: {msg}")
            if msg.strip() == "OK":
                device_ready = True

            elif msg.startswith("FPS:"):
                global arduino_fps, parse_interval
                arduino_fps = float(msg[len("FPS:"):])
                parse_interval = 1 / arduino_fps

        except Exception as e:
            log.error(e)


def main():

    # spawn websocket communication thread
    sampler_thread = Thread(target=sample)
    sampler_thread.start()

    # spawn hand gesture parser thread
    parser_thread = Thread(target=parse)
    parser_thread.start()

    # spawn the incoming message processor thread
    beacon_thread = Thread(target=read)
    beacon_thread.start()

    # run the renderer thread
    render(interactive=True)
    # this will open an interactive python interpreter after the window is successfully loaded
    # Note that you'll need to close the window before closing the interactive shell
    # use Ctrl + D to close the shell after the window is dealt with


def kill():
    # kill other threads
    global stop_websocket, stop_parser, stop_beacon
    stop_websocket = stop_parser = stop_beacon = True
    beacon.close()
    # sampler.create_task(websocket.close())


if __name__ == "__main__":
    main()
