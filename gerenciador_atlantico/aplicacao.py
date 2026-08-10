from .mixins.admin import AdminMixin
from .mixins.agendamentos import AgendamentosMixin
from .mixins.base import BaseAppMixin
from .mixins.bsoft import BsoftMixin
from .mixins.buonny import BuonnyMixin
from .mixins.contratos import ContratosMixin
from .mixins.geu import GeuMixin


class PDFInserterApp(BaseAppMixin, AdminMixin, ContratosMixin, AgendamentosMixin, BsoftMixin, GeuMixin, BuonnyMixin):
    pass
