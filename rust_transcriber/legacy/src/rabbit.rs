
pub async fn send_to_rabbitmq(msg_json: &serde_json::Value) {
    // eprintln!("{:?}", msg_json);
    let connection = match lapin::Connection::connect("amqp://localhost:5672/%2f", lapin::ConnectionProperties::default()).await {
        Ok(conn) => conn,
        Err(_) => return,
    }; let channel = connection.create_channel().await.unwrap();
    let exchange_name = "progress";

    channel.exchange_declare(
        exchange_name,
        lapin::ExchangeKind::Fanout,
        lapin::options::ExchangeDeclareOptions::default(),
        lapin::types::FieldTable::default(),
    ).await.unwrap();

    channel.basic_publish(
        exchange_name,
        "",
        lapin::options::BasicPublishOptions::default(),
        msg_json.to_string().as_bytes(),
        lapin::BasicProperties::default(),
    ).await.unwrap();

}