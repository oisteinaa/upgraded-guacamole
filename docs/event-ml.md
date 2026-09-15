# Four-class DAS classifier

Classes: **Normal Operations**, **Ice Loading**, **Wind Galloping**,
**External Interference**. This is an offline supervised baseline; no trained
model or measured field accuracy is supplied. Existing live RMS alarms continue
to operate. Validate this pipeline before connecting predictions to live alarms.

## Install and label

Use Python 3.10+ and `python3 -m pip install -r requirements-ml.txt` in a virtual
environment. Create a CSV manifest with this header:

```csv
path,start_sample,stop_sample,channel_start,channel_stop,sample_rate_hz,label,group,temperature,wind_speed,wind_direction,humidity
recordings/normal.hdf5,0,1000,0,20,100,Normal Operations,session-01,5,3,270,80
```

Paths are relative to the manifest. Bounds are zero-based, stop-exclusive.
The HDF5 `data` dataset must have shape `(samples, channels)`. Use verified
sample rate and channel order. Features use stored signal values: they do not
apply the live capture script's scaling, reversal, unwrapping or integration.
Train and predict with the same representation, acquisition settings, window
duration and comparable channel spans. Do not apply this model directly to the
live processed arrays without retraining on that representation.

Assign labels using independent evidence such as inspections, cameras or
confirmed incident logs. Include quiet and windy normal operation. Use one
group per independent session or incident, including related files and spans;
all windows from a file must share a group. At least three independent groups
per class are required; substantially more are needed for useful evaluation.
Avoid mixed-class windows or annotate smaller windows. A single-label model
cannot describe simultaneous ice and galloping.

Weather fields are optional: temperature in Celsius, wind speed in m/s,
direction in degrees, humidity in percent. Blank values get explicit missing
indicators. Match weather to the recording time and location, using only data
available at that time. Humidity is accepted here; the production weather
database collector is not changed.

## Train and inspect validation

```bash
python3 -m src.Capture.event_ml train labels.csv event-model.joblib
```

Writes a model and `event-model.joblib.metrics.json`: per-class precision,
recall and F1, a confusion matrix (rows=true, columns=predicted in class-list
order), and group memberships for each fold. Three-fold grouped validation
prevents windows of the same session appearing on both sides of a split.
The final model is fitted on all labels. Keep additional sites, seasons and
incidents untouched for a final evaluation; do not tune repeatedly on these.

## Predict quantified windows

Load only model artifacts you trust; joblib loading can execute Python code.
Use the same dependency versions for training and prediction.

```bash
python3 -m src.Capture.event_ml predict event-model.joblib recording.hdf5 \
  --sample-rate 100 --window-samples 1000 --channel-start 0 --channel-stop 20 \
  --weather '{"temperature":-2,"wind_speed":12,"wind_direction":270,"humidity":95}' \
  > predictions.jsonl
```

Each JSON line contains a predicted class, four uncalibrated probability
scores, a review flag below the default 0.7 threshold, relative start/stop
times, channel bounds, RMS, AC RMS, AC peak and dominant frequency. The threshold
is a starting setting, not a validated operating point. Weather supplied on the
command line applies to the whole file, so split files when weather changes.
Windows do not overlap; a final remainder below eight samples is omitted.

These are window measurements, not merged incident durations or severity.
Channel bounds describe the analyzed region, not a confirmed affected extent.
Amplitude is in stored input units. Estimating ice mass, loading force or cable
displacement requires sensor calibration, cable properties and corresponding
ground-truth measurements. Ice may not be distinguishable from these features
alone; field validation must establish that. Low scores flag review but cannot
reliably identify every unknown event type.

Next deployment steps are validating field performance and thresholds,
aligning live preprocessing/weather, and adding persistent incident tracking
and dashboard storage for the new outputs.

Run checks with `python3 -m unittest discover -s tests`.
