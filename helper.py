import numpy as np


def normalized(x):
    # return the normalized unit vector in the direction of the input vector
    return x / np.linalg.norm(x)


def rotate_to_direction(m, direction):
    # rotate a cube (transformation) to a specific direction
    # so that one face (in terms of a quad) appears in alignment with that direction
    # ! note that the input m is OpenGL matrix, in transposed style
    # check out the package `glm` from glumpy for more info
    r = np.eye(4, dtype=np.float32)
    if direction[0] == 0 and direction[2] == 0:
        if direction[1] < 0:  # rotate 180 degrees
            r[0, 0] = -1
            r[1, 1] = -1

        # else if direction.y >= 0, leave transform as the identity matrix.
    else:

        new_y = normalized(direction)
        new_z = normalized(np.cross(new_y, np.array([0, 1, 0])))
        new_x = normalized(np.cross(new_y, new_z))

        r[:3, 0] = new_x
        r[:3, 1] = new_y
        r[:3, 2] = new_z
    m = np.dot(m, r.T)  # transposed
    return m


def rotate_to_2directions(m, d1, d2):
    # rotate a cube (transformation) to two specific directions
    # so that the cube appears in alignment with some two direcitons
    # ! note that the input m is OpenGL matrix, in transposed style
    # check out the package `glm` from glumpy for more info
    r = np.eye(4, dtype=np.float32)

    new_y = normalized(d1)
    new_z = normalized(d2)
    new_x = normalized(np.cross(d1, d2))

    r[:3, 0] = new_x
    r[:3, 1] = new_y
    r[:3, 2] = new_z
    m = np.dot(m, r.T)  # transposed
    return m
