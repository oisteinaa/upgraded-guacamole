-- Add humidity, forecast provenance and spatially distributed forecast points.
BEGIN;
SELECT pg_advisory_xact_lock(20260916, 5);
DO $$
BEGIN
 IF NOT EXISTS (SELECT 1 FROM weather_obs_types WHERE abv='rhum') THEN
   INSERT INTO weather_obs_types(type,abv,name,unit)
   SELECT greatest(coalesce(max(type),0),3)+1,'rhum','Relative Humidity','%' FROM weather_obs_types;
 END IF;
 IF (SELECT count(*) FROM weather_obs_types WHERE abv='rhum' AND name='Relative Humidity' AND unit='%') <> 1 THEN
   RAISE EXCEPTION 'Conflicting humidity definition';
 END IF;
END $$;
ALTER TABLE weather_obs ADD COLUMN IF NOT EXISTS source_time timestamptz;
ALTER TABLE weather_obs ADD COLUMN IF NOT EXISTS forecast_updated_at timestamptz;
ALTER TABLE weather_obs ADD COLUMN IF NOT EXISTS collected_at timestamptz;
CREATE UNIQUE INDEX IF NOT EXISTS weather_obs_forecast_unique
 ON weather_obs(lid,type,source_time,forecast_updated_at) WHERE source_time IS NOT NULL;
ALTER TABLE weather_stations ADD COLUMN IF NOT EXISTS forecast_route varchar(16);
ALTER TABLE weather_stations ADD COLUMN IF NOT EXISTS forecast_mast varchar(32);
ALTER TABLE weather_stations ADD COLUMN IF NOT EXISTS selection_note text;
CREATE UNIQUE INDEX IF NOT EXISTS weather_stations_forecast_mast_unique
 ON weather_stations(forecast_route,forecast_mast) WHERE forecast_route IS NOT NULL;
-- Coordinates from audited EPSG:4326 mast workbook import; no invented altitude.
-- Fixed initial selection, about 5 km from previously selected points.
INSERT INTO weather_stations(lid,name,latitude,longitude,altitude,forecast_route,forecast_mast,selection_note)
SELECT coalesce(max(lid),0)+1,'R06 M44 forecast',68.14672559965149,13.490675914058292,NULL,'R06','M44',
 'Mast workbook coordinate; approximately 5 km spatial coverage; geographic weather contrast candidate, not validated microclimate.' FROM weather_stations
HAVING NOT EXISTS (SELECT 1 FROM weather_stations WHERE forecast_route='R06' AND forecast_mast='M44');
INSERT INTO weather_stations(lid,name,latitude,longitude,altitude,forecast_route,forecast_mast,selection_note)
SELECT coalesce(max(lid),0)+1,'R06 M67 forecast',68.12716079629317,13.379906259469017,NULL,'R06','M67',
 'Mast workbook coordinate; approximately 5 km spatial coverage; geographic weather contrast candidate, not validated microclimate.' FROM weather_stations
HAVING NOT EXISTS (SELECT 1 FROM weather_stations WHERE forecast_route='R06' AND forecast_mast='M67');
INSERT INTO weather_stations(lid,name,latitude,longitude,altitude,forecast_route,forecast_mast,selection_note)
SELECT coalesce(max(lid),0)+1,'R06 M95 forecast',68.10212958635988,13.27863758504069,NULL,'R06','M95',
 'Mast workbook coordinate; approximately 5 km spatial coverage; geographic weather contrast candidate, not validated microclimate.' FROM weather_stations
HAVING NOT EXISTS (SELECT 1 FROM weather_stations WHERE forecast_route='R06' AND forecast_mast='M95');
INSERT INTO weather_stations(lid,name,latitude,longitude,altitude,forecast_route,forecast_mast,selection_note)
SELECT coalesce(max(lid),0)+1,'R06 M137 forecast',68.06099739276354,13.2247083663401,NULL,'R06','M137',
 'Mast workbook coordinate; approximately 5 km spatial coverage; geographic weather contrast candidate, not validated microclimate.' FROM weather_stations
HAVING NOT EXISTS (SELECT 1 FROM weather_stations WHERE forecast_route='R06' AND forecast_mast='M137');
INSERT INTO weather_stations(lid,name,latitude,longitude,altitude,forecast_route,forecast_mast,selection_note)
SELECT coalesce(max(lid),0)+1,'R06 M177 forecast',68.0187035446406,13.18300642890548,NULL,'R06','M177',
 'Mast workbook coordinate; approximately 5 km spatial coverage; geographic weather contrast candidate, not validated microclimate.' FROM weather_stations
HAVING NOT EXISTS (SELECT 1 FROM weather_stations WHERE forecast_route='R06' AND forecast_mast='M177');
INSERT INTO weather_stations(lid,name,latitude,longitude,altitude,forecast_route,forecast_mast,selection_note)
SELECT coalesce(max(lid),0)+1,'R12 M1 forecast',68.22281842746787,14.510873435162205,NULL,'R12','M1',
 'Mast workbook coordinate; approximately 5 km spatial coverage; geographic weather contrast candidate, not validated microclimate.' FROM weather_stations
