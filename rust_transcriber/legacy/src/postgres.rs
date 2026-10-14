use postgres::{Client, NoTls, Error};

// let conn_str = "host=localhost user=postgres password=secret dbname=mydb";
pub fn connect_and_query(conn_str: &str, query: &str) -> Result<Vec<postgres::Row>, Error> {
    let mut client = Client::connect(conn_str, NoTls)?;
    let rows = client.query(query, &[])?;
    Ok(rows)
}
