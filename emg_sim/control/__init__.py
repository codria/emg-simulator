"""Transform / control layer (§3): activation → (r, θ) → cartesian target → IK."""

from .mapping import PolarController, polar_to_xyz

__all__ = ["PolarController", "polar_to_xyz"]
