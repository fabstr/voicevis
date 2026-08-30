"""What the microphone pump promises: it keeps reading until it is stopped.

The loop is driven directly rather than on its own thread. What matters here
is that it keeps calling back until ``stop``, and that one failed read does
not end the take -- both of which are decided inside ``run``, whichever thread
happens to be running it.
"""

from workers.AudioPumpWorker import AudioPumpWorker


def test_reads_until_stopped():
    calls = []

    def read():
        calls.append(len(calls))
        if len(calls) == 3:
            pump.stop()

    pump = AudioPumpWorker(read)
    pump.run()

    assert calls == [0, 1, 2]


def test_a_failed_read_does_not_end_the_take():
    calls = []

    def read():
        calls.append(len(calls))
        if len(calls) == 1:
            raise OSError("device hiccup")
        if len(calls) == 3:
            pump.stop()

    pump = AudioPumpWorker(read)
    pump.run()

    assert calls == [0, 1, 2]
