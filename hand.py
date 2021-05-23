# Actual Core of the Leap Motion Python Driver (based on WebSocket)
# It contains compact information about the hand recognized from the Leap Motion Controller
# And it also manages the "HollowCube"s to be rendered on the screen for some debugging
# Note that you can print information about a specific hand by just printing the str of it, like `str(hand)` or just print(hand)

from glumpy import app, gl, glm, gloo, __version__
from cube import HollowCube
import numpy as np
import json
import time
from helper import rotate_to_direction  # helper function to construct transformation


class Hand:
    def __init__(self):

        # ! Actual init definitions, want more bones? Add them here
        # the names of the fingers, with order
        # Note: for both fingers and arms, the joints all starts from your heart and goes to your tips, for example, with arm, the first element is the cloest to your heart, which is the elbow, then wrist, then plam
        self.finger_names = ["thumb", "index", "middle", "ring", "pinky"]
        self.arm_names = ["arm"]
        # all components of a hand, including arm, fingers
        self.component_names = self.arm_names + self.finger_names
        # Leap Motion subscription of arm keypoints
        self.arm_pos_names = ["elbow", "wrist", "palmPosition"]
        # Leap Motion subscription of finger keypoints
        # metacarpal, proximal, middle, distal
        self.finger_pos_names = ["carpPosition", "mcpPosition", "pipPosition", "dipPosition", "btipPosition"]

        # ! Derived information from the above definitions
        self.name_to_pos_names = {**{name: self.arm_pos_names for name in self.arm_names}, **{name: self.finger_pos_names for name in self.finger_names}}
        # number of key points of the fingers
        self.finger_key_pt_count = len(self.finger_pos_names) * len(self.finger_names)
        # number of key points of the arm
        self.arm_key_pt_count = len(self.arm_pos_names)
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

        # ! OpenGL controls
        # global camera view transformation
        self.u_view = glm.translation(0, -2, -10)
        # global finger key point scale relative to arm
        self.finger_scale = 0.5
        # global bones scale relative to finger
        self.finger_scale = 0.67
        # show_type: 1: only joints, 2: joints + bones, 0: bones
        self.show_type = 1

        # OpenGL objects
        # actual OpenGL object wrapper of all key points, reused
        self.key_point = HollowCube(self.u_view, np.eye(4, dtype=np.float32))
        self.bone = HollowCube(self.u_view, np.eye(4, dtype=np.float32))

        # ! Actual bare metal data
        # keypoint position list, queried every frame update for new keypoint position
        # websockt process should update this list instead of the raw OpenGL obj
        self.pos = np.array([np.zeros(3, np.float32) for _ in range(self.finger_key_pt_count+self.arm_key_pt_count)])
        # Extra information to be remembered in the history
        # The normal vector of the palm
        self.palm_normal = np.zeros(3, np.float32)
        # timestamp
        self.timestamp = 256101634501  # currently not used in parsing

        # ! History list
        # empty gesture history, updated withe new infromation from the above mentioned data
        self.history = []


    # ! Convenient properties to access the hand structure
    # TODO: find a way to optimize this implementation
    # getter and setter logic already extracted
    # Note: tried to use "inspect" package, too slow
    @property
    def palm(self):
        return self.arm[2]

    @property
    def wrist(self):
        return self.arm[1]

    @property
    def elbow(self):
        return self.arm[0]

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

    def get_key_point_transform(self, position, caller):
        """
        From position to transformation matrix
        Apply corresponding scale first

        :param position: len 3 np.array of the new positions to be updated
        :param caller: caller name, defined in self.component_names
        """
        if caller == "arm":
            return glm.translation(*position)
        else:
            return glm.translate(glm.scale(np.eye(4, dtype=np.float32), self.finger_scale, self.finger_scale, self.finger_scale), *position)

    def get_bone_transform(self, start, end, compensation_cube_scale, caller):
        """
        From two positions to transformation matrix
        Apply corresponding scale first

        :param start: len 3 np.array of the starting point
        :param end: len 3 np.array of the ending point
        :param compensation_cube_scale: the OpenGL cube scale, to compasate for transformation
        :param caller: caller name, defined in self.component_names
        """
        if caller == "arm":
            finger_scale = 1
        else:
            finger_scale = self.finger_scale
        bone_scale = self.bone_scale * finger_scale

        direction = end-start
        m = glm.scale(np.eye(4, dtype=np.float32), bone_scale, 1/compensation_cube_scale/2 * np.linalg.norm(direction), bone_scale)  # scale down a little bit
        m = rotate_to_direction(m, direction)
        m = glm.translate(m, *((start+end)/2))  # to middle point
        return m

    def draw(self):
        """
        Draw the hand in app event loop
        """
        c = self.key_point
        b = self.bone
        for i, name in enumerate(self.component_names):
            positions = getattr(self, name)
            show_bone = self.show_type == 0 or self.show_type == 2
            show_key = self.show_type == 1 or self.show_type == 2
            if show_bone:
                for i in range(len(positions)-1):
                    # iterate through all positions except last
                    start = positions[i]
                    end = positions[i+1]
                    b.transform = self.get_bone_transform(start, end, b.global_scale, name)
                    b.draw()
            if show_key:
                for v in positions:
                    c.transform = self.get_key_point_transform(v, name)
                    c.draw()

    def resize(self, width, height):
        """
        Resize according to window size
        """
        self.key_point.resize(width, height)
        self.bone.resize(width, height)

    def store_pos(self, leap_json, index):
        """
        Update pos list by Leap Motion Websocket json object
        Extract hand #index in the json obj and their corresponding pointables

        :param leap_json: raw json from Leap Motion Websocket
        "param index": hand #index in the json obj
        """

        # log.info(f"Extracting hand info at index: {index}")
        hand_json = leap_json["hands"][index]
        hand_id = hand_json["id"]
        if hand_json["confidence"] < 0.7:
            return
        pointables = [p for p in leap_json["pointables"] if p["handId"] == hand_id]
        pointables = sorted(pointables, key=lambda x: x["type"])  # from thumb to pinky
        assert len(pointables) == len(self.finger_names)

        # log.info(f"Getting hand_json: {hand_json}")
        # log.info(f"Getting sorted pointables: {pointables}")

        self.timestamp = leap_json["timestamp"]
        self.palm_normal = np.array(hand_json["palmNormal"])

        arm = np.array([hand_json[name] for name in self.arm_pos_names]) / 100
        self.arm = arm
        for i, name in enumerate(self.finger_names):

            time.sleep(0)
            finger_json = pointables[i]
            finger = np.array([finger_json[name] for name in self.finger_pos_names]) / 100

            setattr(self, name, finger)

        self.update_history()

    def clean(self):
        self.pos = np.zeros_like(self.pos)

    def update_history(self):
        self.history.append(
            {
                "pos": self.pos,
                "timestamp": self.timestamp,
                "palm_normal": self.palm_normal
            }
        )

    @property
    def formatted_data(self):
        # you can surely guess what this does from the name
        obj = {name: {n: v.tolist() for n, v in zip(self.name_to_pos_names[name], getattr(self, name))} for name in self.component_names}
        obj["timestamp"] = self.timestamp
        obj["palm_normal"] = self.palm_normal.tolist()
        return obj

    def __str__(self):
        return self.__repr__()

    def __repr__(self):
        return json.dumps(self.formatted_data)
