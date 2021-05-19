import math
import numpy as np
from log import log
from hand import Hand
from cube import HollowCube
from glumpy import app, gl, glm, gloo, __version__
from helper import rotate_to_direction, rotate_to_2directions, normal
import json


class GestureParser:
    def __init__(self, hand: Hand, direction):
        self.should_apply_force = False
        self.fist_threshold = 1

        self.palm_open_count_max = 1
        self.palm_open_count = 0
        self.hand = hand  # store a reference to the hand
        self.base_left = np.array([-0.6, 0, 0])  # left palm base position
        self.base_right = np.array([0.6, 0, 0])  # rhgt palm base position
        self.debug_cube = HollowCube(glm.translation(0, -2, -10), np.eye(4, dtype=np.float32))
        self.cube_scale = 2
        self.direction = direction
    
    def is_wrap(self, fist, finger):
        tip = getattr(self.hand, finger)[-1]
        vec = tip - fist
        dist = np.sqrt(np.dot(vec, vec))
        return dist < self.fist_threshold / 2
    
    def is_hold(self):
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
        return dist < self.fist_threshold

    # def get_angle(self, vector):                
    #     # [x right, y up, z in]
    #     angle_hor = round(math.atan(1.0*vector[2]/vector[0])*180/math.pi)
    #     angle_ver = round(math.atan(1.0*vector[2]/math.sqrt(vector[0]**2 + vector[2]**2))*180/math.pi)
    #     return [angle_hor, angle_ver]

    def parse(self):
        palm = self.hand.palm.copy()
        wrist = self.hand.wrist.copy()
        # elbow = self.hand.elbow.copy()
        palm_normal = self.hand.palm_normal.copy()
        fist = palm + 0.05 * normal(palm-wrist) + 0.35 * palm_normal

        # arm_direction = wrist - elbow 
        #[angle_hor, angle_ver] = self.get_angle(arm_direction)
        palm_normal = self.hand.palm_normal.copy()
        
        holding = self.is_hold()
        is_wrap = []
        for finger in self.hand.finger_names:
            is_wrap.append(self.is_wrap(fist, finger))

        msg = {}
        if self.direction == 1 :
            if holding:
                self.palm_open_count = self.palm_open_count_max
            else:
                self.palm_open_count -= 1

            apply_force = self.palm_open_count > 0

            force = np.zeros(2, dtype=np.float32)
            cube_scale = self.cube_scale

            if apply_force:
                force = (palm - self.base_right)[[0, 2]]
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

            voltage = np.array([[c > 0, np.abs(c)] for c in coords]).ravel().tolist()
            multiplier = np.array([255, 512, 255, 512])

            values = voltage * multiplier
            values = np.clip(values, 0, 255)
            msg["voltage"] = values.tolist()

        else:
            if is_wrap[1] and is_wrap[2] and is_wrap[3]:                    
                msg["angle0"] = "10"
                # 爪子闭合
            elif (not is_wrap[1]) and (not is_wrap[2]) and (not is_wrap[3]):
                msg["angle0"] = "50"
                # 爪子打开
            
            if is_wrap[0] and not is_wrap[4]:
                msg["angle3"] = "r"
                # 向右转

            if is_wrap[4] and not is_wrap[0]:
                msg["angle3"] = "l"
                # 向左转
            
            # 这里是计算手腕位置与base_position的差，来控制中间两个舵机角度的代码
            
        return msg
