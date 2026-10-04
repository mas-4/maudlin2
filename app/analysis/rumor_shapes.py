"""Open, short label sets for the shape of a rumor (#145), used beside Thompson's Motif-Index chapters, which fit
folktales far better than modern political rumors (Oct 4: a strict reading matched a specific motif for 5 of 151
claims, and the local model's motif picks were mostly wrong). The labels are concepts from the research literature,
not anyone's text:

- Rumor class, by the emotion that drives it: Robert Knapp, "A Psychology of Rumor" (Public Opinion Quarterly,
  1944), named pipe-dream, bogie and wedge-driving rumors; Nicholas DiFonzo and Prashant Bordia, "Rumor Psychology"
  (2007), call them wish, dread and wedge.
- Conspiracy scope: Michael Barkun, "A Culture of Conspiracy" (2003): event, systemic and superconspiracy.
- Subject family: broad families, our own list, after the way urban-legend collections (Jan Harold Brunvand's
  among them) sort legends into chapters.

Like every label on the folklore pages, these describe the story's shape as its tellers tell it, never whether it's
true."""

RUMOR_CLASSES = {
    'wish': "what its tellers hope is true: a good deed, a rescue, a win, a cure",
    'dread': "what its tellers fear: a danger, a disaster, a threat, a cover-up of harm",
    'wedge': "turns one group against another: blames, vilifies or scapegoats a group",
    'other': "none of these",
}
CONSPIRACY_SCOPES = {
    'event': "a secret plot behind one event (a staged attack, a hidden cause of one disaster)",
    'systemic': "a secret group controlling an institution or system (elections, the press, a government agency)",
    'superconspiracy': "plots nested inside plots, all run by one hidden, all-powerful force",
    'not a conspiracy': "no secret plot is claimed",
}
FAMILIES = ['crime and danger', 'contamination, health and medicine', 'business and products',
            'government and politics', 'celebrities', 'technology and media', 'animals and nature',
            'sex and scandal', 'accidents and disasters', 'religion and the supernatural', 'schools and young people',
            'travel and places', 'none']
EMOJI = {'wish': '🌈', 'dread': '😨', 'wedge': '🪓', 'event': '🕵️', 'systemic': '🏛️', 'superconspiracy': '🐙'}


def prompt_fields() -> str:
    """The lines a labeler's prompt adds for these three label sets."""
    classes = '; '.join(f'"{k}" ({v})' for k, v in RUMOR_CLASSES.items())
    scopes = '; '.join(f'"{k}" ({v})' for k, v in CONSPIRACY_SCOPES.items())
    return (f"rumor_class: what drives it, as its tellers tell it, one of {classes}\n"
            f"secret_plot: does the claim say that a hidden group SECRETLY planned something or secretly controls "
            f"something? A claim about what a government, court, campaign or company openly did or said, or a claim "
            f"that is just wrong, is false. Most claims are false\n"
            f"conspiracy: if secret_plot is true, its scope, one of {scopes}; otherwise \"not a conspiracy\"\n"
            f"family: its subject family, one of {'; '.join(FAMILIES)}")


SCHEMA_FIELDS = {
    'rumor_class': {"type": "string", "enum": list(RUMOR_CLASSES)},
    'secret_plot': {"type": "boolean"},
    'conspiracy': {"type": "string", "enum": list(CONSPIRACY_SCOPES)},
    'family': {"type": "string", "enum": FAMILIES},
}


def settle(label: dict) -> dict:
    """A scope only when the model says a secret plot is claimed (asked first: on its own, a small model calls any
    claim about a government a conspiracy)."""
    if label and not label.get('secret_plot', True):
        label['conspiracy'] = 'not a conspiracy'
    return label
