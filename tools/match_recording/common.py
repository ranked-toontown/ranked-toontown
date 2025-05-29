from abc import ABC, abstractmethod
from typing import Any


class Serializable(ABC):

    @abstractmethod
    def serialize(self) -> dict[str, Any]:
        raise NotImplementedError("Please implement this method")

    @classmethod
    @abstractmethod
    def deserialize(cls, data: dict[str, Any]):
        raise NotImplementedError("Please implement this method")