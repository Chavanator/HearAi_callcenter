from abc import ABC, abstractmethod


class BaseReader(ABC):

    @abstractmethod
    def read(self, **kwargs) -> list[dict]:
        """
        Lee registros del origen.
        Returns: lista de dicts con al menos 'audio_path' y 'source'.
        """
        ...