import json
import websockets
import asyncio
import numpy as np
from glumpy import app, gl, glm, gloo, __version__
import concurrent.futures
from glumpy.geometry import colorcube
import time


class HollowCube:
    def __init__(self, u_view, transform):
        vertex = """
uniform mat4   u_model;         // Model matrix
uniform mat4   u_transform;     // Transform matrix
uniform mat4   u_view;          // View matrix
uniform mat4   u_projection;    // Projection matrix
uniform vec4   u_color;         // Global color
attribute vec4 a_color;         // Vertex color
attribute vec3 a_position;      // Vertex position
varying vec3   v_position;      // Interpolated vertex position (out)
varying vec4   v_color;         // Interpolated fragment color (out)

void main()
{
    v_color = u_color * a_color;
    v_position = a_position;
    gl_Position = u_projection * u_view * u_transform * u_model * vec4(a_position,1.0);
}
"""

        fragment = """
varying vec4 v_color;    // Interpolated fragment color (in)
varying vec3 v_position; // Interpolated vertex position (in)
void main()
{
    float xy = min( abs(v_position.x), abs(v_position.y));
    float xz = min( abs(v_position.x), abs(v_position.z));
    float yz = min( abs(v_position.y), abs(v_position.z));
    float b1 = 0.74;
    float b2 = 0.76;
    float b3 = 0.98;

    if ((xy < b1) && (xz < b1) && (yz < b1))
        discard;
    else if ((xy < b2) && (xz < b2) && (yz < b2))
        gl_FragColor = vec4(0,0,0,1);
    else if ((xy > b3) || (xz > b3) || (yz > b3))
        gl_FragColor = vec4(0,0,0,1);
    else
        gl_FragColor = v_color;
}
"""
        # structured data type
        V = np.zeros(8, [("a_position", np.float32, 3),
                         ("a_color",    np.float32, 4)])

        V["a_position"] = [[1, 1, 1], [-1, 1, 1], [-1, -1, 1], [1, -1, 1],
                           [1, -1, -1], [1, 1, -1], [-1, 1, -1], [-1, -1, -1]]
        V["a_color"] = [[0, 1, 1, 1], [0, 0, 1, 1], [0, 0, 0, 1], [0, 1, 0, 1],
                        [1, 1, 0, 1], [1, 1, 1, 1], [1, 0, 1, 1], [1, 0, 0, 1]]
        V = V.view(gloo.VertexBuffer)

        I = np.array([0, 1, 2, 0, 2, 3,  0, 3, 4, 0, 4, 5,  0, 5, 6, 0, 6, 1,
                      1, 6, 7, 1, 7, 2,  7, 4, 3, 7, 3, 2,  4, 7, 6, 4, 6, 5], dtype=np.uint32)
        self.I = I.view(gloo.IndexBuffer)

        O = np.array([0, 1, 1, 2, 2, 3, 3, 0, 4, 7, 7, 6,
                      6, 5, 5, 4, 0, 5, 1, 6, 2, 7, 3, 4], dtype=np.uint32)
        self.O = O.view(gloo.IndexBuffer)

        # Note that we do not specify the count argument because we'll bind explicitely our own vertex buffer.
        cube = gloo.Program(vertex, fragment)
        cube.bind(V)

        # starting position
        model = glm.rotate(np.eye(4, dtype=np.float32), 40, 0, 0, 1)
        model = glm.rotate(model, 30, 1, 0, 0)
        model = glm.scale(model, 0.1, 0.1, 0.1)
        cube['u_model'] = model
        cube['u_transform'] = transform
        cube['u_view'] = u_view

        self.program = cube
        self.transform = transform

    def draw(self):
        # print(f"Redrawing...")

        self.program['u_transform'] = self.transform

        # Filled cube
        self.program['u_color'] = 1, 1, 1, 1
        self.program.draw(gl.GL_TRIANGLES, self.I)

    def resize(self, width, height):
        self.program['u_projection'] = glm.perspective(45.0, width / float(height), 2.0, 200.0)


