import numpy as np


def normal(x):
    return x / np.linalg.norm(x)


def rotate_to_direction(m, direction):
    r = np.eye(4, dtype=np.float32)
    if direction[0] == 0 and direction[2] == 0:
        if direction[1] < 0:  # rotate 180 degrees
            r[0, 0] = -1
            r[1, 1] = -1

        # else if direction.y >= 0, leave transform as the identity matrix.
    else:

        new_y = normal(direction)
        new_z = normal(np.cross(new_y, np.array([0, 1, 0])))
        new_x = normal(np.cross(new_y, new_z))

        r[:3, 0] = new_x
        r[:3, 1] = new_y
        r[:3, 2] = new_z
    m = np.dot(m, r.T)  # translated
    return m


def rotate_to_2directions(m, d1, d2):
    r = np.eye(4, dtype=np.float32)

    def normal(x):
        n = np.linalg.norm(x)
        return x/n
    new_y = normal(d1)
    new_z = normal(d2)
    new_x = normal(np.cross(d1, d2))

    r[:3, 0] = new_x
    r[:3, 1] = new_y
    r[:3, 2] = new_z
    m = np.dot(m, r.T)  # translated
    return m
