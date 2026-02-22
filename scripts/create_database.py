from __future__ import annotations

import os

import pyodbc


def _get_bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def main() -> None:
    host = os.getenv("SQLSERVER_HOST", "127.0.0.1")
    port = int(os.getenv("SQLSERVER_PORT", "1433"))
    database = os.getenv("SQLSERVER_DATABASE", "Ember")
    user = os.getenv("SQLSERVER_USER", "sa")
    password = os.getenv("SQLSERVER_PASSWORD", "")
    trust_cert = _get_bool_env("SQLSERVER_TRUST_SERVER_CERT", True)

    trust = "yes" if trust_cert else "no"
    conn_str = (
        "DRIVER={ODBC Driver 18 for SQL Server};"
        f"SERVER={host},{port};"
        "DATABASE=master;"
        f"UID={user};PWD={password};"
        "Encrypt=yes;"
        f"TrustServerCertificate={trust};"
    )

    with pyodbc.connect(conn_str, autocommit=True) as conn:
        with conn.cursor() as cursor:
            cursor.execute(f"IF DB_ID('{database}') IS NULL CREATE DATABASE [{database}];")
            cursor.execute("SELECT name FROM sys.databases WHERE name = ?", database)
            row = cursor.fetchone()
            if row:
                print(f"Database ready: {row[0]}")
            else:
                raise RuntimeError(f"Failed to verify database {database}")


if __name__ == "__main__":
    main()
