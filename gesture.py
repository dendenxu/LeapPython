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

import math
import numpy as np
from log import log
from hand import Hand
from cube import HollowCube
from glumpy import app, gl, glm, gloo, __version__
from helper import rotate_to_direction, rotate_to_2directions, normalized
import json


class GestureParser:
    def __init__(self, hand: Hand, direction):
        self.should_apply_force = False
        self.fist_threshold = 1

        self.palm_open_count_max = 1
        self.palm_open_count = 0
        self.hand = hand  # store a reference to the hand
        self.base_left = np.array([-0.8, 0.6, .6])  # left palm base position
        self.base_right = np.array([0.8, 0, 0])  # rhgt palm base position
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

        fist = palm + 0.05 * normalized(palm-wrist) + 0.35 * palm_normal
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
        fist = palm + 0.05 * normalized(palm-wrist) + 0.35 * palm_normal

        # arm_direction = wrist - elbow
        #[angle_hor, angle_ver] = self.get_angle(arm_direction)
        palm_normal = self.hand.palm_normal.copy()

        holding = self.is_hold()
        is_wrap = []
        for finger in self.hand.finger_names:
            is_wrap.append(self.is_wrap(fist, finger))

        msg = {}
        if self.direction == 1:
            if holding:
                self.palm_open_count = self.palm_open_count_max
            else:
                self.palm_open_count -= 1

            apply_force = self.palm_open_count > 0

            force = np.zeros(2, dtype=np.float32)
            cube_scale = self.cube_scale

            if apply_force:
                force = (palm - self.base_right)[[0, 2]]
                force[1] *= -1
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

            # M = np.array([
            #     [np.sqrt(2)/2, np.sqrt(2)/2],
            #     [-np.sqrt(2)/2,np.sqrt(2)/2]
            # ])
            M = np.array([
                [0.57735027, 1.],
                [-0.57735027,  1.]
            ])

            coords = M.dot(force)  # transformed into voltage space

            # log.info(f"Transformed force in arduino space: {coords}")

            voltage = np.array([[c < 0, np.abs(c)] for c in coords]).ravel()

            multiplier = [255, 255, 255, 255]

            values = voltage * multiplier
            values = np.clip(values, 0, 255).astype("uint8")
            # msg["voltage"] = values.tolist()

            # ! being hacky

            return values.tobytes()

        else:
            # 默认状态下 爪子稍微张开，bottom舵机发送信号为0，表示不动
            angle3 = 20
            if is_wrap[1] and is_wrap[2] and is_wrap[3]:
                angle3 = 10
                # 爪子闭合
            elif (not is_wrap[1]) and (not is_wrap[2]) and (not is_wrap[3]):
                angle3 = 70
                # 爪子打开

            # if is_wrap[0] and not is_wrap[4]:
            #     msg["angle0"] = "63"
            #     # 向右转

            # if is_wrap[4] and not is_wrap[0]:
            #     msg["angle0"] = "127"
            #     # 向左转

            # 在y上的移动大概是[1.3, 2.6]
            # 在z上的移动大概是[0, -1.5]
            #
            # 上臂舵机[10, 140], up <-> +
            # 下臂舵机[40, 170], up <-> -
            # y -> 上臂
            # z -> 下臂

            dis_pos = (palm - self.base_left)

            print(dis_pos)
            MIN_POS = [-1, 0.6, -3]
            MAX_POS = [1.5, 6.6, 0.6]
            FLAG_POS = [-1, -1, -1]

            MIN_ANG = [0, 40, 10]
            MAX_ANG = [170, 140, 130]

            angles = [
                MIN_ANG[i] + (MAX_ANG[i] - MIN_ANG[i]) * (
                    (
                        (
                            np.clip(dis_pos[i], MIN_POS[i], MAX_POS[i]) - MIN_POS[i]
                        ) / (MAX_POS[i]-MIN_POS[i]) - 0.5
                    ) * FLAG_POS[i] + 0.5
                ) for i in range(len(dis_pos))] + [angle3]
            # dis_pos[2] = max(-1.5, min(0.6, dis_pos[2]))
            # dis_pos[1] = max(0.6, min(3.3, dis_pos[1]))
            # dis_pos[0] = - max(-1, min(1, dis_pos[0]))

            # msg["angle2"] = 10 + round((130 - 10) * ((dis_pos[1]) / (3.3 - 0.6)))
            # msg["angle1"] = 40 + round((160 - 40) * ((dis_pos[2] + 1.5) / (1.5)))
            # msg["angle0"] = 0 + round((170) * ((dis_pos[0] + 1) / 2))

            # print(dis_pos)
            # print(msg["angle2"])
            # print(msg["angle1"])
            # print(msg["angle0"])

            # # msggg = [msg["angle0"], msg["angle1"], msg["angle2"], angle3]
            # # 底部舵机是否左右转
            # # 下臂舵机角度
            # # 上臂舵机角度
            # # 爪子舵机角度

            # msggg = np.array(msggg).astype("uint8")

            # return msggg.tobytes()
            print(angles)

            raw = np.array(angles).astype('uint8').tobytes()

            print(raw)

            return raw
            #
            # 映射到两个机械臂舵机上就行
            # 这里是计算手腕位置与base_position的差，来控制中间两个舵机角度的代码

        # return np.concatenate([values, msggg], 0).tobytes()
