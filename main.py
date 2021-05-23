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

    log.info(f"Runnning glfw renderer")

    app.use("glfw")
    config = app.configuration.Configuration()
    config.samples = 16
    console = app.Console(rows=32, cols=80, scale=3, color=(0.1, 0.1, 0.1, 1))
    global window  # to be used to close the window
    window = app.Window(width=console.cols*console.cwidth*console.scale, height=console.rows*console.cheight*console.scale, color=(1, 1, 1, 1), config=config)

    @window.timer(1/30.0)
    def timer(dt):
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
        window.clear()
        console.draw()
        parser[1].debug_cube.draw()

        for hand in hand_pool:
            hand.draw()

    @window.event
    def on_resize(width, height):
        parser[1].debug_cube.resize(width, height)
        for hand in hand_pool:
            hand.resize(width, height)

    @window.event
    def on_init():
        gl.glEnable(gl.GL_DEPTH_TEST)
        gl.glEnable(gl.GL_LINE_SMOOTH)
        gl.glPolygonOffset(1, 1)

    @window.event
    def on_close():
        kill()
        log.info("The user closed the renderer window")

    @window.event
    def on_character(text):
        global update_hand_obj
        'A character has been typed'
        if text == "v":
            for hand in hand_pool:
                hand.show_type += 1
                hand.show_type %= 3
        elif text == 'p':
            update_hand_obj = not update_hand_obj
        # TODO: Update keyboard mapping here for testing
        # elif text == "w":
        #     beacon.send("F")
        # elif text == "s":
        #     beacon.send("B")
        # elif text == "a":
        #     beacon.send("L")
        # elif text == "d":
        #     beacon.send("R")
        # elif text == " ":
        #     beacon.send("S")
        # else:
        #     beacon.send(text)
        # log.info(f"Key: {text}")

    window.attach(console)
    if interactive:
        log.info(f"Running in interactive mode, run Python here freely")
        log.info(f"Use 'app.__backend__.windows()[0].close()' to close the window")
        log.info(f"Use Ctrl+D to quit the Python Interactive Shell")
    app.run(framerate=60, interactive=interactive)

    log.info(f"The render function returned")


def sample():

    async def leap_sampler():
        global stop_websocket, update_hand_obj
        uri = "ws://localhost:6437/v7.json"

        while not stop_websocket:
            async with websockets.connect(uri) as ws:
                await ws.send(json.dumps({"focused": True}))
                await ws.send(json.dumps({"background": True}))
                await ws.send(json.dumps({"optimizeHMD": False}))
                log.info(f"Focused on the leap motion controller...")
                end = start = previous = time.perf_counter()

                while not stop_websocket:
                    # always waiting for messages
                    # await asyncio.sleep(1/60)
                    msg = await ws.recv()
                    current = time.perf_counter()
                    if current - previous < end - start:
                        # log.info(f"Skipped...")
                        continue

                    msg = json.loads(msg)
                    if "timestamp" in msg:
                        start = time.perf_counter()
                        left = [i for i in range(len(msg["hands"])) if msg["hands"][i]["type"] == "left"]
                        right = [i for i in range(len(msg["hands"])) if msg["hands"][i]["type"] == "right"]

                        # ! transforming millimeters to meters
                        # ! only updating the first hands
                        if len(left) > 0 and update_hand_obj:
                            i = left[0]
                            hand_pool[0].store_pos(msg, i)
                        else:
                            hand_pool[0].clean()

                        if len(right) > 0 and update_hand_obj:
                            i = right[0]
                            hand_pool[1].store_pos(msg, i)
                        else:
                            hand_pool[1].clean()

                        end = time.perf_counter()
                        # log.info(f"Getting {len(msg['hands'])} hands")

                        # log.info(f"Takes {end-start} to complete the extraction task")

                        # else:

                        # log.info(f"No hands hans been found")
                    else:
                        log.info(f"Getting message: {msg}")

                    previous = time.perf_counter()
                log.info("Reconnecting" if not stop_websocket else "Sampler terminated")

        log.info(f"Leap motion sampler is stopped")

    log.info(f"Running demo sampler from leap motion")
    loop = asyncio.new_event_loop()
    loop.run_until_complete(leap_sampler())
    log.info(f"Sampler runner thread exited")


def parse():
    curr_id = threading.get_native_id()
    main_id = threading.main_thread().native_id
    if curr_id == main_id:
        log.error(f"This functions should only be called from another thread.")
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
        if update_hand_obj and not stop_beacon and device_ready:
            parse_and_send()
            device_ready = False

    log.info(f"Parser thread exited")


def read():
    curr_id = threading.get_native_id()
    main_id = threading.main_thread().native_id
    if curr_id == main_id:
        log.error(f"This functions should only be called from another thread.")
        return

    # log.warning(f"Setting read timeout to None (indefinitely) and looping...")
    start = time.perf_counter()
    while not stop_beacon:
        end = time.perf_counter()
        time.sleep(max(0, READ_INTERVAL - end + start))
        start = time.perf_counter()
        global device_ready
        try:
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

    sampler_thread = Thread(target=sample)
    sampler_thread.start()

    parser_thread = Thread(target=parse)
    parser_thread.start()

    beacon_thread = Thread(target=read)
    beacon_thread.start()

    render(interactive=True)


def kill():
    global stop_websocket, stop_parser, stop_beacon
    stop_websocket = stop_parser = stop_beacon = True
    beacon.close()
    # sampler.create_task(websocket.close())


if __name__ == "__main__":
    main()
