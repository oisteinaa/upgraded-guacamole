import psycopg2
import pandas as pd
from sqlalchemy import create_engine, text

# import sys

def get_db_conn():
    engine = create_engine(
        "postgresql+psycopg2://sensnetdbu:obs@10.147.20.10:5432/sensnetdb"
    )
    return engine.connect()

def get_mastliste():
    # Execute the query and fetch data
    query = """
    WITH numbered_rows AS 
        (SELECT *, row_number() OVER (ORDER BY id) AS rn FROM masteliste)
    SELECT *
    FROM numbered_rows
    WHERE (rn - 1) % 4 = 0 
    AND channel < 33421
    ORDER BY channel DESC 
    LIMIT 8356;
    """
    conn = get_db_conn()
    df = pd.read_sql_query(text(query), conn)
    conn.close()
    
    return df

def get_weather():
    query = """
    SELECT * FROM weather_obs
    WHERE age(now(), time) < interval '24 hour'
    ORDER BY time
    """
    
    conn = get_db_conn()
    df = pd.read_sql_query(text(query), conn)
    conn.close()
    
    return df

def get_event_limits():
    query = """
    SELECT "time", name, gid, data_type, "limit", absolute
	FROM event_limits ORDER BY gid;
    """
    
    conn = get_db_conn()
    df = pd.read_sql_query(text(query), conn)
    conn.close()
    
    return df

def get_event_data():
    query = """
    SELECT time, type, value, comment
    FROM events ORDER BY time DESC limit 20;
    """
    
    conn = get_db_conn()
    df = pd.read_sql_query(text(query), conn)
    conn.close()
    
    return df

def get_event_data_extended(limit=200):
    query = text("""
    SELECT time, type, value, comment
    FROM events ORDER BY time DESC LIMIT :limit;
    """)

    conn = get_db_conn()
    df = pd.read_sql_query(query, conn, params={"limit": limit})
    conn.close()

    return df

def get_event_locations(limit=200):
    """
    Approximate map location for recent events. event_detector.insert_event
    stores the tripped segment's event_limits.name as events.comment, so we
    join events -> event_limits (on name) -> masteliste (on gid, averaged)
    to get a lat/long per event.
    """
    events_df = get_event_data_extended(limit=limit)
    if events_df.empty:
        events_df['latitude'] = pd.Series(dtype=float)
        events_df['longitude'] = pd.Series(dtype=float)
        return events_df

    limits_df = get_event_limits()[['name', 'gid']].drop_duplicates()
    mast_locations = get_mastliste().groupby('gid')[['latitude', 'longitude']].mean().reset_index()

    merged = events_df.merge(limits_df, left_on='comment', right_on='name', how='left')
    merged = merged.merge(mast_locations, on='gid', how='left')

    return merged

def insert_event(typeid, value, comment):
    query = """
    INSERT INTO events (type, value, comment)
    VALUES (%s, %s, %s);
    """
    
    conn = get_db_conn()
    cursor = conn.cursor()
    try:
        cursor.execute(text(query), (typeid, value, comment))
        conn.commit()
    except Exception as e:
        conn.rollback()  # Rollback in case of error
        print(f"Error inserting event: {e}")
    finally:
        cursor.close()
        conn.close()