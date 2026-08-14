"""Kinematics: 6-DOF arm model + damped-least-squares IK (ported from C++)."""

from .arm import (
    Axis,
    Joint,
    ArmDimensions,
    DEFAULT_DIMS,
    IKOptions,
    Manipulator,
    make_standard_arm,
    TIP_OFFSET_LOCAL,
)

__all__ = [
    "Axis",
    "Joint",
    "ArmDimensions",
    "DEFAULT_DIMS",
    "IKOptions",
    "Manipulator",
    "make_standard_arm",
    "TIP_OFFSET_LOCAL",
]
