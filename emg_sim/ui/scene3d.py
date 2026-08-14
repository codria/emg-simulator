"""3D scene: floor, base, parametric arm, reach fan, target (PyQtGraph).

The arm is drawn from the ported parametric parts (armmesh.build_parts) — one
GLMeshItem per part, re-transformed each frame by its parent joint frame. The
reach fan (a filled + outlined half-annulus over [θ_min,θ_max] between r_min and
r_max) is rebuilt every frame from cfg, so it tracks the r/θ sliders and shows
the play area; a yellow arrow marks the forward direction. The target is a green
sphere with a green reach-region ring; the arm tip is a small cyan marker.
"""

from __future__ import annotations

import numpy as np
import pyqtgraph as pg
import pyqtgraph.opengl as gl
from pyqtgraph.opengl.shaders import FragmentShader, ShaderProgram, VertexShader

from . import armmesh

# Brighter two-sided shader. Mirrors pyqtgraph's ES2-compatible 'shaded' shader
# (a_position/a_normal/a_color + u_mvp/u_normal) — required because Qt on Windows
# runs OpenGL ES via ANGLE — but with high ambient + |N·L| so no face is dark.
_BRIGHT = ShaderProgram("brightarm", [
    VertexShader("""
        uniform mat4 u_mvp;
        uniform mat3 u_normal;
        attribute vec4 a_position;
        attribute vec3 a_normal;
        attribute vec4 a_color;
        varying vec4 v_color;
        varying vec3 v_normal;
        void main() {
            v_normal = normalize(u_normal * a_normal);
            v_color = a_color;
            gl_Position = u_mvp * a_position;
        }
    """),
    FragmentShader("""
        #ifdef GL_ES
        precision mediump float;
        #endif
        varying vec4 v_color;
        varying vec3 v_normal;
        void main() {
            vec3 n = normalize(v_normal);
            float d = abs(dot(n, normalize(vec3(0.4, -0.5, 1.0))));
            float p = 0.55 + 0.6 * d;
            vec3 rgb = min(v_color.rgb * p, vec3(1.0));
            gl_FragColor = vec4(rgb, v_color.a);
        }
    """),
])

_C_TARGET = (0.30, 0.90, 0.42, 0.9)
_C_REGION = (0.4, 1.0, 0.5, 1.0)
_C_TIP = (0.55, 0.85, 1.0, 1.0)
_C_FAN = (90 / 255, 160 / 255, 220 / 255, 1.0)
_C_FAN_FILL = (0.30, 0.55, 0.9, 0.16)
_C_FRONT = (1.0, 0.82, 0.30, 1.0)


