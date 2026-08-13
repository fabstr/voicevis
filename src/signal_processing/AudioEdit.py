"""Edits on the in-memory PCM buffer.

The audio is a flat ``QByteArray`` of mono signed 16-bit samples, so every edit
is a byte-range operation. Ranges are given in seconds and clipped to the buffer,
which keeps the callers free of sample arithmetic.
"""

import logging

from PyQt6.QtCore import QByteArray

BYTES_PER_SAMPLE = 2


def byte_offset(seconds: float, sample_rate: int) -> int:
    """The byte where a moment in time starts, never negative."""
    return max(0, int(round(seconds * sample_rate))) * BYTES_PER_SAMPLE


def duration(audio: QByteArray, sample_rate: int) -> float:
    return audio.size() / (BYTES_PER_SAMPLE * sample_rate)


def _clipped_range(audio, start_s, end_s, sample_rate):
    low = min(byte_offset(start_s, sample_rate), audio.size())
    high = min(byte_offset(end_s, sample_rate), audio.size())
    return (low, high) if high > low else (0, 0)


def silence(audio: QByteArray, start_s: float, end_s: float, sample_rate: int) -> bool:
    """Replace a stretch of audio with silence. Returns False if nothing changed."""
    low, high = _clipped_range(audio, start_s, end_s, sample_rate)
    if high <= low:
        return False

    audio.replace(low, high - low, QByteArray(high - low, b'\x00'))
    logging.debug("Silenced %.3fs..%.3fs", start_s, end_s)
    return True


def cut(audio: QByteArray, start_s: float, end_s: float, sample_rate: int) -> bool:
    """Remove a stretch of audio and close the gap.

    Unlike :func:`silence`, the recording gets shorter and everything after the
    cut moves earlier.
    """
    low, high = _clipped_range(audio, start_s, end_s, sample_rate)
    if high <= low:
        return False

    audio.remove(low, high - low)
    logging.debug("Cut %.3fs..%.3fs", start_s, end_s)
    return True


def move(audio: QByteArray, start_s: float, end_s: float, delta_s: float,
         sample_rate: int) -> bool:
    """Move a stretch of audio, overwriting whatever it lands on.

    The source is left silent, so this is a move rather than a copy. The chunk
    is taken before the source is cleared, which makes an overlapping move --
    nudging a selection slightly -- come out right.
    """
    low, high = _clipped_range(audio, start_s, end_s, sample_rate)
    if high <= low:
        return False

    shift = int(round(delta_s * sample_rate)) * BYTES_PER_SAMPLE
    if shift == 0:
        return False

    chunk = audio.mid(low, high - low)
    destination = low + shift

    # Dragging past the start clips the front of the chunk rather than wrapping.
    if destination < 0:
        clipped = -destination
        if clipped >= chunk.size():
            return False
        chunk = chunk.mid(clipped)
        destination = 0

    audio.replace(low, high - low, QByteArray(high - low, b'\x00'))

    # Dragging past the end grows the buffer instead of truncating the audio.
    overrun = destination + chunk.size() - audio.size()
    if overrun > 0:
        audio.append(QByteArray(overrun, b'\x00'))

    audio.replace(destination, chunk.size(), chunk)
    logging.debug("Moved %.3fs..%.3fs by %.3fs", start_s, end_s, delta_s)
    return True
