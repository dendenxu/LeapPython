import numpy as np
from log import log
from hand import Hand
from cube import HollowCube
from glumpy import app, gl, glm, gloo, __version__
from helper import rotate_to_direction, rotate_to_2directions, normal
import json


class GestureParser:
    def __init__(self, hand: Hand):
        self.should_apply_force = False
        self.fist_threshold = 1

        self.palm_open_count_max = 1
        self.palm_open_count = 0
        self.hand = hand  # store a reference to the hand
        self.base = np.array([0, 0, 0])  # palm position
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

        apply_force = self.palm_open_count > 0

        force = np.zeros(2, dtype=np.float32)
        cube_scale = self.cube_scale

        if apply_force:
            force = (palm - self.base)[[0, 2]]
            cube_scale *= 1.5
            # log.info(f"Adding force: {force}")
        # else:
        #     self.base = palm

        m = rotate_to_2directions(np.eye(4, dtype=np.float32), palm_normal, palm-wrist)
        m = glm.scale(m, cube_scale, cube_scale, cube_scale)
        m = glm.translate(m, *fist)
        # log.info(f"New transformation:\n{m}")
        self.debug_cube.transform = m

        # remapping of force to wheel voltage
        # ! Assuming Arduino.h: LOW 0x0, HIGH 0x1
        LOW = 0x0
        HIGH = 0x1

        # M = np.array([
        #     [-np.sqrt(3)/2, -np.sqrt(3)/2],
        #     [-1/2, 1/2]
        # ]) # Transform from Arduino space to Our space

        # M = np.linalg.inv(M) # Transfrom from Out space to Arduino space

        M = np.array([
            [-0.57735027, -1.],
            [-0.57735027,  1.]
        ])

        coords = M.dot(force)  # transformed into voltage space

        # log.info(f"Transformed force in arduino space: {coords}")

        msg = {
            "voltages": np.array([[c > 0, np.abs(c)] for c in coords]).ravel().tolist()
        }

        return json.dumps(msg)+"\n"
