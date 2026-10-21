"""The work after the site is built: transcription, the nightly narrative report, claims from the shows and the
Focus Group, the radio running order, TV chyrons, filing claims in the motif index, plain news filed again, their fits,
the weekly reranker teaching and the nightly proposals. The hourly run did it all after its build until Oct 9; now the
worker (app/worker.py) does it whenever the GPU is free, and the hourly run only when no worker is up (main.py).

STEPS is the schedule, in the order the steps run (Oct 21, Fable's architecture review: what ran when had been
spread over hour tests in a 130-line function). Each step says how many seconds it wants, how many it leaves for the
steps after it (FILING_RESERVE: kept for filing claims and their fits), the hours it may run in, and whether it runs in
the cycle that writes the night's report, which nears the time limit. A step that fails is logged and the next one
runs."""
import os
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime as dt

from app.utils import get_logger

logger = get_logger(__name__)

SHOW_BUDGET = 420  # seconds a run spends reading the shows' transcripts for claims (about 280 parts a day at ~35 s)
FOCUS_BUDGET = 180  # seconds a run spends reading new Focus Group episodes (one a week, about a minute and a half)
RUNNING_BUDGET = 120  # seconds a run spends splitting the radio newscasts into their stories (two an hour)
CHYRON_BUDGET = 180  # seconds a run spends cleaning TV chyron OCR (about 45 minutes of work a day)
MOTIF_BUDGET = 300  # seconds a run spends filing claims in the motif index
SPLIT_BUDGET = 120  # seconds for the children of splits the person approved
FIT_BUDGET = 240  # seconds a run spends scoring new filings (reranker and a yes/no from the filing model per filing)
FILING_RESERVE = 600  # seconds kept back for filing claims and their fits, whatever the steps before them want


def teaching() -> bool:
    """Whether a reranker teaching is still running (one at a time)"""
    import subprocess
    return subprocess.run(['pgrep', '-f', '[a]pp.analysis.reranker_teach'], capture_output=True).returncode == 0


# The steps' work, each given its seconds
def _transcribe(budget: float):
    from app.transcribe import transcribe_pending
    transcribe_pending(budget=budget)


def _report(budget: float):
    """The day's narratives (research only, #142): the GPU has nothing else to do at 4 AM. If that cycle was missed
    (Oct 5: the machine hung in sleep from 3 to 7), the next one after 4 AM makes up for it"""
    from app import narratives
    from app.analysis import circulation, narrative_threads
    narratives.report(hours=24)
    narrative_threads.link_days()  # the same narratives told on earlier days
    circulation.nightly()  # which fact-checked rumors people are telling or arguing over (#153)


def _report_due() -> bool:
    from app import narratives
    return not narratives.made_today()


def _focus_group(budget: float):  # what voters say in The Focus Group's episodes (#164), once per episode
    from app.analysis import focus_group
    focus_group.extract(budget=budget)


def _show_claims(budget: float):  # what's told on every show we transcribe, right, left and center
    from app.analysis import show_claims
    show_claims.extract(budget=budget)


def _running_order(budget: float):  # the hourly radio newscasts' running order beside the front pages' (#159)
    from app.analysis import running_order
    running_order.read(budget=budget)


def _chyrons(budget: float):  # TV chyrons: the OCR read into headlines, names, promos and ads
    from app import chyrons
    chyrons.clean_recent(budget=budget)
    chyrons.match_recent()


def _motif_filing(budget: float):  # new claims into our own motif index (#145)
    from app.analysis import motif_index
    motif_index.nightly(budget=budget)


def _split_children(budget: float):  # the children of a split the person approved, not filed then (claim_organizer)
    from app.analysis import claim_organizer
    claim_organizer.refile_pending(budget=budget)


def _plain_news(budget: float):
    """Plain news filed again against the grown index, weekly, or when a later day tells it again (watch_list.py)"""
    from app.analysis import watch_list
    watch_list.refile(budget=budget)


def _fits(budget: float):  # how sure each new filing is: many signals weighed on the person's own decisions
    from app.analysis import filing_confidence
    filing_confidence.refresh(budget=budget)


