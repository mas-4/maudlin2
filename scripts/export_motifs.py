"""Export the motif index (app/analysis/motif_export.py): a readable catalog, a spreadsheet, JSON or SKOS.

    .venv/bin/python scripts/export_motifs.py md                 # verified motifs, readable, to the current folder
    .venv/bin/python scripts/export_motifs.py ttl --all          # every live motif, as SKOS
    .venv/bin/python scripts/export_motifs.py csv -o motifs.csv  # to a file of your choosing ('-' for the screen)

The motif workbench's 📦 export menu downloads the same files.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.analysis import motif_export  # noqa: E402

if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('format', choices=sorted(motif_export.FORMATS))
    ap.add_argument('--all', action='store_true', help='every live motif, not only the verified ones')
    ap.add_argument('-o', '--out', help="file to write ('-' for the screen); default: its own name, here")
    args = ap.parse_args()
    text, _, name = motif_export.export(args.format, 'all' if args.all else 'verified')
    if args.out == '-':
        sys.stdout.write(text)
    else:
        with open(args.out or name, 'w') as f:
            f.write(text)
        print(f'wrote {args.out or name}', file=sys.stderr)
