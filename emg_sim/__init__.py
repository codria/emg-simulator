"""emg_sim — EMG-driven robot-arm reaching-game simulator.

Full-Python implementation for the open-campus exhibit (see
``docs/emg_robotarm_exhibit_design.md``). Layers per the design doc:

    acquisition -> signal_processing -> transform -> kinematics -> rendering -> game

Only ``kinematics`` (IK + arm model, ported from the C++ reference) is
implemented so far.
"""

__version__ = "0.0.1"