def _teach(budget: float):
    """The reranker taught the person's latest decisions, weekly, on the CPU in a process of its own (about two and a
    half hours at low priority; the next cycles carry on beside it)"""
    import subprocess
    from app.analysis import reranker_teach
    if reranker_teach.due() and not teaching():
        subprocess.Popen(['nice', '-n', '19', sys.executable, '-m', 'app.analysis.reranker_teach'],
                         cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))), start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        logger.info("Reranker teaching started")


def _proposals(budget: float):  # fixes for a person to approve in the workbench (typos, links, groups), once a day
    from app.analysis import motif_proposals
    motif_proposals.nightly(budget=budget)


@dataclass
class Step:
    name: str
    run: Callable[[float], object]
    want: float | None  # seconds it asks for; None: no budget of its own (the report)
    keep: float | None = None  # seconds left for the steps after it; None: the cycle's reserve (FILING_RESERVE)
    hours: tuple[int, int] = (0, 24)  # local hours it may start in, from the first up to (not with) the second
    in_report_cycle: bool = True  # False: skipped in the cycle that writes the night's report (it nears the limit)
    due: Callable[[], bool] | None = None  # asked last, once the step may run: is there work for it?
    report: bool = False  # this step writes the night's report


def _want(name: str) -> Callable[[], float]:
    """A budget another module keeps (read when the step runs, so a test or an experiment can change it)"""
    module, attr = name.rsplit('.', 1)

    def get() -> float:
        import importlib
        return getattr(importlib.import_module(module), attr)
    return get


STEPS = [
    Step('Transcription', _transcribe, 600),  # the language model is done for this run: Whisper gets the GPU
    Step('Narrative report', _report, None, hours=(4, 24), due=_report_due, report=True),
    Step('Focus group claims', _focus_group, FOCUS_BUDGET),
    Step('Show claims', _show_claims, SHOW_BUDGET, in_report_cycle=False),
    Step('Running order', _running_order, RUNNING_BUDGET),
    Step('Chyrons', _chyrons, CHYRON_BUDGET),
    Step('Motif filing', _motif_filing, MOTIF_BUDGET, keep=FIT_BUDGET),
    Step('Split children', _split_children, SPLIT_BUDGET, keep=FIT_BUDGET),
    Step('Plain news refiling', _plain_news, _want('app.analysis.watch_list.BUDGET'), keep=FIT_BUDGET,
         hours=(3, 4), in_report_cycle=False),  # in the night's runs, before the 4 AM report
    Step('Filing confidence', _fits, FIT_BUDGET, keep=0, in_report_cycle=False),
    Step('Reranker teaching', _teach, None, hours=(1, 2), in_report_cycle=False),  # starts a process; done by 4 AM
    Step('Motif proposals', _proposals, _want('app.analysis.motif_proposals.NIGHT_BUDGET'), keep=0, hours=(5, 24),
         in_report_cycle=False),  # after the 4 AM report and its first filings
]


def process(limit: float, reserve: float = FILING_RESERVE, stop=None, steps: list[Step] | None = None) -> None:
    """Every step in turn, within `limit` seconds from now; `stop()` true (the worker: the hourly run has begun, or an
    experiment holds the GPU lease) skips the steps not begun"""
    t = time.time()
    reported = False
    for step in STEPS if steps is None else steps:
        if not step.hours[0] <= dt.now().hour < step.hours[1]:
            continue
        if reported and not step.in_report_cycle:
            continue
        if stop is not None and stop():
            logger.info("%s left for later: the GPU is wanted (the hourly run, or an experiment's lease)", step.name)
            continue
        want = step.want() if callable(step.want) else step.want
        if want is not None:
            keep = reserve if step.keep is None else step.keep
            left = t + limit - time.time() - keep
            if left < 30:
                logger.warning("%s skipped this run: %.0f minutes in, no time left before the limit", step.name,
                               (time.time() - t) / 60)
                continue
            budget = min(want, left)
        else:
            budget = max(0.0, t + limit - time.time())
        if step.due is not None and not step.due():
            continue
        reported = reported or step.report
        try:
            step.run(budget)
        except Exception as e:  # noqa: BLE001 - one step failing mustn't stop the rest; the next cycle tries again
            logger.exception("%s failed: %s", step.name, e)