class Hand:
    def __init__(self):
        # the names of the fingers, with order
        self.finger_names = ["thumb", "index", "middle", "ring", "pinky"]
        # all components of a hand, including arm, fingers
        self.component_names = ["arm"] + self.finger_names
        # Leap Motion subscription of arm keypoints
        self.arm_pos_names = ["elbow", "wrist", "palmPosition"]
        # Leap Motion subscription of finger keypoints
        self.finger_pos_names = ["btipPosition", "carpPosition", "dipPosition", "mcpPosition", "pipPosition", "tipPosition"]
        # number of key points of the fingers
        self.finger_key_pt_count = len(self.finger_pos_names) * len(self.finger_names)
        # number of key points of the arm
        self.arm_key_pt_count = len(self.arm_pos_names)
        # global view transformation
        self.u_view = glm.translation(0, -2, -10)
        # finger key point scale relative to arm
        self.finger_scale = 0.5

        # actual OpenGL object wrapper of all key points, reused
        self.key_point = HollowCube(self.u_view, np.eye(4, dtype=np.float32))

        # mapper from all finger names and "arm" to their index in the position list
        self.name_to_index = {}
        arm_name_count = len(self.arm_pos_names)
        finger_name_count = len(self.finger_pos_names)
        index = 0
        self.name_to_index["arm"] = [index, index+arm_name_count]
        index += arm_name_count
        for name in self.finger_names:
            self.name_to_index[name] = [index, index+finger_name_count]
            index += finger_name_count

        # keypoint position list, queried every frame update for new keypoint position
        # websockt process should update this list instead of the raw OpenGL obj
        self.pos = [np.zeros(3, np.float32) for _ in range(self.finger_key_pt_count+self.arm_key_pt_count)]

    # TODO: find a way to optimize this implementation
    # getter and setter logic already extracted
    # tried to use "inspect" package, too slow
    @property
    def arm(self):
        return self.getter("arm")

    @arm.setter
    def arm(self, value):
        self.setter(value, "arm")

    @property
    def thumb(self):
        return self.getter("thumb")

    @thumb.setter
    def thumb(self, value):
        self.setter(value, "thumb")

    @property
    def index(self):
        return self.getter("index")

    @index.setter
    def index(self, value):
        self.setter(value, "index")

    @property
    def middle(self):
        return self.getter("middle")

    @middle.setter
    def middle(self, value):
        self.setter(value, "middle")

    @property
    def ring(self):
        return self.getter("ring")

    @ring.setter
    def ring(self, value):
        self.setter(value, "ring")

    @property
    def pinky(self):
        return self.getter("pinky")

    @pinky.setter
    def pinky(self, value):
        self.setter(value, "pinky")

    def position(self, start=0, end=None):
        """
        Evaluate start and end to Python list slice

        :param start: starting position
        :param end: ending position
        :return: correpsonding pos in the position list
        """
        return self.pos[start:end]

    def getter(self, caller):
        """
        Get the position of the corresponding component
        This should be called by the above @property stuff

        :param caller: caller name, defined in self.component_names
        :return: np.array of positions, with order
        """
        return self.position(*self.name_to_index[caller])

    def setter(self, value, caller):
        """
        Set the position of the corresponding component
        This should be called by the above @property stuff

        :param value: np.array of the new positions to be updated, with order
        :param caller: caller name, defined in self.component_names
        """
        for p, i in enumerate(range(*self.name_to_index[caller])):
            self.pos[i] = value[p]

    def get_transform(self, value, caller):
        """
        From position to transformation matrix
        Apply corresponding scale first

        :param value: len 3 np.array of the new positions to be updated
        :param caller: caller name, defined in self.component_names
        """
        if caller == "arm":
            return glm.translation(*value)
        else:
            return glm.translate(glm.scale(np.eye(4, dtype=np.float32), *[self.finger_scale for _ in range(3)]), *value)

    def draw(self):
        """
        Draw the hand in app event loop
        """
        c = self.key_point
        for i, name in enumerate(self.component_names):
            for v in getattr(self, name):
                c.transform = self.get_transform(v, name)
                c.draw()

    def resize(self, width, height):
        """
        Resize according to window size
        """
        self.key_point.resize(width, height)

    def store_pos(self, leap_json, index):
        """
        Update pos list by Leap Motion Websocket json object
        Extract hand #index in the json obj and their corresponding pointables

        :param leap_json: raw json from Leap Motion Websocket
        "param index": hand #index in the json obj
        """

        # print(f"Extracting hand info at index: {index}")
        hand_json = leap_json["hands"][index]
        hand_id = hand_json["id"]
        pointables = [p for p in leap_json["pointables"] if p["handId"] == hand_id]
        pointables = sorted(pointables, key=lambda x: x["type"])  # from thumb to pinky
        assert len(pointables) == len(self.finger_names)

        # print(f"Getting hand_json: {hand_json}")
        # print(f"Getting sorted pointables: {pointables}")

        arm = np.array([hand_json[name] for name in self.arm_pos_names]) / 100
        self.arm = arm
        for i, name in enumerate(self.finger_names):

            time.sleep(0)
            finger_json = pointables[i]
            finger = np.array([finger_json[name] for name in self.finger_pos_names]) / 100

            setattr(self, name, finger)


