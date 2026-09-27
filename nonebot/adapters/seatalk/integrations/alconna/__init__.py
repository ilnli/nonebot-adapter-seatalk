from enum import Enum


class SeaTalkAdapter(str, Enum):
    seatalk = "SeaTalk"


class Loader:
    def get_adapter(self):
        return SeaTalkAdapter.seatalk

    def get_builder(self):
        from .builder import SeaTalkMessageBuilder

        return SeaTalkMessageBuilder()

    def get_exporter(self):
        from .exporter import SeaTalkMessageExporter

        return SeaTalkMessageExporter()

    def get_fetcher(self):
        raise NotImplementedError
