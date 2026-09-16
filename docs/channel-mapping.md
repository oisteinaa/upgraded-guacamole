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
