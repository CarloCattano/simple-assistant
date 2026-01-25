# Use official PostgreSQL image
FROM postgres:16

# Set environment variables for default user and database
ENV POSTGRES_USER=assistant
ENV POSTGRES_PASSWORD=assistant
ENV POSTGRES_DB=assistant

# Copy schema to docker-entrypoint-initdb.d so it runs on container start
COPY schema.sql /docker-entrypoint-initdb.d/

# Expose default PostgreSQL port
EXPOSE 5432
