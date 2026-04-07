# -*- coding: utf-8 -*-
from . import models
from . import utils
from . import controllers


def post_init_hook(env):
    """
    Hook executado após a instalação do módulo.
    Garante que equipamentos existentes recebam uma categoria de IA padrão.
    """
    import logging
    _logger = logging.getLogger(__name__)
    equipments = env['maintenance.equipment'].search([('ai_category', '=', False)])
    if equipments:
        equipments.write({'ai_category': 'generic'})
        _logger.info(
            "[PostInit] %d equipamentos receberam categoria de IA padrão 'generic'.",
            len(equipments)
        )
