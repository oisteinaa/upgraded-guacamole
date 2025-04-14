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

            # Insert each weather detail into the database
            cursor.execute(
                """
                INSERT INTO public.weather_obs (lid, type, value)
                VALUES (%s, %s, %s)
                """,
                (location_id, 1, details.air_temperature)
            )
            cursor.execute(
                """
                INSERT INTO public.weather_obs (lid, type, value)
                VALUES (%s, %s, %s)
                """,
                (location_id, 2, details.wind_speed)
            )
            cursor.execute(
                """
                INSERT INTO public.weather_obs (lid, type, value)
                VALUES (%s, %s, %s)
                """,
                (location_id, 3, details.wind_from_direction)
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