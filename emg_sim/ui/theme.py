"""Shared UI palette so the bars, EMG graphs and the 3D scene use one consistent,
unambiguous colour per concept. RGB 0-255 tuples."""

R_COLOR = (95, 210, 255)    # right arm  — cyan  (水色) : R bar + R graph
L_COLOR = (255, 214, 90)    # left arm   — yellow (黄色): L bar + L graph
FRONT = (225, 225, 232)     # forward direction — monochrome (near-white)
FAN = (150, 155, 165)       # reach area — monochrome grey (keeps the board calm)
TARGET = (80, 230, 110)     # target sphere — green
TIP = (235, 240, 250)       # arm tip — near-white
# r/θ teaching overlay reuses the channel colours (r → R_COLOR, θ → L_COLOR).
