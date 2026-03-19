from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta


class PigWarsError(Exception):
    """Base domain error."""


class GroupOnlyCommandError(PigWarsError):
    """Raised when a game command is used outside of a group chat."""


class InvalidPigNameError(PigWarsError):
    """Raised when a pig name is invalid."""


class PigAlreadyExistsError(PigWarsError):
    """Raised when a user already owns a pig in the group."""


class PigNotFoundError(PigWarsError):
    """Raised when the user does not have a pig in the group."""


@dataclass(slots=True)
class CooldownError(PigWarsError):
    remaining: timedelta


class FeedCooldownError(CooldownError):
    """Raised when feeding is on cooldown."""


class BattleCooldownError(CooldownError):
    """Raised when battle mode is on cooldown."""


class PigBusyError(PigWarsError):
    """Raised when the pig cannot perform an action due to current status."""


class ConcurrentActionError(PigWarsError):
    """Raised when a lock could not be acquired."""
