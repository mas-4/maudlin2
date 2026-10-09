"""The work after the site is built: transcription, the nightly narrative report, claims from the shows and the
Focus Group, the radio running order, TV chyrons, filing claims in the motif index, their fits, the weekly reranker
teaching and the nightly proposals. The hourly run did it all after its build until Oct 9; now the worker (app/worker.py)
does it whenever the GPU is free, and the hourly run only when no worker is up (main.py). Each step has a budget, and
none starts later than leaves `reserve` seconds of `limit` (FILING_RESERVE: kept for filing claims and their fits)."""
import os
import sys
import time
from datetime import datetime as dt

from app.utils import get_logger

logger = get_logger(__name__)

NARRATIVE_HOUR = 4  # the run that writes the day's narrative report
SHOW_BUDGET = 420  # seconds a run spends reading the shows' transcripts for claims (about 280 parts a day at ~35 s)
FOCUS_BUDGET = 180  # seconds a run spends reading new Focus Group episodes (one a week, about a minute and a half)
RUNNING_BUDGET = 120  # seconds a run spends splitting the radio newscasts into their stories (two an hour)
CHYRON_BUDGET = 180  # seconds a run spends cleaning TV chyron OCR (about 45 minutes of work a day)
MOTIF_BUDGET = 300  # seconds a run spends filing claims in the motif index
FIT_BUDGET = 240  # seconds a run spends scoring new filings (reranker and a yes/no from the filing model per filing)
PROPOSAL_HOUR = 5  # the motif proposer's nightly run: after the 4 AM report and its first filings
TEACH_HOUR = 1  # the weekly reranker teaching starts in this hour's run (done by the 4 AM report)
FILING_RESERVE = 600  # seconds kept back for filing claims and their fits, whatever the steps before them want


def teaching() -> bool:
    """Whether a reranker teaching is still running (one at a time)"""
    import subprocess
    return subprocess.run(['pgrep', '-f', '[a]pp.analysis.reranker_teach'], capture_output=True).returncode == 0


def process(limit: float, reserve: float = FILING_RESERVE, stop=None) -> None:
    """Every step in turn, within `limit` seconds from now; `stop()` true (the worker: the hourly run has begun, or an
    experiment holds the GPU lease) skips the steps not begun"""
    t = time.time()

    def budget(want: float, step: str, keep: float = reserve) -> float:
        """A step's seconds: what it wants, but no more than leaves `keep` before the run's limit; 0 skips it"""
        left = t + limit - time.time() - keep
        if stop is not None and stop():
            logger.info("%s left for later: the GPU is wanted (the hourly run, or an experiment's lease)", step)
            return 0
        if left < 30:
            logger.warning("%s skipped this run: %.0f minutes in, no time left before the limit", step,
                           (time.time() - t) / 60)
            return 0
        return min(want, left)
    # The language model is done for this run: Whisper gets the GPU for up to ten minutes
    from app.transcribe import transcribe_pending
    if (b := budget(600, 'Transcription')):
        transcribe_pending(budget=b)
    # Once a night, the day's narratives (research only, #142): the GPU has nothing else to do at 4 AM. If that
    # run was missed (Oct 5: the machine hung in sleep from 3 to 7), the next run after 4 AM makes up for it
    from app import narratives
    reported = False
    if dt.now().hour >= NARRATIVE_HOUR and not narratives.made_today() and not (stop is not None and stop()):
        reported = True
        from app.analysis import circulation
        narratives.report(hours=24)
        from app.analysis import narrative_threads
        narrative_threads.link_days()  # the same narratives told on earlier days
        circulation.nightly()  # which fact-checked rumors people are telling or arguing over (#153)
    # New claims into our own motif index (#145), a few minutes a run with the bigger model, so a night with a
    # long report can't push a run past its time limit; what's left waits for the next run
    # What voters say in The Focus Group's episodes (#164), read once per episode with the bigger model
    from app.analysis import focus_group
    if (b := budget(FOCUS_BUDGET, 'Focus group claims')):
        focus_group.extract(budget=b)
    # What's told on every show we transcribe, right, left and center (talk radio, call-ins, podcasts), never in
    # the report's run: it nears the 45-minute limit
    if not reported:
        from app.analysis import show_claims
        if (b := budget(SHOW_BUDGET, 'Show claims')):
            show_claims.extract(budget=b)
    # The hourly radio newscasts' running order beside the front pages' (#159)
    from app.analysis import running_order
    if (b := budget(RUNNING_BUDGET, 'Running order')):
        running_order.read(budget=b)
    # TV chyrons: the OCR read into headlines, names, promos and ads, a few minutes a run
    from app import chyrons
    if (b := budget(CHYRON_BUDGET, 'Chyrons')):
        chyrons.clean_recent(budget=b)
        chyrons.match_recent()
    from app.analysis import motif_index
    if (b := budget(MOTIF_BUDGET, 'Motif filing', keep=FIT_BUDGET)):
        motif_index.nightly(budget=b)
    # How sure each new filing is (its fit: many signals weighed on the person's own decisions), for the checker
    if not reported:  # never in the report's run: it nears the 45-minute limit
        from app.analysis import filing_confidence
        try:
            if (b := budget(FIT_BUDGET, 'Filing confidence', keep=0)):
                filing_confidence.refresh(budget=b)
        except Exception as e:  # noqa: BLE001 - the fits wait for the next run
            logger.warning("Filing confidence failed: %s", e)
        # Weekly at night: the reranker taught the person's latest decisions, on the CPU in a process of its own
        # (about two and a half hours at low priority; the next runs carry on beside it)
        if dt.now().hour == TEACH_HOUR:
            try:
                from app.analysis import reranker_teach
                if reranker_teach.due() and not teaching():
                    import subprocess
                    subprocess.Popen(['nice', '-n', '19', sys.executable, '-m', 'app.analysis.reranker_teach'],
                                     cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))), start_new_session=True,
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    logger.info("Reranker teaching started")
            except Exception as e:  # noqa: BLE001 - next week
                logger.warning("Reranker teaching didn't start: %s", e)
    # Fixes for a person to approve in the workbench (typos, links, groups), once a day after the new filings
    if dt.now().hour >= PROPOSAL_HOUR and not reported:  # never in the report's run: it nears the 45-minute limit
        from app.analysis import motif_proposals
        if (b := budget(motif_proposals.NIGHT_BUDGET, 'Motif proposals', keep=0)):
            motif_proposals.nightly(budget=b)
