# Recording channels and fibre coordinates

The local DataCopy examples (`000009.hdf5`, `000019.hdf5`, `000029.hdf5`)
contain 25,236 columns. Header regions declare native-channel ranges 0–68036
and 69000–101900, both sampled every four channels. Database `masteliste`
positions in the second region instead begin at 69003 and end at 101899.
Matching by row number would silently shift measurements and is not used.

The header sensor distances establish native spacing 1.0213001907746815 m.
The first three database positions of each region match
`(channel - region_start) * native_spacing` within 0.05 m. In the second
region, channel 69003 has distance 3.063900572 m and channel 69007 has
7.149101335 m. This supports a common native channel axis with different
sampling phases; it does not establish historical event alignment.

Exact `(lid, channel)` matches retain their stored coordinates. Where the
region-origin check passes, an unmatched recording channel may use coordinates
linearly interpolated between adjacent stored channels. Both neighbours must be
in the same region and continuous mapping run, separated by four native channels,
and within `2 * 4 * native_spacing + 1` metres geographically. No extrapolation,
missing-range reconstruction, or signal resampling occurs. Each feature retains
its recording channel ID, interpolation status and both coordinate source IDs.
For example, channel 69004 lies one quarter of the way from 69003 to 69007.

For the prepared recordings this yields 17,010 exact and 8,224 interpolated
positions. Channels 69000 and 101900 remain outside the stored bounds.
The local audit is `.local/channel-mapping-audit.json`; API and unit tests cover
these counts, provenance, rejected gaps and absent origin evidence. The database
mapping remains unchanged. Mast-span straight lines are never substituted for
fibre geometry, and event-limit group names are not used as geographic evidence.

Discovery candidates in the event queue now use their validated source channel
blocks for geographic display independently of clock verification. With a single
configured DAS line and no recording lid, this requires the header ROI origin
checks above; multiple configured lines require an explicit recording lid.
The map marker represents the middle mapped channel of the sampled block, not
a pinpointed incident. Exact or interpolated coordinates and interpolation
neighbours remain visible. Span matches use mapped channels within same-line
mast endpoint bounds; inferred span status is unchanged. Nearby masts are ranked
by straight-line geographic distance to the marker and are not asserted to be
its span endpoints. If no inventory span covers the channels, the GUI explicitly
says so while still showing fibre coordinates and nearest masts. No time,
alignment, class or historical mapping verification flags are changed.

Server candidate #115850 maps header channel 69832 between stored channels
69831 and 69835, near 68.14999 N, 13.62147 E. No imported span covers this block;
nearest inventory masts are R14 M197 (~969 m) and R06 M1 (~997 m). Do not invent
a connection between those routes. All five server candidates now have map
markers; route filters include candidates whose blocks intersect inventory spans.
