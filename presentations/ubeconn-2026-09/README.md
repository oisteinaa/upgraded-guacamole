# Ubeconn AS — executive project review

18 slides in English, 16:9, prepared from the repository and recorded project
evidence on 16 September 2026. The main presentation is 16 slides, followed by
two appendices for sources and brand identity.

- `Ubeconn_Executive_Review_2026-09.pptx`: editable PowerPoint; source context,
  caveats and presenter guidance are in each slide's speaker notes.
- `Ubeconn_Executive_Review_2026-09.pdf`: matching presentation with embedded
  fonts for consistent viewing and sharing.
- `assets/ubeconn-white.svg`: white wordmark as vector outlines.
- `assets/ubeconn-white.png`: white wordmark on a transparent background.
- `fonts/`: IBM Plex fonts and their SIL Open Font License. Install these fonts
  before opening the editable deck for the intended typography. PowerPoint may
  substitute fonts if they are unavailable.
- `slide-overview.png`: contact sheet of all slides.
- `speaker-notes.md`: standalone presenter notes and evidence references.
- `brand-palette.json`: proposed Ubeconn colour tokens.

The presentation follows house-report's dark backgrounds, restrained cards,
rules, and IBM Plex type hierarchy, with ube purple and lavender replacing the
Nord accents. The application screenshot retains its actual existing appearance.
Roadmap phases and acceptance measures are explicitly proposals; no budget,
schedule, field accuracy, customer commitment or financial benefit is invented.

The source application, database and existing project changes were left untouched.
Recorded application tests are described as historical evidence, not as tests
rerun for this presentation. Database counts are the documented snapshot.

## Rebuild and verification

From the repository root, run `python3 presentations/ubeconn-2026-09/build_presentation.py`
in a Python 3 environment with python-pptx, Pillow, fonttools, brotli and reportlab.
The generator uses the existing frontend's locally bundled IBM Plex font sources,
mast CSVs, pilot JSON files and original local application screenshot.

Slide text, diagrams, bars and route lines are editable native PowerPoint objects.
The application screenshot is embedded. PDF and preview images are rendered from
the same layout definition. The generator checks text width, slide bounds and
speaker notes, and reopens the PowerPoint package. The previews were visually
reviewed; they are shared-layout renders, not renders from Microsoft PowerPoint
or LibreOffice. The PDF is the font-stable reference.
