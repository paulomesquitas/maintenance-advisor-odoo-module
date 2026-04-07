# -*- coding: utf-8 -*-
# ==============================================================================
# Extensão do modelo nativo maintenance.equipment
# Adiciona campos para suportar o ciclo de Manutenção Preditiva com XAI.
# ==============================================================================

import logging
from odoo import models, fields, api
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# Limiar padrão (%) acima do qual o risco é considerado CRÍTICO.
# Pode ser sobrescrito via parâmetro de sistema: maintenance_advisor.failure_threshold
DEFAULT_FAILURE_THRESHOLD = 70.0


class MaintenanceEquipmentPredictive(models.Model):
    """
    Herança de maintenance.equipment para adicionar capacidades preditivas.

    Campos adicionados:
    ------------------
    - Categoria de IA (ai_category): Direciona o roteador de modelos para o
      algoritmo correto (ex: 'milling', 'compressor', 'conveyor').
    - Status preditivo (predictive_risk_pct): Probabilidade de falha em %.
    - Data da última predição (last_prediction_date).
    - Imagem SHAP (shap_chart_b64): Gráfico de explicabilidade em Base64.
    - Explicação textual (shap_explanation_text): Resumo gerado pelo motor XAI.
    - Flag de criticidade (is_critical_risk): Computed para acionar alertas na UI.
    """

    _inherit = 'maintenance.equipment'

    # ------------------------------------------------------------------
    # CAMPOS DE CONFIGURAÇÃO DO MOTOR DE IA
    # ------------------------------------------------------------------

    ai_category = fields.Selection(
        selection=[
            ('milling',    'Fresadora / CNC (AI4I 2020)'),
            ('compressor', 'Compressor'),
            ('conveyor',   'Esteira Transportadora'),
            ('lathe',      'Torno Mecânico'),
            ('generic',    'Genérico'),
        ],
        string='Categoria de IA',
        default='generic',
        required=True,
        help=(
            "Define qual modelo de IA será usado para predição.\n"
            "• 'Fresadora / CNC' → XGBoost treinado no AI4I 2020 Dataset.\n"
            "• Demais categorias → Prontas para integração futura de modelos dedicados."
        ),
    )

    ai_model_version = fields.Char(
        string='Versão do Modelo',
        default='mock-v0.1',
        readonly=True,
        help="Identificador da versão do modelo de IA utilizado na última predição.",
    )

    failure_threshold_override = fields.Float(
        string='Limiar Crítico (%)',
        default=0.0,
        help=(
            "Limiar personalizado de risco crítico para este equipamento (em %).\n"
            "Se 0, usa o valor global definido no parâmetro de sistema "
            "'maintenance_advisor.failure_threshold'."
        ),
    )

    # ------------------------------------------------------------------
    # CAMPOS DE RESULTADO DA PREDIÇÃO
    # ------------------------------------------------------------------

    predictive_risk_pct = fields.Float(
        string='Risco de Falha (%)',
        digits=(6, 2),
        default=0.0,
        readonly=True,
        help="Probabilidade de falha calculada pelo modelo de IA na última execução.",
    )

    last_prediction_date = fields.Datetime(
        string='Última Predição',
        readonly=True,
        help="Data e hora em que o motor de IA realizou a última predição para este equipamento.",
    )

    # ------------------------------------------------------------------
    # CAMPOS DE EXPLICABILIDADE (XAI / SHAP)
    # ------------------------------------------------------------------

    shap_chart_b64 = fields.Binary(
        string='Gráfico SHAP',
        attachment=False,       # Armazenado inline no banco (base64); evita overhead de IR.Attachment
        readonly=True,
        help="Gráfico de barras SHAP (PNG em Base64) mostrando a contribuição de cada variável na predição.",
    )

    shap_chart_filename = fields.Char(
        string='Nome do Gráfico SHAP',
        default='shap_explanation.png',
        readonly=True,
    )

    shap_explanation_text = fields.Html(
        string='Explicação da Predição',
        readonly=True,
        sanitize=True,
        help="Resumo textual gerado pelo motor XAI descrevendo os fatores críticos da predição.",
    )

    shap_top_feature = fields.Char(
        string='Variável Mais Crítica',
        readonly=True,
        help="Nome da variável com maior impacto SHAP na última predição.",
    )

    # ------------------------------------------------------------------
    # CAMPOS COMPUTADOS / RELACIONAIS
    # ------------------------------------------------------------------

    is_critical_risk = fields.Boolean(
        string='Risco Crítico',
        compute='_compute_is_critical_risk',
        store=True,
        help="True quando o risco de falha supera o limiar crítico configurado.",
    )

    telemetry_count = fields.Integer(
        string='Leituras de Telemetria',
        compute='_compute_telemetry_count',
        help="Total de registros de telemetria associados a este equipamento.",
    )

    maintenance_request_predictive_count = fields.Integer(
        string='Ordens Preditivas',
        compute='_compute_maintenance_request_predictive_count',
        help="Total de Ordens de Manutenção geradas automaticamente pelo módulo preditivo.",
    )

    # ------------------------------------------------------------------
    # COMPUTES
    # ------------------------------------------------------------------

    @api.depends('predictive_risk_pct', 'failure_threshold_override')
    def _compute_is_critical_risk(self):
        """Determina se o risco atual ultrapassa o limiar crítico."""
        IrParam = self.env['ir.config_parameter'].sudo()
        global_threshold = float(
            IrParam.get_param('maintenance_advisor.failure_threshold', DEFAULT_FAILURE_THRESHOLD)
        )
        for rec in self:
            threshold = rec.failure_threshold_override if rec.failure_threshold_override > 0 else global_threshold
            rec.is_critical_risk = rec.predictive_risk_pct >= threshold

    def _compute_telemetry_count(self):
        """Conta registros de telemetria por equipamento."""
        Telemetry = self.env['maintenance.telemetry']
        for rec in self:
            rec.telemetry_count = Telemetry.search_count([('equipment_id', '=', rec.id)])

    def _compute_maintenance_request_predictive_count(self):
        """Conta Ordens de Manutenção criadas pelo módulo preditivo."""
        for rec in self:
            rec.maintenance_request_predictive_count = self.env['maintenance.request'].search_count([
                ('equipment_id', '=', rec.id),
                ('name', 'ilike', '[Preditivo]%'),
            ])

    # ------------------------------------------------------------------
    # ACTIONS (botões da UI)
    # ------------------------------------------------------------------

    def action_run_prediction(self):
        self.ensure_one()
        AIRouter = self.env['maintenance.ai.router']
        result = AIRouter.run_prediction_for_equipment(self)

        failure_pct  = result.get('failure_probability', 0.0)
        notif_type   = result.get('notification_type', 'success')

        if notif_type == 'danger':
            risk_label = f'CRÍTICO — {failure_pct:.1f}%'
        elif notif_type == 'warning':
            risk_label = f'Moderado — {failure_pct:.1f}%'
        else:
            risk_label = f'Normal — {failure_pct:.1f}%'

        wizard = self.env['maintenance.prediction.result.wizard'].sudo().create({
            'equipment_name':      self.name,
            'failure_probability': failure_pct,
            'risk_level':          risk_label,
            'top_feature':         result.get('top_feature', ''),
            'message':             result.get('message', ''),
            'notification_type':   notif_type,
        })

        return {
            'type':      'ir.actions.act_window',
            'name':      'Predição Concluída',
            'res_model': 'maintenance.prediction.result.wizard',
            'res_id':    wizard.id,
            'view_mode': 'form',
            'target':    'new',
        }

    def action_view_telemetry(self):
        """Abre a lista de leituras de telemetria para o equipamento atual."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'Telemetria — {self.name}',
            'res_model': 'maintenance.telemetry',
            'view_mode': 'list,form',
            'domain': [('equipment_id', '=', self.id)],
            'context': {'default_equipment_id': self.id},
        }

    def action_view_predictive_requests(self):
        """Abre Ordens de Manutenção preditivas vinculadas ao equipamento."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'Ordens Preditivas — {self.name}',
            'res_model': 'maintenance.request',
            'view_mode': 'list,form',
            'domain': [
                ('equipment_id', '=', self.id),
                ('name', 'ilike', '[Preditivo]%'),
            ],
        }

    # ------------------------------------------------------------------
    # HELPERS INTERNOS
    # ------------------------------------------------------------------

    def _get_effective_threshold(self):
        """Retorna o limiar efetivo (personalizado ou global) para este equipamento."""
        self.ensure_one()
        if self.failure_threshold_override > 0:
            return self.failure_threshold_override
        IrParam = self.env['ir.config_parameter'].sudo()
        return float(
            IrParam.get_param('maintenance_advisor.failure_threshold', DEFAULT_FAILURE_THRESHOLD)
        )

    def _get_latest_telemetry_values(self):
        self.ensure_one()
        latest = self.env['maintenance.telemetry'].search(
            [('equipment_id', '=', self.id)],
            order='reading_datetime desc',
            limit=1,
        )
        if not latest:
            return None

        # Temperaturas armazenadas em °C — convertidas para Kelvin
        # antes de enviar ao modelo (treinado com valores em Kelvin).
        # Fórmula: K = °C + 273.15
        CELSIUS_TO_KELVIN = 273.15
        return {
            'Air temperature [K]':     latest.air_temperature_k     + CELSIUS_TO_KELVIN,
            'Process temperature [K]': latest.process_temperature_k + CELSIUS_TO_KELVIN,
            'Rotational speed [rpm]':  latest.rotational_speed_rpm,
            'Torque [Nm]':             latest.torque_nm,
            'Tool wear [min]':         latest.tool_wear_min,
        }