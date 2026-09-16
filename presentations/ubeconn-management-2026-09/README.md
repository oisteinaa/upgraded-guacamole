# Ubeconn AS — management update

New ten-slide management presentation, prepared on 16 September 2026.
The previous technical executive presentation is preserved separately.

Revised to focus on real-event classification. Existing event records are
randomly generated demonstration data, excluded from training and performance
claims. Their future deletion is outside this presentation update; no database
records were changed. A dedicated UI slide includes the screenshot, explicitly labeled as a demonstration; visible example entries are not operational evidence.

- `Ubeconn_Management_Update_2026-09.pptx`: editable 16:9 PowerPoint, with
  presenter notes and evidence references on every slide.
- `Ubeconn_Management_Update_2026-09.pdf`: matching PDF with embedded fonts.
- `slide-overview.png`: all ten slides at a glance.
- `assets/ubeconn-supplied-logo.png`: the supplied logo, unchanged.
- `fonts/`: IBM Plex fonts and their Open Font License. Install the fonts for
  the intended editable PowerPoint appearance; use the PDF for consistent viewing
  without installing fonts.
- `speaker-notes.md`: the complete presenter notes.

The design uses pale lavender backgrounds, white panels, dark plum text and purple
accents. Text, tables, bars and diagrams are native editable PowerPoint objects.
The supplied logo is embedded unchanged. The operator workflow is shown as an editable diagram, followed by a dedicated screenshot slide with explanations.

## Content

1. Moving forward with event classification
2. Platform capabilities for classification
3. The unified investigation workspace
4. New UI screenshot: network map, recording inspection and review
5. Deployed weather expansion: 2 to 17 locations, including humidity
6. Random Forest supervised machine learning: 300 decision trees
7. K-means and Isolation Forest discovery; expert labeling; training and testing
8. The four target categories
9. Building a dedicated real-world training dataset
10. Short sequence of next steps to classify events

The updated weather documentation supersedes older statements that humidity is
missing. The software for supervised training is implemented, but no trained,
field-validated classifier or measured field accuracy is claimed. The discovery
pilot is separate from supervised classification. Roadmap steps remain proposals.
Detailed implementation and evidence limitations are kept in presenter notes.

## Build and checks

Run `build_presentation.py` from a Python 3 environment with python-pptx, Pillow,
fonttools, brotli and reportlab. The generator reads locally bundled frontend
fonts and existing project artifacts; it does not modify the application or DB.

PowerPoint package structure, XML, text widths, slide bounds and notes were
checked. Preview images were visually reviewed. PDF and preview images are drawn
from the same layout definition; these are not Microsoft Office engine renders.
The included PDF is the reference for consistent typography and appearance.
