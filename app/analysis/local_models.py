"""The local models the app asks through Ollama (and the reranker it runs itself), named once (Oct 21, Fable's
architecture review: 'gemma4:26b' was written out in seventeen files). Each module keeps its own constant
(motif_filing.MODEL, narratives.LABEL_MODEL...) with the reason for its choice beside it, set from here: a new model for
one job is a change there, for every job a change here. Why each was chosen: docs/models.md.

The two language models can be swapped for one process by environment variable, for an experiment or a trial run:
MAUDLIN_MODEL_BIG and MAUDLIN_MODEL_DECIDER. The embedders can't: thresholds across the app are calibrated on their
scales (stories, wire copy, ties, the curators' matches)."""
import os

BIG = os.environ.get('MAUDLIN_MODEL_BIG') or 'gemma4:26b'  # filing, labelling, judging: the model nearly every job uses
DECIDER = os.environ.get('MAUDLIN_MODEL_DECIDER') or 'nimble:9b'  # quick yes/no judgments (J1: Gemma's at a fifth the time)
MXBAI = 'mxbai-embed-large'  # stories, narratives, claims and motifs
NOMIC = 'nomic-embed-text'  # a filing signal
QWEN3_EMBED = 'qwen3-embedding:8b'  # a filing signal (E11)
ARCTIC = 'snowflake-arctic-embed2'  # a filing signal (E11)
RERANKER = 'Qwen/Qwen3-Reranker-0.6B'  # the filing's reranker, taught weekly on the person's decisions
