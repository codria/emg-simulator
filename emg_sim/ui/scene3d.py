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

        self._add_ring(cfg.control.r_min, (90, 160, 220, 110))
        self._add_ring(cfg.control.r_max, (90, 160, 220, 110))

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

    def _add_ring(self, radius: float, color) -> None:
        th = np.linspace(0, 2 * np.pi, 96)
        pts = np.column_stack([radius * np.cos(th), radius * np.sin(th),
                               np.full_like(th, self.cfg.control.z_plane)])
        ring = gl.GLLinePlotItem(pos=pts, width=1.5, antialias=True,
                                 color=tuple(c / 255 for c in color))
        self.addItem(ring)

    def update_state(self, arm, target_xyz, tip) -> None:
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
