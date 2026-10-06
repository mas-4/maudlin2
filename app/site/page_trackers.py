"""The nav's menus: every page past the front page, grouped the way a story travels (front pages, then TV and radio,
then people retelling it online), so the nav stays short. Two links sit beside them: every story, and the sagas."""

# On the front pages: the outlets, their headlines and what the trackers measure in them
FRONT_PAGES = [
    {'href': 'headlines.html', 'emoji': '📰', 'name': 'Every headline',
     'about': "Every outlet's front-page headlines right now, searchable."},
    {'href': 'agencies.html', 'emoji': '🏢', 'name': 'Outlets',
     'about': 'Every outlet we read: its lean, its mood, what it leads with.'},
    {'href': 'edits.html', 'emoji': '✏️', 'name': 'Headline changes',
     'about': 'Headlines outlets rewrote after publishing, and the wordings they A/B test.'},
    {'href': 'emotions.html', 'emoji': '😱', 'name': 'Emotions',
     'about': "The feelings each outlet's headlines are likely to stir."},
    {'href': 'names.html', 'emoji': '🗣️', 'name': "Who's in the news",
     'about': 'The people, places and groups our stories name, day by day, and who covered them.'},
    {'href': 'court.html', 'emoji': '⚖️', 'name': 'The Supreme Court',
     'about': "This term's cases: who's covering which, from which side, at which stage."},
    {'href': 'archive.html', 'emoji': '🗄️', 'name': 'Archive',
     'about': "Each day's front page as it stood at day's end."},
]

# On the air: broadcast, and the shows and newsletters that talk the news over
ON_AIR = [
    {'href': 'tv.html', 'emoji': '📺', 'name': 'On TV',
     'about': "What CNN, Fox News, MSNOW and BBC News kept on screen, and for how long, beside the front pages."},
    {'href': 'radio.html', 'emoji': '📻', 'name': 'On the radio',
     'about': "NPR's and ABC's hourly newscasts, story by story, beside what the front pages led with."},
    {'href': 'beyond.html', 'emoji': '🎙️', 'name': 'Shows and newsletters',
     'about': "What the podcasts, newsletters and investigators are talking about, and every source we follow."},
]

# Online: what people retell and what fact-checkers examine, read for their shapes
FOLKLORE = [
    {'href': 'folklore.html', 'emoji': '🧶', 'name': 'Folklore',
     'about': 'Rumors, legends and sayings people retell in their own words, from Bluesky and Mastodon.'},
    {'href': 'rumors.html', 'emoji': '🔎', 'name': 'Rumors',
     'about': "Rumors the fact-checkers examined, read for their shape: what drives them, what plot they claim."},
    {'href': 'motifs.html', 'emoji': '🧩', 'name': 'Motif index',
     'about': "Our own index of the recurring shapes of today's political rumors and narratives."},
]

ABOUT = [
    {'href': 'glossary.html', 'emoji': '🛠️', 'name': 'How it works',
     'about': 'What every measure means and how we make it.'},
    {'href': 'methods.html', 'emoji': '📓', 'name': 'Methods log',
     'about': 'Every change to how we measure, with the mistakes we caught, day by day.'},
    {'href': 'feed.xml', 'emoji': '📡', 'name': 'RSS feed', 'about': 'The current stories, for your feed reader.'},
]

# (label, its pages, a note at the top of the menu)
MENUS = [
    ('📰 front pages', FRONT_PAGES, ''),
    ('📡 on air', ON_AIR, ''),
    ('🧶 online', FOLKLORE, 'Work in progress: rumors and narratives read for their shapes, not their truth.'),
    ('🛠️ how it works', ABOUT, ''),
]