HAVING NOT EXISTS (SELECT 1 FROM weather_stations WHERE forecast_route='R12' AND forecast_mast='M1');
INSERT INTO weather_stations(lid,name,latitude,longitude,altitude,forecast_route,forecast_mast,selection_note)
SELECT coalesce(max(lid),0)+1,'R12 M38 forecast',68.21407503147203,14.390250726084309,NULL,'R12','M38',
 'Mast workbook coordinate; approximately 5 km spatial coverage; geographic weather contrast candidate, not validated microclimate.' FROM weather_stations
HAVING NOT EXISTS (SELECT 1 FROM weather_stations WHERE forecast_route='R12' AND forecast_mast='M38');
INSERT INTO weather_stations(lid,name,latitude,longitude,altitude,forecast_route,forecast_mast,selection_note)
SELECT coalesce(max(lid),0)+1,'R12 M72 forecast',68.23643644800812,14.284581691638133,NULL,'R12','M72',
 'Mast workbook coordinate; approximately 5 km spatial coverage; geographic weather contrast candidate, not validated microclimate.' FROM weather_stations
HAVING NOT EXISTS (SELECT 1 FROM weather_stations WHERE forecast_route='R12' AND forecast_mast='M72');
INSERT INTO weather_stations(lid,name,latitude,longitude,altitude,forecast_route,forecast_mast,selection_note)
SELECT coalesce(max(lid),0)+1,'R13 M1 forecast',68.32661915179847,14.651054778742767,NULL,'R13','M1',
 'Mast workbook coordinate; approximately 5 km spatial coverage; geographic weather contrast candidate, not validated microclimate.' FROM weather_stations
HAVING NOT EXISTS (SELECT 1 FROM weather_stations WHERE forecast_route='R13' AND forecast_mast='M1');
INSERT INTO weather_stations(lid,name,latitude,longitude,altitude,forecast_route,forecast_mast,selection_note)
SELECT coalesce(max(lid),0)+1,'R13 M39 forecast',68.2823476288053,14.618741801392403,NULL,'R13','M39',
 'Mast workbook coordinate; approximately 5 km spatial coverage; geographic weather contrast candidate, not validated microclimate.' FROM weather_stations
HAVING NOT EXISTS (SELECT 1 FROM weather_stations WHERE forecast_route='R13' AND forecast_mast='M39');
INSERT INTO weather_stations(lid,name,latitude,longitude,altitude,forecast_route,forecast_mast,selection_note)
SELECT coalesce(max(lid),0)+1,'R14 M1 forecast',68.22759369104426,14.120028514086378,NULL,'R14','M1',
 'Mast workbook coordinate; approximately 5 km spatial coverage; geographic weather contrast candidate, not validated microclimate.' FROM weather_stations
HAVING NOT EXISTS (SELECT 1 FROM weather_stations WHERE forecast_route='R14' AND forecast_mast='M1');
INSERT INTO weather_stations(lid,name,latitude,longitude,altitude,forecast_route,forecast_mast,selection_note)
SELECT coalesce(max(lid),0)+1,'R14 M43 forecast',68.24766695560271,14.010822372573587,NULL,'R14','M43',
 'Mast workbook coordinate; approximately 5 km spatial coverage; geographic weather contrast candidate, not validated microclimate.' FROM weather_stations
HAVING NOT EXISTS (SELECT 1 FROM weather_stations WHERE forecast_route='R14' AND forecast_mast='M43');
INSERT INTO weather_stations(lid,name,latitude,longitude,altitude,forecast_route,forecast_mast,selection_note)
SELECT coalesce(max(lid),0)+1,'R14 M83 forecast',68.24423141965678,13.88638031731162,NULL,'R14','M83',
 'Mast workbook coordinate; approximately 5 km spatial coverage; geographic weather contrast candidate, not validated microclimate.' FROM weather_stations
HAVING NOT EXISTS (SELECT 1 FROM weather_stations WHERE forecast_route='R14' AND forecast_mast='M83');
INSERT INTO weather_stations(lid,name,latitude,longitude,altitude,forecast_route,forecast_mast,selection_note)
SELECT coalesce(max(lid),0)+1,'R14 M123 forecast',68.22630567208199,13.773672954942626,NULL,'R14','M123',
 'Mast workbook coordinate; approximately 5 km spatial coverage; geographic weather contrast candidate, not validated microclimate.' FROM weather_stations
HAVING NOT EXISTS (SELECT 1 FROM weather_stations WHERE forecast_route='R14' AND forecast_mast='M123');
INSERT INTO weather_stations(lid,name,latitude,longitude,altitude,forecast_route,forecast_mast,selection_note)
SELECT coalesce(max(lid),0)+1,'R14 M160 forecast',68.19384371026098,13.685240602603436,NULL,'R14','M160',
 'Mast workbook coordinate; approximately 5 km spatial coverage; geographic weather contrast candidate, not validated microclimate.' FROM weather_stations
HAVING NOT EXISTS (SELECT 1 FROM weather_stations WHERE forecast_route='R14' AND forecast_mast='M160');
COMMIT;