class Scene3D(gl.GLViewWidget):
    def __init__(self, cfg):
        super().__init__()
        self.cfg = cfg
        # view from the right-rear, looking down (front = +Y)
        self.setCameraPosition(distance=1.75, elevation=30, azimuth=-55)
        self.opts["center"] = pg.Vector(0.0, 0.05, 0.12)
        self.setBackgroundColor(pg.mkColor(20, 20, 28))

        # Floor + pedestal are anchored to the ARM BASE (J1 at z=0), NOT to the
        # operation plane — otherwise raising z_plane buries the arm in the pedestal.
        z_floor = -0.05

        floor = gl.GLGridItem()
        floor.setSize(1.8, 1.8)
        floor.setSpacing(0.1, 0.1)
        floor.translate(0, 0, z_floor)
        floor.setColor((120, 120, 140, 110))
        self.addItem(floor)

        # pedestal: floor up to the arm base (top face at z=0)
        ped_v = armmesh.cylinder_tris(0.09, 0.05, 48)
        ped = gl.GLMeshItem(
            meshdata=gl.MeshData(vertexes=ped_v, faces=np.arange(len(ped_v)).reshape(-1, 3)),
            smooth=False, color=(0.34, 0.36, 0.42, 1.0), shader=_BRIGHT, glOptions="opaque")
        ped.translate(0, 0, z_floor + 0.025)  # spans -0.05..0.0
        self.addItem(ped)

        # reach fan: translucent fill + outline + front arrow (all live)
        self._fan_fill = gl.GLMeshItem(smooth=False, color=_C_FAN_FILL,
                                       glOptions="translucent", drawEdges=False)
        self.addItem(self._fan_fill)
        self._arc_in = gl.GLLinePlotItem(width=2.0, antialias=True, color=_C_FAN)
        self._arc_out = gl.GLLinePlotItem(width=2.0, antialias=True, color=_C_FAN)
        self._edge_lo = gl.GLLinePlotItem(width=2.0, antialias=True, color=_C_FAN)
        self._edge_hi = gl.GLLinePlotItem(width=2.0, antialias=True, color=_C_FAN)
        self._front = gl.GLLinePlotItem(width=3.5, antialias=True, color=_C_FRONT, mode="lines")
        for it in (self._arc_in, self._arc_out, self._edge_lo, self._edge_hi, self._front):
            self.addItem(it)
        try:
            self._front_label = gl.GLTextItem(text="FRONT", color=(255, 210, 80, 255))
            self.addItem(self._front_label)
        except Exception:
            self._front_label = None
        self._update_fan()

        # parametric arm parts
        self.parts = []
        for part in armmesh.build_parts():
            v = part["verts"]
            md = gl.MeshData(vertexes=v, faces=np.arange(len(v)).reshape(-1, 3))
            item = gl.GLMeshItem(meshdata=md, smooth=False, color=(*part["color"], 1.0),
                                 shader=_BRIGHT, glOptions="opaque")
            self.addItem(item)
            self.parts.append((item, part["parent"], part["xform"]))

        tmd = gl.MeshData.sphere(rows=14, cols=14, radius=cfg.game.reach_dist)
        self.target = gl.GLMeshItem(meshdata=tmd, smooth=True, color=_C_TARGET,
                                    shader=_BRIGHT, glOptions="translucent")
        self.addItem(self.target)
        self._region = gl.GLLinePlotItem(width=2.0, antialias=True, color=_C_REGION)
        self.addItem(self._region)

        pmd = gl.MeshData.sphere(rows=8, cols=8, radius=0.018)
        self.tipmark = gl.GLMeshItem(meshdata=pmd, smooth=True, color=_C_TIP, shader=_BRIGHT)
        self.addItem(self.tipmark)

    # -- reach fan ---------------------------------------------------------
    def _arc(self, radius: float, th0: float, th1: float, n: int = 72) -> np.ndarray:
        th = np.linspace(th0, th1, n)
        z = self.cfg.control.z_plane
        return np.column_stack([radius * np.cos(th), radius * np.sin(th), np.full(n, z)])

    def _update_fan(self) -> None:
        c = self.cfg.control
        z = c.z_plane
        self._arc_in.setData(pos=self._arc(c.r_min, c.theta_min, c.theta_max))
        self._arc_out.setData(pos=self._arc(c.r_max, c.theta_min, c.theta_max))
        for edge, th in ((self._edge_lo, c.theta_min), (self._edge_hi, c.theta_max)):
            edge.setData(pos=np.array([[c.r_min * np.cos(th), c.r_min * np.sin(th), z],
                                       [c.r_max * np.cos(th), c.r_max * np.sin(th), z]]))
        # translucent fill
        n = 48
        th = np.linspace(c.theta_min, c.theta_max, n)
        inner = np.column_stack([c.r_min * np.cos(th), c.r_min * np.sin(th), np.full(n, z)])
        outer = np.column_stack([c.r_max * np.cos(th), c.r_max * np.sin(th), np.full(n, z)])
        verts = np.vstack([inner, outer])
        faces = []
        for i in range(n - 1):
            a, b, cc, d = i, i + 1, n + i, n + i + 1
            faces += [[a, cc, d], [a, d, b]]
        self._fan_fill.setMeshData(vertexes=verts, faces=np.array(faces))
        # front arrow (with arrowhead)
        thm = 0.5 * (c.theta_min + c.theta_max)
        dvec = np.array([np.cos(thm), np.sin(thm), 0.0])
        perp = np.array([-np.sin(thm), np.cos(thm), 0.0])
        base = np.array([0.0, 0.0, z]) + c.r_min * 0.35 * dvec
        tip = np.array([0.0, 0.0, z]) + c.r_max * 1.12 * dvec
        hl = tip - 0.07 * dvec + 0.045 * perp
        hr = tip - 0.07 * dvec - 0.045 * perp
        self._front.setData(pos=np.array([base, tip, tip, hl, tip, hr]))
        if self._front_label is not None:
            self._front_label.setData(pos=tip + 0.04 * dvec + np.array([0, 0, 0.02]))

    # -- per-frame ---------------------------------------------------------
    def update_state(self, arm, target_xyz, tip) -> None:
        self._update_fan()
        Ts = arm.forward_kinematics()
        for item, parent, xform in self.parts:
            m = Ts[parent + 1] @ xform
            item.setTransform(pg.Transform3D(*m.flatten()))
        self._place(self.target, target_xyz)
        self._place(self.tipmark, tip)
        # reach-region ring around the target
        rr = self.cfg.game.reach_dist
        th = np.linspace(0, 2 * np.pi, 48)
        ring = np.column_stack([target_xyz[0] + rr * np.cos(th),
                                target_xyz[1] + rr * np.sin(th),
                                np.full(48, self.cfg.control.z_plane)])
        self._region.setData(pos=ring)

    @staticmethod
    def _place(item, p) -> None:
        item.resetTransform()
        item.translate(float(p[0]), float(p[1]), float(p[2]))
