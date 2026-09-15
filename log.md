## What the pilot found

  We can process the archive efficiently and distinguish signal patterns, but we have not identified confirmed cable events.

  - Coverage: 15 minutes of recordings, sampled across 16 channel blocks, produced 240 analyzed windows.
  - Grouping: The algorithm divided these into six clusters. Six was the configured maximum—not evidence of six physical event types.
  - Strong location differences: Three channel blocks stayed in the same high-amplitude, higher-frequency cluster throughout all 15
    minutes. This suggests the model is partly learning persistent differences between cable sections.

  - Interesting review targets:
      - Channels 6656–6780: changing patterns with prominent peaks around 3.65 and 5.1 Hz in several windows.
      - Channels 0–124: several highly ranked unusual windows, including peaks near 100 Hz. Their amplitudes were relatively low, showing
        that “unusual” does not necessarily mean strong vibration.

  - Practical result: Processing used about 160 MiB of memory. Rerunning reused all extracted features and reproduced identical results.

  These findings come from the review results (results/das-discovery-pilot-20260916/review.csv). No ice, galloping or vegetation strike is
  confirmed, and weather was not joined because timestamp alignment remains unverified.

  ## Basic next steps

  1. Inspect the interesting windows visually. Plot signal traces and frequency spectra for the two channel ranges above, alongside
     typical examples.

  2. Verify time and channel mapping. Confirm acquisition timestamps and identify which channels correspond to monitored cable sections.
  3. Expand to days or weeks with contrasting weather. Include calm, windy, cold and warmer periods, then match the appropriate weather
     station.

  4. Learn a baseline for each section. Detect changes relative to that section’s usual behavior, so permanently different sections do not
     dominate anomaly rankings.

  5. Add mast positions and verified labels. Analyze individual spans, compare measured frequency patterns, and label confirmed incidents
     before training an event classifier.

  My recommended next step is visual inspection of channels 6656–6780 and 0–124, followed by a longer weather-linked run.