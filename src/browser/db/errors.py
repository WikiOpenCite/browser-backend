# SPDX-FileCopyrightText: 2026 The University of St Andrews
# SPDX-License-Identifier: GPL-3.0-or-later


class DatabaseError(Exception):
    """General Database Error"""


class NotFoundError(DatabaseError):
    """No row could be found to match the query"""

    def __init__(self, message: str = "could not find row to match query") -> None:
        super().__init__(message)


class NotReadyError(DatabaseError):
    """The data is not yet ready for retrieval"""

    def __init__(self, message: str = "the requested data is not ready yet") -> None:
        super().__init__(message)


class DuplicateError(DatabaseError):
    """Operation would cause duplicate record"""

    def __init__(self, message: str = "operation would cause duplicate record") -> None:
        super().__init__(message)


class InternalError(DatabaseError):
    """An internal error occurred"""

    def __init__(self, message: str = "internal error occurred") -> None:
        super().__init__(message)


class AlreadyCompleteError(DatabaseError):
    """The task has already completed"""

    def __init__(self, message: str = "task already completed") -> None:
        super().__init__(message)


class DBConnectionError(DatabaseError):
    """Failed to connect to the database"""

    def __init__(self, message: str = "failed to connect to database") -> None:
        super().__init__(message)


class DBStateError(DatabaseError):
    """The database is in an invalid state for the requested operation"""

    def __init__(self, message: str = "database is in an invalid state") -> None:
        super().__init__(message)
