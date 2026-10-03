import os
import string
from functools import partial
from typing import Callable, Optional

import numpy as np
import pandas as pd
from wordcloud import WordCloud

from app.analysis import textnorm
from app.analysis.newsfilter import EMOTION_EMOJI, EMOTIONS, emotion_weights
from app.analysis.pipelines import Pipelines, STOPWORDS, prepare
from app.utils.logger import get_logger

logger = get_logger(__name__)

POS = ['NN', 'NNS', 'NNP', 'NNPS']

STOPWORDS = list(STOPWORDS)
# clean some default words
STOPWORDS.extend([
    'say', 'said', 'says', "n't", 'Mr', 'Ms', 'Mrs', 'time', 'year', 'week', 'month', "years",
    "life", "day", "thing", "something", "number", "system", "video", "months", "group",
    "home", "effort", "product", "part", "cup", "Jan", "Feb", "Mar", "Apr", "Jun", "Jul", "Aug", "Sep", "Sept",
    "Oct", "Nov", "Dec", "company", "companies", "business", "’", "'", '"', "go",
    "new", "January", "February", "March", "April", "May," "June", "July", "August", "September", "October", "November",
    "December", "time", "year", "week", "month", "years", "people", "life", "day", "thing", "something", "number",
    "Subscribe", "EST", "READ", "News", "New", "York", "Images", "Politics", "newsletter", "ago", "live", "updates",
    "exclusive",
    "producers", "hour",
    # filler that headlines lean on without saying anything about the news
    "big", "could", "would", "may", "might", "show", "help", "face", "faces", "make", "take", "get", "set", "way",
    "city", "center", "rule", "plan", "record", "man", "woman", "leader", "report", "east", "west", "north", "south",
    "top", "first", "last", "next", "back", "today", "tonight", "inside", "here", "what", "why", "how", "know",
    "state", "case", "end", "call", "look", "claim", "release", "history", "country", "world", "family", "issue"
])
# strip stray letters
STOPWORDS.extend(list(string.ascii_lowercase))
STOPWORDS.extend(list(string.ascii_uppercase))
STOPWORDS.extend(list(string.punctuation))

STOPWORDS = [word.lower() for word in STOPWORDS]

PIPELINE = [
    textnorm.hyphenated_words,
    textnorm.quotation_marks,
    textnorm.normalize_unicode,
    textnorm.whitespace,
    textnorm.accents,
    textnorm.brackets,
    textnorm.punctuation,
    Pipelines.tokenize,
    Pipelines.expand_contractions,
    partial(Pipelines.remove_stop, stopwords=STOPWORDS),
    Pipelines.lemmatize,
    Pipelines.pos_filter,
    lambda x: ' '.join(x)
]


# Fonts tried in order; the default is used if none are installed
FONTS = ['/usr/share/fonts/comic-neue/ComicNeue-Bold.ttf', '/usr/share/fonts/noto/NotoSans-Bold.ttf',
         '/usr/share/fonts/TTF/DejaVuSans-Bold.ttf']
MIN_OUTLETS = 2
# A phrase replaces its pieces when it accounts for most of their uses ("Christa Pike" over "Pike")
ABSORB_SHARE = 0.6
# Lean is log2 of how readily right-leaning outlets use a term over left-leaning ones (see term_outlets): 1 means
# twice as readily. Colors come in solid tiers rather than a blend, which turned every term muddy.
# Four kinds of word: used predominantly by one side (blue or red), balanced between them (a blue-to-red gradient
# on the page), or used mostly by center outlets (gray)
LEFT_COLOR, RIGHT_COLOR, CENTER_COLOR = '#1a5cff', '#e0102e', '#8a8f98'
BALANCED = 'balanced'  # drawn with a gradient in the browser; purple where a flat color is needed (the png)
BALANCED_FLAT = '#7a3fd0'
SIDE_LEAN = 0.4  # |log2 ratio| beyond which one side clearly dominates (about 1.3x as readily)
CENTER_MAJORITY = 0.5
# Mood is the average event score of the headlines using a term (-1 grim to 1 good news)
MOOD_EMOJI = [(-0.6, '💀'), (-0.3, '😬'), (0.3, ''), (0.6, '🙂'), (float('inf'), '🎉')]
MIN_OUTLETS_FOR_EMOJI = 5
MAX_EMOJI = 25
MIN_EMOTION_SHARE = 0.25  # of the averaged ranked-choice votes, so 25% is a strong pull
CLOUD_WORDS = 120


