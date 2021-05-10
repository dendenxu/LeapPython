from glumpy import app, gl, glm, gloo, __version__
import numpy as np


class HollowCube:
    def __init__(self, u_view, transform: np.ndarray):
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


    if ((xy < b1) && (xz < b1) && (yz < b1)) {
            discard;
    }
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

        self.global_scale = 0.1

        # starting position
        model = glm.scale(np.eye(4, dtype=np.float32), self.global_scale, self.global_scale, self.global_scale)
        cube['u_model'] = model
        cube['u_transform'] = transform
        cube['u_view'] = u_view
        # ! IS THIS A BUG? CANNOT USE BOOL IN GLSL SHADER
        # cube['u_should_hollow'] = np.uint32(should_hollow)

        self.program = cube
        self.transform = transform

    @property
    def transform(self):
        return self.program['u_transform'].reshape(4, 4)

    @transform.setter
    def transform(self, value):
        self.program['u_transform'] = value

    @property
    def model(self):
        return self.program['u_model'].reshape(4, 4)

    @model.setter
    def model(self, value):
        self.program['u_model'] = value

    def draw(self):
        # log.info(f"Redrawing...")

        # self.program['u_transform'] = self.transform

        # Filled cube
        self.program['u_color'] = 1, 1, 1, 1
        self.program.draw(gl.GL_TRIANGLES, self.I)

    def resize(self, width, height):
        self.program['u_projection'] = glm.perspective(45.0, width / float(height), 2.0, 200.0)
