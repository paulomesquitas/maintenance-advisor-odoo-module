# -*- coding: utf-8 -*-
import logging
import os
import importlib.util
from odoo import models, fields, api
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


def _load_ai_engine():
    engine_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        'utils', 'ai_engine.py'
    )
    spec = importlib.util.spec_from_file_location('maintenance_advisor_ai_engine', engine_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class MaintenanceAIRouter(models.AbstractModel):

    _name        = 'maintenance.ai.router'
    _description = 'Roteador de IA — Orquestrador do Pipeline Preditivo'

    @api.model
    def run_prediction_for_equipment(self, equipment) -> dict:
        equipment.ensure_one()

        features = equipment._get_latest_telemetry_values()
        if not features:
            msg = (
                f"Nenhuma leitura de telemetria encontrada para '{equipment.name}'. "
                "Execute a coleta de dados antes de executar a predição."
            )
            _logger.warning("[AIRouter] %s", msg)
            return {
                'success':                False,
                'message':                msg,
                'failure_probability':    0.0,
                'is_critical':            False,
                'maintenance_request_id': None,
                'notification_type':      'warning',
            }

        ai_engine_module = _load_ai_engine()
        ai_router_instance = ai_engine_module.ai_router_instance
        threshold = equipment._get_effective_threshold()

        try:
            result = ai_router_instance.run(
                ai_category=equipment.ai_category or 'generic',
                features=features,
                threshold=threshold,
                generate_xai=True,
            )
        except Exception as e:
            _logger.error("[AIRouter] Erro no pipeline para '%s': %s", equipment.name, e, exc_info=True)
            raise UserError(f"Erro no motor de IA: {e}")

        failure_pct = result['failure_probability']
        is_critical = result['is_critical']

        write_vals = {
            'predictive_risk_pct':  failure_pct,
            'last_prediction_date': fields.Datetime.now(),
            'ai_model_version':     result.get('model_version', 'unknown'),
        }
        if result.get('shap_chart_b64'):
            write_vals['shap_chart_b64']        = result['shap_chart_b64']
            write_vals['shap_explanation_text'] = result.get('shap_explanation', '')
            write_vals['shap_top_feature']      = result.get('top_feature', '')

        equipment.sudo().write(write_vals)

        maintenance_request_id = None
        if is_critical:
            try:
                req = self._create_maintenance_request(equipment, result)
                maintenance_request_id = req.id
            except Exception as e:
                _logger.error("[AIRouter] Falha ao criar OS: %s", e, exc_info=True)

        if is_critical:
            message = (
                f"⚠️ RISCO CRÍTICO detectado em '{equipment.name}': {failure_pct:.1f}%.\n"
                f"Ordem de Manutenção criada automaticamente. "
                f"Principal fator: {result.get('top_feature', 'N/A')}."
            )
            notification_type = 'danger'
        elif failure_pct >= 40:
            message = (
                f"Risco moderado em '{equipment.name}': {failure_pct:.1f}%. "
                "Monitoramento recomendado."
            )
            notification_type = 'warning'
        else:
            message = f"Equipamento '{equipment.name}' operando normalmente. Risco: {failure_pct:.1f}%."
            notification_type = 'success'

        return {
            'success':                True,
            'message':                message,
            'failure_probability':    failure_pct,
            'is_critical':            is_critical,
            'maintenance_request_id': maintenance_request_id,
            'notification_type':      notification_type,
        }

    def _create_maintenance_request(self, equipment, ai_result: dict):
        failure_pct = ai_result['failure_probability']
        top_feature = ai_result.get('top_feature', 'N/A')
        explanation = ai_result.get('shap_explanation', '')
        model_ver   = ai_result.get('model_version', 'unknown')

        description = f"""
<h2>🚨 Alerta de Manutenção Preditiva — Risco {failure_pct:.1f}%</h2>
<p><strong>Equipamento:</strong> {equipment.name}</p>
<p><strong>Principal variável de risco:</strong> {top_feature}</p>
<p><strong>Modelo de IA:</strong> {model_ver}</p>
<hr/>
{explanation or '<p>Explicação SHAP não disponível.</p>'}
        """.strip()

        request_vals = {
            'name':             f'[Preditivo] Risco {failure_pct:.0f}% — {equipment.name}',
            'equipment_id':     equipment.id,
            'maintenance_type': 'preventive',
            'description':      description,
            'priority':         '3' if failure_pct >= 90 else ('2' if failure_pct >= 70 else '1'),
        }
        if equipment.category_id:
            request_vals['category_id'] = equipment.category_id.id

        req = self.env['maintenance.request'].sudo().create(request_vals)

        if explanation:
            req.message_post(
                body=explanation,
                subject=f'Análise XAI — Risco {failure_pct:.1f}%',
                message_type='comment',
                subtype_xmlid='mail.mt_note',
            )
        return req

    @api.model
    def run_batch_predictions(self, category_filter=None, limit=50) -> dict:
        domain = [('ai_category', '!=', False)]
        if category_filter:
            domain.append(('ai_category', 'in', category_filter))

        equipments = self.env['maintenance.equipment'].search(domain, limit=limit)
        if not equipments:
            return {'processed': 0, 'critical': 0, 'errors': 0}

        processed = critical = errors = 0
        for eq in equipments:
            try:
                result = self.run_prediction_for_equipment(eq)
                processed += 1
                if result.get('is_critical'):
                    critical += 1
            except Exception as e:
                errors += 1
                _logger.error("[BatchPrediction] Erro em '%s': %s", eq.name, e)

        return {'processed': processed, 'critical': critical, 'errors': errors}