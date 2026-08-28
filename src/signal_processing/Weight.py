"""Weight -- one number for how heavy or light a voice reads.

Weight is the length of the vector whose components are the voice's distance
from a reference H1-A3 and its loudness::

    weight = sqrt((H1_A3_REFERENCE - H1_A3)^2 + (LOUDNESS_WEIGHT * loudness)^2)

Both inputs come straight off the frames openSMILE produced, already cleaned by
:meth:`AudioFeatureExtractor.extractFeatures`, so a frame that failed the
validity check is NaN in the inputs and stays NaN here -- it never reaches a
plot.
"""

import numpy as np

from signal_processing.AudioFeatures import SignalTimeSeries

#: The H1-A3 value the weight vector is measured from, in dB. A voice gets
#: heavier as its H1-A3 falls away from this.
H1_A3_REFERENCE = 50.0

#: How far a unit of loudness counts against a dB of H1-A3 distance. Named
#: rather than written into the formula because it is tuned by ear, and a bare
#: literal there is the kind of thing that changes without the tests noticing.
LOUDNESS_WEIGHT = 4.0


def calculate_weight(t, H1_A3, loudness) -> SignalTimeSeries:
    """The per-frame weight of a voice, over the timepoints ``t``.

    :param t: The frame timepoints, used unchanged as the series' x axis.
    :param H1_A3: The cleaned H1-A3 value of each frame, in dB.
    :param loudness: The cleaned loudness of each frame.
    """
    weight_y = np.hypot(H1_A3_REFERENCE - np.asarray(H1_A3, dtype=float),
                        np.multiply(LOUDNESS_WEIGHT, np.asarray(loudness, dtype=float)))
    return SignalTimeSeries(x=t, y=weight_y)
