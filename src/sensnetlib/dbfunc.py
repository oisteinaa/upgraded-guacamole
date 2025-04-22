import psycopg2
import pandas as pd

# import sys

def get_db_conn():
    conn = psycopg2.connect(
        dbname="sensnetdb",
        user="sensnetdbu",
        password="obs",
        host="10.147.20.10",
        port="5432"
    )
    
    return conn

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
    df = pd.read_sql_query(query, conn)
    conn.close()
    
    return df

def get_weather():
    query = """
    SELECT * FROM weather_obs
    WHERE age(now(), time) < interval '24 hour'
    ORDER BY time
    """
    
    conn = get_db_conn()
    df = pd.read_sql_query(query, conn)
    conn.close()
    
    return df

def get_event_limits():
    query = """
    SELECT "time", name, gid, data_type, "limit", absolute
	FROM event_limits ORDER BY gid;
    """
    
    conn = get_db_conn()
    df = pd.read_sql_query(query, conn)
    conn.close()
    
    return df

def get_event_data():
    query = """
    SELECT time, type, value, comment
    FROM events ORDER BY time DESC limit 20;
    """
    
    conn = get_db_conn()
    df = pd.read_sql_query(query, conn)
    conn.close()
    
    return df

def insert_event(typeid, value, comment):
    query = """
    INSERT INTO events (type, value, comment)
    VALUES (%s, %s, %s);
    """
    
    conn = get_db_conn()
    cursor = conn.cursor()
    try:
        cursor.execute(query, (typeid, value, comment))
        conn.commit()
    except Exception as e:
        conn.rollback()  # Rollback in case of error
        print(f"Error inserting event: {e}")
    finally:
        cursor.close()
        conn.close()