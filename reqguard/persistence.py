"""A single acknowledged transaction; no retries after uncertain COMMIT."""
import os
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb


class PersistenceUnavailable(Exception):
    """Sanitized persistence failure exposed to the HTTP boundary."""


def save_analysis(original_input: str, result: dict) -> None:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise PersistenceUnavailable() from None
    payload = result["analysis"]
    parameters = (
        UUID(result["run_id"]), result["provider"], result["status"],
        original_input, Jsonb(payload) if payload is not None else None,
    )
    try:
        with psycopg.connect(database_url, connect_timeout=5) as connection:
            connection.execute(
                "INSERT INTO public.analyses "
                "(run_id, provider, status, original_input, analysis_payload) "
                "VALUES (%s, %s, %s, %s, %s)", parameters,
            )
        # Connection context has acknowledged COMMIT before returning.
    except psycopg.Error:
        raise PersistenceUnavailable() from None
