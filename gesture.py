import numpy as np
from log import log
from hand import Hand
from cube import HollowCube
from glumpy import app, gl, glm, gloo, __version__
from helper import rotate_to_direction, rotate_to_2directions, normal


class GestureParser:
    def __init__(self, hand: Hand):
        self.should_apply_force = False
        self.fist_threshold = 1

        self.palm_open_count_max = 1
        self.palm_open_count = 0
        self.hand = hand  # store a reference to the hand
        self.base = np.array([0,0,0])  # palm position
        self.debug_cube = HollowCube(glm.translation(0, -2, -10), np.eye(4, dtype=np.float32))
        self.cube_scale = 2

    def parse(self):

        palm = self.hand.palm.copy()
        wrist = self.hand.wrist.copy()
        palm_normal = self.hand.palm_normal.copy()

        fist = palm + 0.05 * normal(palm-wrist) + 0.35 * palm_normal
        dist = 0
        for finger in self.hand.finger_names:
            tip = getattr(self.hand, finger)[-1]
            vec = tip - fist
            dist += np.dot(vec, vec)

        dist = np.sqrt(dist)
        # log.info(f"L2 Distance: {dist}")
        holding = dist < self.fist_threshold

        if holding:
            self.palm_open_count = self.palm_open_count_max
        else:
            self.palm_open_count -= 1

        force = self.palm_open_count > 0

        acc = np.zeros(2, dtype=np.float32)
        cube_scale = self.cube_scale

        if force:
            acc = (palm - self.base)[[0, 2]]
            cube_scale *= 1.5
            # log.info(f"Adding force: {acc}")
        #else:
            #self.base = palm

        m = rotate_to_2directions(np.eye(4, dtype=np.float32), palm_normal, palm-wrist)
        m = glm.scale(m, cube_scale, cube_scale, cube_scale)
        m = glm.translate(m, *fist)
        # log.info(f"New transformation:\n{m}")
        self.debug_cube.transform = m

        result = ""
        Z_thresh = 0.5
        X_thresh = 0.5
        stopx = False
        stopz = False
        if acc[1] < -Z_thresh:
            result += "F"
        elif acc[1] > Z_thresh:
            result += "B"
        else:
            stopz = True

        if acc[0] < -X_thresh:
            result += "L"
        elif acc[0] > X_thresh:
            result += "R"
        else:
            stopx = True

        if stopx and stopz:
            result = "S"

        return result
