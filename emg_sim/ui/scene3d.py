"""3D scene: floor, base, parametric arm, target sphere (PyQtGraph GLViewWidget).

The arm is drawn from the ported parametric parts (armmesh.build_parts) — one
GLMeshItem per part, re-transformed each frame by its parent joint frame. Floor
grid, base box, reach rings (r_min / r_max) and a target sphere complete the
scene.
"""

from __future__ import annotations

import numpy as np
import pyqtgraph as pg
import pyqtgraph.opengl as gl

from . import armmesh


class Scene3D(gl.GLViewWidget):
    def __init__(self, cfg):
        super().__init__()
        self.cfg = cfg
        self.setCameraPosition(distance=1.7, elevation=20, azimuth=40)
        self.opts["center"] = pg.Vector(0.0, 0.0, 0.18)
        self.setBackgroundColor(pg.mkColor(20, 20, 28))

        z_floor = cfg.control.z_plane - 0.05

        floor = gl.GLGridItem()
        floor.setSize(1.8, 1.8)
        floor.setSpacing(0.1, 0.1)
        floor.translate(0, 0, z_floor)
        floor.setColor((120, 120, 140, 110))
        self.addItem(floor)

        ped_v = armmesh.cylinder_tris(0.09, 0.05, 48)
        ped = gl.GLMeshItem(
            meshdata=gl.MeshData(vertexes=ped_v, faces=np.arange(len(ped_v)).reshape(-1, 3)),
            smooth=False, color=(0.30, 0.32, 0.38, 1.0), shader="shaded", glOptions="opaque")
        ped.translate(0, 0, z_floor + 0.025)
        self.addItem(ped)

        # reach fan (arcs at r_min/r_max over the θ range + radial edges).
        # Rebuilt every frame from cfg so it tracks the r_min/r_max/θ sliders,
        # and the sector shape + front arrow make the forward direction clear.
        fan = (90 / 255, 160 / 255, 220 / 255, 1.0)
        self._arc_in = gl.GLLinePlotItem(width=2.0, antialias=True, color=fan)
        self._arc_out = gl.GLLinePlotItem(width=2.0, antialias=True, color=fan)
        self._edge_lo = gl.GLLinePlotItem(width=2.0, antialias=True, color=fan)
        self._edge_hi = gl.GLLinePlotItem(width=2.0, antialias=True, color=fan)
        self._front = gl.GLLinePlotItem(width=3.5, antialias=True, color=(1.0, 0.82, 0.30, 1.0),
                                        mode="lines")
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
            faces = np.arange(len(v)).reshape(-1, 3)
            md = gl.MeshData(vertexes=v, faces=faces)
            item = gl.GLMeshItem(meshdata=md, smooth=False, color=(*part["color"], 1.0),
                                 shader="shaded", glOptions="opaque")
            self.addItem(item)
            self.parts.append((item, part["parent"], part["xform"]))

        tmd = gl.MeshData.sphere(rows=14, cols=14, radius=cfg.game.reach_dist)
        self.target = gl.GLMeshItem(meshdata=tmd, smooth=True, color=(1.0, 0.42, 0.32, 0.8),
                                    shader="shaded", glOptions="translucent")
        self.addItem(self.target)

        pmd = gl.MeshData.sphere(rows=8, cols=8, radius=0.02)
        self.tipmark = gl.GLMeshItem(meshdata=pmd, smooth=True, color=(0.35, 1.0, 0.55, 1.0),
                                     shader="shaded")
        self.addItem(self.tipmark)

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
        # front arrow (with arrowhead) along the fan centre
        thm = 0.5 * (c.theta_min + c.theta_max)
        d = np.array([np.cos(thm), np.sin(thm), 0.0])
        perp = np.array([-np.sin(thm), np.cos(thm), 0.0])
        base = np.array([0.0, 0.0, z]) + c.r_min * 0.35 * d
        tip = np.array([0.0, 0.0, z]) + c.r_max * 1.12 * d
        hl = tip - 0.07 * d + 0.045 * perp
        hr = tip - 0.07 * d - 0.045 * perp
        self._front.setData(pos=np.array([base, tip, tip, hl, tip, hr]))  # mode="lines" → pairs
        if self._front_label is not None:
            self._front_label.setData(pos=tip + 0.04 * d + np.array([0, 0, 0.02]))

    def update_state(self, arm, target_xyz, tip) -> None:
        self._update_fan()
        Ts = arm.forward_kinematics()
        for item, parent, xform in self.parts:
            m = Ts[parent + 1] @ xform
            item.setTransform(pg.Transform3D(*m.flatten()))
        self._place(self.target, target_xyz)
        self._place(self.tipmark, tip)

    @staticmethod
    def _place(item, p) -> None:
        item.resetTransform()
        item.translate(float(p[0]), float(p[1]), float(p[2]))