def render(interactive=False):
    print(f"Runnning glfw renderer")

    app.use("glfw")
    config = app.configuration.Configuration()
    config.samples = 16
    console = app.Console(rows=32, cols=80, scale=3, color=(1, 1, 1, 1))
    window = app.Window(width=console.cols*console.cwidth*console.scale, height=console.rows*console.cheight*console.scale, color=(0.3, 0.3, 0.3, 1), config=config)

    @window.timer(1/60.0)
    def timer(fps):
        console.clear()
        console.write("-------------------------------------------------------")
        console.write(" Glumpy version %s" % (__version__))
        console.write(" Window size: %dx%d" % (window.width, window.height))
        console.write(" Console size: %dx%d" % (console._rows, console._cols))
        console.write(" Backend: %s (%s)" % (window._backend.__name__,
                                             window._backend.__version__))
        console.write(" Actual FPS: %.2f frames/second" % (window.fps))
        console.write("-------------------------------------------------------")
        for line in repr(window.config).split("\n"):
            console.write(" "+line)
        console.write("-------------------------------------------------------")

        # Rotate cube
        for hand in hand_pool:
            model = hand.key_point.program["u_model"].reshape(4, 4)
            glm.rotate(model, 1, 0, 0, 1)
            glm.rotate(model, 1, 0, 1, 0)
            hand.key_point.program['u_model'] = model

    @window.event
    def on_draw(dt):
        window.clear()

        console.draw()

        for hand in hand_pool:
            hand.draw()

    @window.event
    def on_resize(width, height):
        for hand in hand_pool:
            hand.resize(width, height)

    @window.event
    def on_init():
        gl.glEnable(gl.GL_DEPTH_TEST)
        gl.glEnable(gl.GL_LINE_SMOOTH)
        gl.glPolygonOffset(1, 1)

    @window.event
    def on_close():
        global stop_websocket
        stop_websocket = True
        print("The user closed the renderer window")

    window.attach(console)
    app.run(framerate=60, interactive=interactive)

    print(f"The renderer app has exited")


def sample(interactive=False):
    global stop_websocket

    async def leap_sampler():
        uri = "ws://localhost:6437/v7.json"
        async with websockets.connect(uri) as ws:
            await ws.send(json.dumps({"focused": True}))
            await ws.send(json.dumps({"background": True}))
            await ws.send(json.dumps({"optimizeHMD": False}))
            print(f"Focused on the leap motion controller...")
            end = start = previous = time.perf_counter()

            while not stop_websocket:
                # always waiting for messages
                # await asyncio.sleep(1/60)
                msg = await ws.recv()
                current = time.perf_counter()
                if current - previous < end - start:
                    # print(f"Skipped...")
                    continue

                msg = json.loads(msg)
                if "timestamp" in msg:
                    if len(msg["hands"]) > 0:
                        # print(f"Getting {len(msg['hands'])} hands")
                        # ! transforming millimeters to meters
                        start = time.perf_counter()
                        for i in range(min(len(msg["hands"]), len(hand_pool))):
                            hand_pool[i].store_pos(msg, i)
                        end = time.perf_counter()
                        # print(f"Takes {end-start} to complete the extraction task")
                    # else:
                        # print(f"No hands hans been found")
                else:
                    print(f"Getting message: {msg}")

                previous = time.perf_counter()

        print(f"Leap motion sampler is stopped")

    print(f"Running demo sampler from leap motion")
    if interactive:
        loop = asyncio.get_event_loop()
    else:
        loop = asyncio.new_event_loop()
    loop.run_until_complete(leap_sampler())
    print(f"Sampler runner thread exited")


def main():

    pool = concurrent.futures.ThreadPoolExecutor(max_workers=2)
    loop = asyncio.get_event_loop()
    tasks = asyncio.gather(loop.run_in_executor(pool, sample), loop.run_in_executor(pool, render))
    loop.run_until_complete(tasks)
    # render(interactive=True)
    # run_demo(interactive=True)

# ! the signaler of the two threads, updated by renderer, used by sampler
stop_websocket = False
# * the actual hand pool, stores global hand object, updated by sampler, used by renderer
hand_pool = [Hand() for i in range(2)]

main()
