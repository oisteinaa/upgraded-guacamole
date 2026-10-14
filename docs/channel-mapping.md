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

## New acquisition spacing (2026-10-14)

Incoming files now contain 12,612 channels with `roiDec=[8,8]`, ROI bounds
0–68008 and 69000–101872. Inspected header values are native `dx` =
1.0213001907746815 m, sensor spacing = 8.170401526 m and gauge length =
16.340803052 m. Older files use spacing 4.085200763 m and gauge length
8.170401526 m. Gauge length and sample spacing are separate quantities.

The stored geometry still uses four native channels between adjacent positions;
it must not be decimated or have its channel IDs multiplied by two. Origin checks
accept acquisition steps that are positive multiples of that geometry step.
Coordinate interpolation still requires adjacent **four-channel geometry**
neighbours, regardless of the recording step. Map display buckets use the minimum
channel step from the complete recording and retain separate geometry runs, so
8-channel files reduce correctly without joining excluded loops. Mixed steps are
handled conservatively in display reduction. Demo caches are versioned to discard
previous map results. Signal metrics continue using explicit file channel IDs and
`dataScale`, with no extra factor of two or spatial resampling.

Both spacings can coexist in the archive. Stitching stops at changes in channel
IDs, ROI configuration or gauge length. The old calm reference cannot be applied
to the new acquisition configuration: raw metrics remain available and calm
scores require a separately trained and validated reference. The legacy
`sensnetlib.get_mastliste()` helper is not used by the observatory capture/map
pipeline and its row-based selection is not suitable for these files.

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

## Live chart direction (2026-10-14)

The two Live monitor activity charts display acquisition regions in south-to-north
route order. Each region is oriented using the latitude of its first and last
mapped native channels, then regions are ordered by their southern endpoint.
Within a region, native cable order is retained through bends; individual points
are not sorted by latitude. For the current recording this puts channels
101872 down to 69000 first, followed by 0 up to 68008. Older 4 m recordings use
their own ROI bounds. This display order is inferred from mapped endpoints, not
a new verified physical connection between regions.

The x-axis ticks show original channel IDs in this order. A blank spacer separates
regions; it has no distance meaning. The axis is not cumulative geographic or
cable distance. Existing profile gaps and missing calm scores remain breaks;
heatmap bins are moved intact, retaining values, peak channel identities and
original widths. Hover, click selection and highlights retain native IDs in raw
and calm modes. When mapped acquisition regions cannot establish direction, the
charts retain channel order with an explicit geographic-order-unavailable label.
