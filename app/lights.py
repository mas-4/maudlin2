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

At night (sunset to sunrise where the machine is, from PLACE; NIGHT to DAY until that's set) the room stays dark: off,
working or not (Oct 12: the dim ember breathing while it worked kept
Terra, the dog, up all night: "your freaking computer keeps me up at night grrrr"). The
case fans on the board take the same colour. Picked with the person on Oct 11 from a demo of each (the meteor effect
ignores its colour, "rainbow goop", and so does the wave; breathing at the fastest speed looked like blinking).

It talks to OpenRGB's server (deploy/systemd/user/openrgb-server.service) and changes the card only when the look
does, so the card's effects run smoothly in between. deploy/systemd/rgb-off.service sets everything dark at boot and
after a wake, should this not be running.

If OpenRGB came up before the card's I2C was ready (it does at some boots: "One or more I2C/SMBus interfaces failed
to initialize"), it serves no devices and the bar stays as it was; the lights then restart it and look again (Oct 12:
blind from an 08:23 boot until noon).

Run: python -m app.lights"""
import json
import math
import os
import subprocess
import time
from datetime import datetime as dt

from app.utils import get_logger

logger = get_logger(__name__)

GPU = 'MSI GeForce RTX 3080 Gaming Z Trio LHR'
BOARD = 'MSI PRO Z790-P WIFI (MS-7E06)'
DAY, NIGHT = 8, 23  # hours: the lights work from DAY until NIGHT, until PLACE is set
PLACE = 'lights_place.json'  # {'lat', 'lon'} in the data folder, not the repo: where the sun sets for the lights
BLIND_WAIT = 60  # seconds: with no devices, wait this long, restart OpenRGB and start again
LOOK = 2.0  # seconds between looks at the GPU and the machine's state
STUCK = 120  # seconds of failed looks before the lights exit for systemd to start them afresh
LOG, LOG_KEEP = 'lights_log.csv', 1440  # who had the GPU each minute, the last day of it
HOT, LIMIT = 85, 93  # degrees C: the card runs at ~83 under load; its slowdown limit is 93
PARTY = 'lights_party.json'  # {'until': epoch seconds}: the Stream Deck's 🦄 key asks for the rainbow until then

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


def log(holder: str, load: float):
    """A line in LOG: when, who had the GPU, its load; kept to its last LOG_KEEP lines"""
    from app.utils import Config
    path = os.path.join(Config.data, LOG)
    with open(path, 'a') as f:
        f.write(f"{dt.now().isoformat(timespec='seconds')},{holder},{load:.0f}\n")
    if os.path.getsize(path) > LOG_KEEP * 40:
        with open(path) as f:
            lines = f.readlines()[-LOG_KEEP:]
        with open(path, 'w') as f:
            f.writelines(lines)


def party() -> bool:
    """Someone pressed the Stream Deck's 🦄 key lately (app/deck.py): the card's own rainbow until PARTY's time"""
    import json
    from app.utils import Config
    try:
        with open(os.path.join(Config.data, PARTY)) as f:
            return json.load(f).get('until', 0) > time.time()
    except (OSError, ValueError):
        return False


