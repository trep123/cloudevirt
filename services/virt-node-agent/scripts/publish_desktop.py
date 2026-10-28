"""Read a private capture specification from stdin; never expose credentials in argv."""

import json
import signal
import sys


def main():
    import gi

    gi.require_version("Gst", "1.0")
    from gi.repository import GLib, Gst

    Gst.init(None)
    config = json.loads(sys.stdin.buffer.read(16385))
    port = config["port"]
    if not isinstance(port, int) or not 1 <= port <= 65535:
        return 2
    # Encode complete framebuffer snapshots. Delta-only buffers can lose static pixels
    # when passed through a continuously clocked video encoder; bound capture to 15 Hz.
    pipeline = Gst.parse_launch(
        "rfbsrc name=capture host=127.0.0.1 shared=true view-only=true incremental=false "
        "! identity sleep-time=66666 "
        "! queue max-size-buffers=2 leaky=downstream "
        "! imagefreeze is-live=true allow-replace=true "
        "! videoconvert ! videoscale add-borders=true "
        "! video/x-raw,format=I420,width=1280,height=720,framerate=15/1 "
        "! x264enc tune=zerolatency speed-preset=ultrafast bitrate=2500 key-int-max=15 bframes=0 "
        "! video/x-h264,profile=baseline ! h264parse "
        "! rtspclientsink name=publisher protocols=tcp latency=100"
    )
    capture = pipeline.get_by_name("capture")
    capture.set_property("port", port)
    capture.set_property("password", config["password"])
    pipeline.get_by_name("publisher").set_property("location", config["url"])
    config.clear()
    loop = GLib.MainLoop()
    outcome = [0]

    def stop(*_):
        loop.quit()
        return False

    def message(_, msg):
        if msg.type in (Gst.MessageType.ERROR, Gst.MessageType.EOS):
            outcome[0] = 1
            stop()

    bus = pipeline.get_bus()
    bus.add_signal_watch()
    bus.connect("message", message)
    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, stop)
    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGINT, stop)
    try:
        if pipeline.set_state(Gst.State.PLAYING) == Gst.StateChangeReturn.FAILURE:
            return 1
        loop.run()
        return outcome[0]
    finally:
        pipeline.set_state(Gst.State.NULL)
        bus.remove_signal_watch()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:  # noqa: BLE001 - redact credentials at this subprocess boundary.
        # GStreamer errors can contain publishing URLs; do not log raw exceptions.
        print("DESKTOP_PUBLISHER_FAILED", file=sys.stderr)
        raise SystemExit(1)
