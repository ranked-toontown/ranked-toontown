from dataclasses import dataclass


@dataclass
class AccountLookupResult:
    success: bool
    accountId: int = 0
    databaseId: str = 0
    accessLevel: str = "NO_ACCESS"
    reason: str = "The accounts database rejected your play token."