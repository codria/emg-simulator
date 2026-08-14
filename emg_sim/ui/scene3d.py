"""3D scene: floor, base, arm links, target sphere (PyQtGraph GLViewWidget).

Deliberately simple geometry for the MVP — a link polyline with joint dots, a
grid floor, a base box and a target sphere. The fancy curved arm mesh from the
C++ renderer is deferred (see docs §2.5); this is enough to see the arm move.
"""

from __future__ import annotations

import numpy as np
import pyqtgraph as pg
import pyqtgraph.opengl as gl


class Scene3D(gl.GLViewWidget):
    def __init__(self, cfg):
        super().__init__()
        self.cfg = cfg
        self.setCameraPosition(distance=1.7, elevation=22, azimuth=40)
        self.opts["center"] = pg.Vector(0.0, 0.0, 0.12)
        self.setBackgroundColor(pg.mkColor(20, 20, 28))

        z_floor = cfg.control.z_plane - 0.05

        floor = gl.GLGridItem()
        floor.setSize(1.8, 1.8)
        floor.setSpacing(0.1, 0.1)
        floor.translate(0, 0, z_floor)
        floor.setColor((120, 120, 140, 120))
        self.addItem(floor)

        # base box (pedestal top at z_plane)
        base = gl.GLBoxItem(size=pg.Vector(0.12, 0.12, 0.05), color=(160, 170, 190, 255))
        base.translate(-0.06, -0.06, z_floor)
        self.addItem(base)

        # operation-plane ring hint (inner/outer reach radius)
        self._add_ring(cfg.control.r_min, (90, 160, 220, 90))
        self._add_ring(cfg.control.r_max, (90, 160, 220, 90))

        self.chain = gl.GLLinePlotItem(width=7.0, antialias=True, color=(0.82, 0.87, 0.95, 1.0))
        self.addItem(self.chain)
        self.joints = gl.GLScatterPlotItem(size=11.0, color=(0.45, 0.68, 1.0, 1.0))
        self.addItem(self.joints)

        tmd = gl.MeshData.sphere(rows=14, cols=14, radius=cfg.game.reach_dist)
        self.target = gl.GLMeshItem(meshdata=tmd, smooth=True, color=(1.0, 0.42, 0.32, 0.85),
                                    shader="shaded", glOptions="translucent")
        self.addItem(self.target)

        pmd = gl.MeshData.sphere(rows=10, cols=10, radius=0.022)
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
        pts = np.array([T[:3, 3] for T in Ts] + [np.asarray(tip)])
        self.chain.setData(pos=pts)
        self.joints.setData(pos=pts)
        self._place(self.target, target_xyz)
        self._place(self.tipmark, tip)

    @staticmethod
    def _place(item, p) -> None:
        item.resetTransform()
        item.translate(float(p[0]), float(p[1]), float(p[2]))
