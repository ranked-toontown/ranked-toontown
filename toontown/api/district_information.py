from dataclasses import dataclass
from typing import Any


@dataclass
class DistrictInformation:
    doId: int
    name: str
    population: int

    def to_astron(self) -> list[Any]:
        return [self.doId, self.name, self.population]

    @classmethod
    def from_astron(cls, raw: list[Any]) -> "DistrictInformation":
        return cls(*raw)
