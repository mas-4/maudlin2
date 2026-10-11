"""The case lights as a GPU monitor (Oct 11, the person: "some kind of gpu business monitor during the day and then at
night it be off or even in a night mode with dark colors"). The MSI card's light bar says who has the GPU and how hard
it's working, in the card's own effects (OpenRGB sets one colour for the whole bar: its six LEDs can't be set apart on
Linux, OpenRGB issue 2284; the card's effects do animate them, and dimming by darker colours looked poor, so
brightness is the card's own 0-5):

    the worker              teal, breathing slowly; brighter with the load
    an experiment's lease   violet, flowing
    the hourly run          amber, flowing
    nothing                 blue, breathing slowly and dim
    last hourly run failed  red, double-flashing (until a run succeeds)
    hot (HOT C and up)      the colour turns toward orange; at LIMIT, red flashing

At night (NIGHT to DAY) the room stays dark: off while the GPU is idle, a dim ember breathing while it works. The
case fans on the board take the same colour. Picked with the person on Oct 11 from a demo of each (the meteor effect
ignores its colour, "rainbow goop", and so does the wave; breathing at the fastest speed looked like blinking).

It talks to OpenRGB's server (deploy/systemd/user/openrgb-server.service) and changes the card only when the look
does, so the card's effects run smoothly in between. deploy/systemd/rgb-off.service sets everything dark at boot and
after a wake, should this not be running.

Run: python -m app.lights"""
import subprocess
import time
from datetime import datetime as dt

from app.utils import get_logger

logger = get_logger(__name__)

GPU = 'MSI GeForce RTX 3080 Gaming Z Trio LHR'
BOARD = 'MSI PRO Z790-P WIFI (MS-7E06)'
DAY, NIGHT = 8, 23  # hours: the lights work from DAY until NIGHT
LOOK = 2.0  # seconds between looks at the GPU and the machine's state
HOT, LIMIT = 85, 93  # degrees C: the card runs at ~83 under load; its slowdown limit is 93

AMBER, VIOLET, TEAL, IDLE = (255, 140, 0), (140, 60, 255), (0, 190, 170), (40, 80, 200)
ORANGE, RED, EMBER, DARK = (255, 70, 0), (255, 0, 0), (120, 12, 0), (0, 0, 0)


def who() -> str:
    """Who has the GPU now: 'hourly', 'experiment', 'worker' or 'idle'"""
    from app import gpu_lease, worker
    if worker.run_going():
        return 'hourly'
    if gpu_lease.held() is not None:
        return 'experiment'
    return 'worker' if worker.busy() else 'idle'


def failed() -> bool:
    """The last hourly run failed (systemd keeps its result until the next one)"""
    out = subprocess.run(['systemctl', 'show', '-p', 'Result', '--value', 'maudlin-scrape.service'],
                         capture_output=True, text=True).stdout.strip()
    return out not in ('success', '')


def card() -> tuple[float, float]:
    """(load 0-100, temperature C) of the GPU"""
    out = subprocess.run(['nvidia-smi', '--query-gpu=utilization.gpu,temperature.gpu', '--format=csv,noheader,nounits'],
                         capture_output=True, text=True, timeout=10).stdout.strip().split(',')
    return float(out[0]), float(out[1])


def mix(a, b, t: float):
    t = max(0.0, min(1.0, t))
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def look(state: dict, hour: float) -> tuple:
    """(effect, colour, speed 0-2, brightness 0-5) for the state: {'who', 'load', 'temp', 'failed'}; hour: 0-24"""
    working = not (state['who'] == 'idle' and state['load'] < 10)
    if hour >= NIGHT or hour < DAY:  # the room stays dark
        return ('Breathing', EMBER, 0, 1) if working else ('Direct', DARK, 0, 0)
    if state['temp'] >= LIMIT:
        return ('Flashing', RED, 1, 5)
    if state['failed'] and state['who'] != 'hourly':
        return ('Doubleflashing', RED, 0, 3)
    if not working:
        return ('Breathing', IDLE, 0, 2)
    effect, colour = {'hourly': ('Flowing', AMBER), 'experiment': ('Flowing', VIOLET)}.get(state['who'], ('Breathing', TEAL))
    colour = mix(colour, ORANGE, (state['temp'] - HOT) / (LIMIT - HOT))
    return effect, colour, 0, 2 + min(3, int(state['load'] / 25))  # 2 at light load, 5 from 75%


def show(device, effect: str, colour: tuple, speed: int, brightness: int):
    from openrgb.utils import RGBColor
    mode = next(m for m in device.modes if m.name == effect)
    if mode.speed_min is not None:
        mode.speed = speed
    if getattr(mode, 'brightness_min', None) is not None:
        mode.brightness = brightness
    device.set_mode(mode)
    device.set_color(RGBColor(*colour))


def main():
    from openrgb import OpenRGBClient
    client = None
    while client is None:
        try:
            client = OpenRGBClient('127.0.0.1', 6742, 'maudlin lights')
        except (ConnectionRefusedError, OSError):
            time.sleep(5)
    devices = {d.name: d for d in client.devices}
    gpu, board = devices.get(GPU), devices.get(BOARD)
    logger.info("Lights: %s", ', '.join(devices))
    shown, shown_at, smooth = None, 0.0, 0.0
    while True:
        try:
            load, temp = card()
            # The load jumps second to second; a new brightness restarts the card's effect, so it follows a ~20 s
            # average
            smooth += (load - smooth) * LOOK / 20
            state = {'who': who(), 'load': smooth, 'temp': temp, 'failed': failed()}
            d = dt.now()
            now = look(state, d.hour + d.minute / 60)
            if now != shown or time.time() - shown_at > 60:  # again each minute: after a wake rgb-off has set it dark
                if gpu is not None:
                    show(gpu, *now)
                if board is not None:  # the fans: one colour, no effects worth having
                    show(board, 'Static', now[1] if now[3] else DARK, 0, 0)
                shown, shown_at = now, time.time()
        except Exception as e:  # noqa: BLE001 - a missed look keeps the last lights; the next one tries again
            logger.warning("Lights: %s", e)
        time.sleep(LOOK)


if __name__ == '__main__':
    main()