def sun(day, lat: float, lon: float) -> tuple[float, float] | None:
    """(sunrise, sunset) as UTC hours on `day` (a date) at lat, lon (degrees; west negative), by the Almanac for
    Computers formula (a minute or two out); None in a polar day or night"""
    n = day.timetuple().tm_yday
    rad, deg = math.radians, math.degrees
    out = []
    for rising in (True, False):
        t = n + ((6 if rising else 18) - lon / 15) / 24
        m = 0.9856 * t - 3.289
        sun_lon = (m + 1.916 * math.sin(rad(m)) + 0.020 * math.sin(rad(2 * m)) + 282.634) % 360
        ra = deg(math.atan(0.91764 * math.tan(rad(sun_lon)))) % 360
        ra = (ra + (sun_lon // 90) * 90 - (ra // 90) * 90) / 15
        sin_dec = 0.39782 * math.sin(rad(sun_lon))
        cos_dec = math.cos(math.asin(sin_dec))
        cos_h = (math.cos(rad(90.833)) - sin_dec * math.sin(rad(lat))) / (cos_dec * math.cos(rad(lat)))
        if not -1 <= cos_h <= 1:
            return None
        h = (360 - deg(math.acos(cos_h)) if rising else deg(math.acos(cos_h))) / 15
        out.append((h + ra - 0.06571 * t - 6.622 - lon / 15) % 24)
    return out[0], out[1]


def night(when: dt | None = None) -> bool:
    """Is it between sunset and sunrise where the machine is (PLACE), or between NIGHT and DAY if that isn't set"""
    from datetime import UTC
    from app.utils import Config
    when = (when or dt.now()).astimezone()
    try:
        with open(os.path.join(Config.data, PLACE)) as f:
            place = json.load(f)
        times = sun(when.date(), float(place['lat']), float(place['lon']))
    except (OSError, ValueError, KeyError, TypeError):
        times = None
    if times is None:
        hour = when.hour + when.minute / 60
        return hour >= NIGHT or hour < DAY
    utc = when.astimezone(UTC)
    hour = utc.hour + utc.minute / 60
    rise, set_ = times
    return not (rise <= hour < set_ if rise < set_ else hour >= rise or hour < set_)  # day may cross midnight UTC


def mix(a, b, t: float):
    t = max(0.0, min(1.0, t))
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def look(state: dict, dark: bool) -> tuple:
    """(effect, colour, speed 0-2, brightness 0-5) for the state: {'who', 'load', 'temp', 'failed', 'party'};
    dark: it's night (night())"""
    working = not (state['who'] == 'idle' and state['load'] < 10)
    if state.get('party') and state['temp'] < LIMIT:  # the 🦄 key: the unicorn puke on demand, night or day
        return ('Rainbow', VIOLET, 2, 5)
    if dark:  # the room stays dark, for the dog
        return ('Direct', DARK, 0, 0)
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
    if gpu is None and board is None:  # OpenRGB came up blind: restart it, and start again (systemd restarts this)
        logger.warning("Lights: OpenRGB has no devices; restarting it in %d s", BLIND_WAIT)
        time.sleep(BLIND_WAIT)
        subprocess.run(['systemctl', '--user', 'restart', 'openrgb-server.service'], timeout=60)
        return
    from app import worker
    start = worker.commit()
    shown, shown_at, smooth, logged, failing = None, 0.0, 0.0, 0.0, False
    while True:
        if worker.commit() != start:  # the hourly run pulled new code: exit, and systemd starts this again on it
            logger.info("Lights: new code; exiting so systemd starts them again on it")
            return
        try:
            load, temp = card()
            # The load jumps second to second; a new brightness restarts the card's effect, so it follows a ~20 s
            # average
            smooth += (load - smooth) * LOOK / 20
            state = {'who': who(), 'load': smooth, 'temp': temp, 'failed': failed(), 'party': party()}
            if time.time() - logged >= 60:  # who had the GPU, a minute a line, for the desktop widget's sparkline
                log(state['who'], load)
                logged = time.time()
            now = look(state, night())
            if now != shown or time.time() - shown_at > 60:  # again each minute: after a wake rgb-off has set it dark
                if gpu is not None:
                    show(gpu, *now)
                if board is not None:  # the fans: one colour, no effects worth having
                    show(board, 'Static', now[1] if now[3] else DARK, 0, 0)
                shown, shown_at = now, time.time()
        except Exception as e:  # noqa: BLE001 - a missed look keeps the last lights; the next one tries again
            # its kind and where, the first time (Oct 18: a bare str(e) logged an empty line every 2 s all day, and the
            # lights stayed lit into the night)
            logger.warning("Lights: %s: %r", type(e).__name__, e, exc_info=not failing)
            failing = failing or time.time()
            if time.time() - failing > STUCK:  # a fresh process got through where this one failed all day (Oct 18)
                logger.warning("Lights: failing for %d s; exiting so systemd starts them afresh", STUCK)
                return
        else:
            failing = False
        time.sleep(LOOK)


if __name__ == '__main__':
    main()