def term_outlets(df: pd.DataFrame, pipeline: list[Callable]) -> pd.DataFrame:
    """For every 1-3 word term: how many outlets used it, their average bias, and the average mood (event score)
    of the headlines using it, when `df` has a sentiment column."""
    rows = []
    has_mood, has_emotion = 'sentiment' in df, 'emotion_ranks' in df
    for row in df.itertuples():
        tokens = prepare(row.title, pipeline).split()
        terms = {' '.join(tokens[i:i + n]) for n in (1, 2, 3) for i in range(len(tokens) - n + 1)}
        mood = row.sentiment if has_mood else float('nan')
        ranks = row.emotion_ranks if has_emotion and isinstance(row.emotion_ranks, str) else None
        rated = getattr(row, 'rated', True)
        rows.extend((term, row.agency, row.bias, rated, mood, ranks, row.Index) for term in terms)
    terms = pd.DataFrame(rows, columns=['term', 'agency', 'bias', 'rated', 'mood', 'ranks', 'row'])
    # "State" and "state" are one term, shown in whichever spelling outlets use most
    terms['key'] = terms['term'].str.lower()
    spelling = terms.groupby('key')['term'].agg(lambda t: t.value_counts().index[0])
    one_vote = terms.drop_duplicates(['key', 'agency'])  # each outlet counts once toward reach and lean
    merged = one_vote.groupby('key').agg(outlets=('agency', 'nunique'), bias=('bias', 'mean'))
    merged['mood'] = terms.groupby('key')['mood'].mean()
    # Lean compares how readily each side's outlets use a term. Outlets that publish more use more distinct words and
    # would tilt every term their way, so each outlet's use counts as 1 / (the number of distinct terms it used) and
    # each side's score is the average over its outlets: every outlet weighs the same, whatever its volume.
    # lean = log2(right score / left score), smoothed; positive means the right uses it more.
    # Outlets without a lean rating count toward reach but not lean.
    vocab = one_vote.groupby('agency').size()
    rated_vote = one_vote[one_vote['rated'].astype(bool)]
    usage = rated_vote.assign(weight=1 / rated_vote['agency'].map(vocab))
    sides = rated_vote.drop_duplicates('agency').set_index('agency')['bias']
    left_outlets, right_outlets = (sides < 0).sum(), (sides > 0).sum()
    smooth = 0.5 / vocab.mean()
    left = usage[usage['bias'] < 0].groupby('key')['weight'].sum().reindex(merged.index, fill_value=0) / left_outlets
    right = usage[usage['bias'] > 0].groupby('key')['weight'].sum().reindex(merged.index, fill_value=0) / right_outlets
    merged['lean'] = np.log2((right + smooth) / (left + smooth))
    # How much of a term's use comes from center outlets (bias 0), on the same per-outlet footing
    center_outlets = (sides == 0).sum()
    center = usage[usage['bias'] == 0].groupby('key')['weight'].sum().reindex(merged.index, fill_value=0) / max(
        center_outlets, 1)
    merged['center_share'] = center / (left + right + center).replace(0, np.nan)
    merged['rows'] = terms.groupby('key')['row'].agg(list)  # which headlines used each term, for samples
    # Spice: how loaded the wording of the term's headlines is on average (0 plain to 2 heavily loaded)
    if 'loaded_score' in df:
        merged['spice'] = merged['rows'].apply(lambda rows: df.loc[rows, 'loaded_score'].mean())
    # The term's feeling, ranked-choice style: average each headline's split vote (emotion_weights) across the term's
    # headlines, then take the strongest emotion other than neutral and its share of the whole (neutral included, so
    # a mostly-plain term gets a low share)
    felt = terms.dropna(subset=['ranks'])
    if not felt.empty:
        weights = pd.DataFrame([emotion_weights(r) for r in felt['ranks']], index=felt.index).reindex(
            columns=EMOTIONS, fill_value=0).fillna(0)
        soft = weights.groupby(felt['key']).mean()
        feelings = soft.drop(columns='neutral')
        merged = merged.join(pd.DataFrame({'emotion': feelings.idxmax(axis=1), 'share': feelings.max(axis=1),
                                           'neutral_share': soft['neutral']}))
        merged['neutral_share'] = merged['neutral_share'].fillna(0)
    merged.index = spelling.reindex(merged.index).to_numpy()
    return merged.rename_axis('term')


def absorb_fragments(terms: pd.DataFrame) -> pd.DataFrame:
    """Keep phrases that carry most of their words' uses, and drop the fragments they cover."""
    counts = terms['outlets'].to_dict()
    keep = {t for t in counts if ' ' not in t}
    for phrase in sorted((t for t in counts if ' ' in t), key=counts.get, reverse=True):
        words = phrase.split()
        pieces = [' '.join(words[i:j]) for i in range(len(words)) for j in range(i + 1, len(words) + 1)
                  if (i, j) != (0, len(words))]
        if counts[phrase] < max(MIN_OUTLETS, ABSORB_SHARE * min(counts.get(p, 0) for p in pieces)):
            continue
        keep.add(phrase)
        keep -= {p for p in pieces if counts[phrase] >= ABSORB_SHARE * counts.get(p, 0)}
    return terms[terms.index.isin(keep) & (terms['outlets'] >= MIN_OUTLETS)]


def feeling_phrase(emotion: str, share: float, neutral_share: float) -> str:
    """Describe a term's leading feeling no more strongly than the numbers allow."""
    pct = f"{share:.0%} of the feeling in its headlines"
    if share >= 0.5:
        return f"Mostly {emotion}: {pct}"
    if share >= neutral_share:
        return f"Most often {emotion}: {pct}"
    return f"Leans {emotion}: {pct} (most read as neutral)"


