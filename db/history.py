import os
import psycopg2
from contextlib import contextmanager
from typing import List, Tuple, Optional
from utils.logger import logger, GREEN, YELLOW, RST

DB_DSN = os.getenv("PG_DSN", "dbname=assistant user=assistant password=assistant host=localhost")


DB_DSN = os.getenv("PG_DSN", "dbname=assistant user=assistant password=assistant host=localhost")

