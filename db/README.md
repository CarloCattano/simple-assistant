# Conversation History Database

This folder contains the schema and access code for storing Telegram bot conversation history in PostgreSQL using psycopg2.


## Docker Setup

To run PostgreSQL with the schema using Docker:

```sh
docker build -t assistant-pg .
docker run -d --name assistant-pg -e POSTGRES_PASSWORD=assistant -p 5432:5432 assistant-pg
```

This will start a PostgreSQL server on port 5432 with user `assistant`, password `assistant`, and database `assistant`.

To connect from your app or psql:

```sh
psql -h localhost -U assistant -d assistant
# or set PG_DSN:
export PG_DSN="dbname=assistant user=assistant password=assistant host=localhost"
```

## Manual Setup

1. Create a PostgreSQL database and user, e.g.:
   ```sh
   createuser assistant --pwprompt
   createdb assistant -O assistant
   ```
2. Run the schema:
   ```sh
   psql -U assistant -d assistant -f db/schema.sql
   ```
3. Set the environment variable `PG_DSN` to your connection string, e.g.:
   ```sh
   export PG_DSN="dbname=assistant user=assistant password=yourpassword host=localhost"
   ```

## Usage

- Use `save_message(chat_id, user_id, role, content)` to store a message.
- Use `get_history(chat_id, limit=20)` to retrieve recent messages for a chat.

See `history.py` for details.