def word_color(lean: float, center_share: float) -> tuple[str, str]:
    """(color, description) for a term: gray if center outlets carry most of it, else blue or red when one side
    clearly dominates, else balanced."""
    if not pd.isna(center_share) and center_share >= CENTER_MAJORITY:
        return CENTER_COLOR, 'used mostly by center outlets'
    if lean <= -SIDE_LEAN:
        return LEFT_COLOR, 'used predominantly by left-leaning outlets'
    if lean >= SIDE_LEAN:
        return RIGHT_COLOR, 'used predominantly by right-leaning outlets'
    return BALANCED, 'used by both sides'


def mood_emoji(mood: float, outlets: int) -> str:
    if pd.isna(mood) or outlets < MIN_OUTLETS_FOR_EMOJI:
        return ''
    return next(emoji for bound, emoji in MOOD_EMOJI if mood < bound)


def cloud_words(df: pd.DataFrame, pipeline: Optional[list[Callable]] = None) -> list[dict]:
    """The terms for the homepage's interactive cloud: size, color, emoji and a tooltip for each."""
    terms = absorb_fragments(term_outlets(df, pipeline or PIPELINE)).sort_values('outlets', ascending=False)
    terms = terms.head(CLOUD_WORDS)
    # Emoji only on the few words with the clearest feeling, or they crowd the cloud. With emotions scored, that's
    # the word's dominant emotion; otherwise it falls back to grim or good news.
    eligible = terms[terms['outlets'] >= MIN_OUTLETS_FOR_EMOJI]
    by_emotion = 'share' in terms and terms['share'].notna().any()
    if by_emotion:
        strongest = set(eligible[eligible['share'] >= MIN_EMOTION_SHARE]['share'].nlargest(MAX_EMOJI).index)
    else:
        strongest = set(eligible['mood'].abs().nlargest(MAX_EMOJI).index)
    words = []
    for term, row in terms.iterrows():
        color, side = word_color(row['lean'], row['center_share'])
        mood = '' if pd.isna(row['mood']) else f" · mood {row['mood']:+.2f}"
        has_feeling = by_emotion and isinstance(row.get('emotion'), str)
        phrase = feeling_phrase(row['emotion'], row['share'], row['neutral_share']) if has_feeling else ''
        feeling = f" · {phrase}" if phrase else ''
        if term not in strongest:
            emoji = ''
        elif by_emotion:
            emoji = EMOTION_EMOJI[row['emotion']]
        else:
            emoji = mood_emoji(row['mood'], row['outlets'])
        feeling_detail = {'emoji': EMOTION_EMOJI[row['emotion']], 'phrase': phrase} if has_feeling else None
        words.append({'text': term, 'outlets': int(row['outlets']), 'color': color, 'emoji': emoji,
                      'feeling': feeling_detail, 'side': side,
                      'lean': round(float(row['lean']), 3),
                      'spice': round(float(row['spice']), 3) if pd.notna(row.get('spice')) else 0.0,
                      'tip': f"{term}: {int(row['outlets'])} outlets · {side}{mood}{feeling}",
                      'samples': samples(df.loc[row['rows']])})
    return words


SAMPLES = 8


def samples(headlines: pd.DataFrame) -> list[dict]:
    """Up to SAMPLES headlines using a term, one per outlet, spread across the bias range and ordered left to
    right, so a click on a word shows how different outlets put it."""
    one_each = headlines.drop_duplicates('agency').sort_values('bias')
    if len(one_each) > SAMPLES:
        picks = np.linspace(0, len(one_each) - 1, SAMPLES).round().astype(int)
        one_each = one_each.iloc[sorted(set(picks))]
    return [{'title': r.title.strip(), 'agency': r.agency, 'bias': int(r.bias), 'url': getattr(r, 'url', '')}
            for r in one_each.itertuples()]


def generate_wordcloud(df: pd.DataFrame, path: str, pipeline: Optional[list[Callable]] = None):
    """Draw the terms the most outlets are using: size is how many outlets used a term, color is which side
    used it more (blue left, red right, gray both), relative to the outlets in `df` (title, agency, bias)."""
    if pipeline is None:
        pipeline = PIPELINE
    logger.debug("Generating wordcloud for %s headlines...", len(df))
    terms = absorb_fragments(term_outlets(df, pipeline))
    if terms.empty:
        logger.warning("No terms for a wordcloud at %s", path)
        return
    colors = {term: (lambda c: BALANCED_FLAT if c == BALANCED else c)(word_color(r['lean'], r['center_share'])[0])
              for term, r in terms.iterrows()}
    font = next((f for f in FONTS if os.path.exists(f)), None)
    wc = WordCloud(width=1600, height=800, background_color='white', max_words=70, font_path=font,
                   prefer_horizontal=1.0, relative_scaling=0.4, margin=24, max_font_size=210, random_state=42,
                   color_func=lambda word, **_: colors.get(word, 'rgb(95, 99, 104)'))
    wc.generate_from_frequencies(terms['outlets'].to_dict())
    wc.to_file(path)
    logger.debug("Saved wordcloud to %s", path)
