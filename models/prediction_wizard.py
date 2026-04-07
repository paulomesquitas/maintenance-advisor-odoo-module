# -*- coding: utf-8 -*-
from odoo import models, fields

class PredictionResultWizard(models.TransientModel):
    _name        = 'maintenance.prediction.result.wizard'
    _description = 'Resultado da Predição Preditiva'

    equipment_name     = fields.Char(string='Equipamento', readonly=True)
    risk_level         = fields.Char(string='Nível de Risco', readonly=True)
    failure_probability = fields.Float(string='Probabilidade de Falha (%)', readonly=True, digits=(6, 2))
    top_feature        = fields.Char(string='Principal Fator', readonly=True)
    message            = fields.Text(string='Mensagem', readonly=True)
    notification_type  = fields.Selection([
        ('success', 'Normal'),
        ('warning', 'Moderado'),
        ('danger',  'Crítico'),
    ], string='Status', readonly=True)