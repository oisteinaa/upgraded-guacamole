#! /usr/bin/env python3
import requests
import yr_weather
import psycopg2

def get_weather():
    headers = {
       "User-Agent" : "ubecon.no oistein.aanensen@ubecon.no"
    }    
   
    LATITUDE = 68.01885  
    LONGITUDE = 14.18153  
   
    client = yr_weather.Locationforecast(headers)
    forecast = client.get_forecast(LATITUDE, LONGITUDE)
    
    def insert_weather_data(details):
        try:
            connection = psycopg2.connect(
                dbname="sensnetdb",
                user="sensnetdbu",
                password="obs",
                host="10.147.20.10",
                port="5432"
            )
            cursor = connection.cursor()

            # Define the location ID (lid) for this observation
            location_id = 1  # Replace with the appropriate location ID
            
            # Fetch all weather station locations from the database
            cursor.execute("SELECT lid, latitude, longitude FROM public.weather_stations")
            stations = cursor.fetchall()

            # Iterate over each station and insert weather data
            for station in stations:
                station_id, station_lat, station_lon = station
                station_forecast = client.get_forecast(station_lat, station_lon).now().details

                cursor.execute(
                    """
                    INSERT INTO public.weather_obs (lid, type, value)
                    VALUES (%s, %s, %s)
                    """,
                    (station_id, 1, station_forecast.air_temperature)
                )
                cursor.execute(
                    """
                    INSERT INTO public.weather_obs (lid, type, value)
                    VALUES (%s, %s, %s)
                    """,
                    (station_id, 2, station_forecast.wind_speed)
                )
                cursor.execute(
                    """
                    INSERT INTO public.weather_obs (lid, type, value)
                    VALUES (%s, %s, %s)
                    """,
                    (station_id, 3, station_forecast.wind_from_direction)
                )

            connection.commit()
        except Exception as e:
            print(f"Error inserting weather data: {e}")
        finally:
            if connection:
                cursor.close()
                connection.close()

    # Call the function to insert data
    insert_weather_data(forecast.now().details)

if __name__ == "__main__":
    get_weather()