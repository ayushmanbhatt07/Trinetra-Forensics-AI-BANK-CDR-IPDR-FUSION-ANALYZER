"""CDR parser plugins (Jio VVM / Vi / Jio nodal / Airtel)."""

from __future__ import annotations

from .. import parsers_cdr as _v2
from ..errors import SkipFileError
from .base import BaseParser, ParseResult
from .registry import register


class _CdrBase(BaseParser):
    dataset = "CDR"

    def _wrap(self, fn, path):
        try:
            res = fn(path)
        except ValueError as e:
            raise SkipFileError("parse_error", str(e)[:160]) from e
        return ParseResult(res["records"], res.get("meta", {}),
                           self.format_id, self.dataset)


@register
class JioVVMParser(_CdrBase):
    format_id = "jio_vvm"
    description = "Jio VVM ticket export (CSV)"

    def parse(self, path, context=None):
        return self._wrap(_v2.parse_jio_vvm, path)


@register
class ViParser(_CdrBase):
    format_id = "vi"
    description = "Vodafone Idea CDR (CSV)"

    def parse(self, path, context=None):
        return self._wrap(_v2.parse_vi, path)


@register
class JioNodalParser(_CdrBase):
    format_id = "jio_nodal"
    description = "Jio nodal-office export (CSV)"

    def parse(self, path, context=None):
        return self._wrap(_v2.parse_jio_nodal, path)


@register
class AirtelParser(_CdrBase):
    format_id = "airtel"
    description = "Bharti Airtel CDR (CSV)"

    def parse(self, path, context=None):
        return self._wrap(_v2.parse_airtel, path)
