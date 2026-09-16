"""Small original Home chime, generated locally without media dependencies."""

from array import array
from io import BytesIO
from math import exp, pi, sin
import sys
import wave


def home_chime_wav() -> bytes:
    rate = 22050
    samples = array("h")
    for index in range(int(rate * 1.8)):
        t = index / rate
        value = 0.0
        for onset, frequency in ((0.0, 523.25), (0.45, 659.25)):
            age = t - onset
            if age >= 0:
                envelope = min(age / 0.025, 1.0) * exp(-3.5 * age)
                value += 0.26 * envelope * (
                    sin(2 * pi * frequency * age)
                    + 0.15 * sin(2 * pi * frequency * 2 * age)
                )
        value *= min((1.8 - t) / 0.1, 1.0)
        samples.append(round(32767 * value))
    if sys.byteorder != "little":
        samples.byteswap()
    stream = BytesIO()
    with wave.open(stream, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(rate)
        audio.writeframes(samples.tobytes())
    return stream.getvalue()
