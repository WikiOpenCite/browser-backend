# SPDX-FileCopyrightText: 2026 The University of St Andrews
# SPDX-License-Identifier: GPL-3.0-or-later

from dataclasses import dataclass
from enum import Enum
from typing import Any


class DatabaseType(Enum):
    MARIADB = "mariadb"


@dataclass
class Database:
    """Representation of a database"""

    db_type: DatabaseType


@dataclass
class MariaDBDatabase(Database):
    """Representation of a MariaDB database"""

    host: str
    port: int
    user: str
    password: str
    database: str
    min_pool_size: int = 5
    max_pool_size: int = 20
    max_idle_time: float = 600.0  # in seconds
    max_lifetime: float = 3600.0  # in seconds
    ping_threshold: float = 0.25  # in seconds
    enable_health_check: bool = True


def build_from_config(config: Any) -> MariaDBDatabase:
    """Build a database representation from a config file

    Args:
        config (Any): The configuration to build from
    """

    match config.type:
        case "mariadb":
            return MariaDBDatabase(
                db_type=DatabaseType.MARIADB,
                host=config.host,
                port=config.port,
                user=config.user,
                password=config.password,
                database=config.database,
                min_pool_size=config.min_pool_size,
                max_pool_size=config.max_pool_size,
                max_idle_time=config.max_idle_time,
                max_lifetime=config.max_lifetime,
                ping_threshold=config.ping_threshold,
                enable_health_check=config.enable_health_check,
            )
        case _:
            raise ValueError(f"Unsupported database type: {config.type}")
