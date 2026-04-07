# -*- coding: utf-8 -*-
# ==============================================================================
# Controller HTTP — Ingestão de Telemetria via API REST
# Endpoint para receber leituras de sensores de sistemas externos (SCADA, IoT).
# ==============================================================================

import json
import logging
from odoo import http
from odoo.http import request, Response

_logger = logging.getLogger(__name__)


class MaintenanceAdvisorController(http.Controller):
    """
    Endpoints REST do módulo Maintenance Advisor.

    Rota principal: /maintenance-advisor/api/v1/

    Autenticação: Sessão Odoo padrão (cookie session_id) ou API Key.
    Para uso em produção, recomenda-se autenticação via API Key do Odoo 16+.
    """

    # ------------------------------------------------------------------
    # POST /maintenance-advisor/api/v1/telemetry
    # Injeta uma nova leitura de telemetria para um equipamento.
    # ------------------------------------------------------------------

    @http.route(
        '/maintenance-advisor/api/v1/telemetry',
        type='json',
        auth='user',
        methods=['POST'],
        csrf=False,
    )
    def ingest_telemetry(self, **kwargs):
        """
        Recebe uma leitura de telemetria e persiste no banco.
        Opcionalmente aciona a predição imediatamente.

        Payload JSON esperado:
        {
            "equipment_id": 5,                      (obrigatório)
            "air_temperature_k":     298.5,          (obrigatório)
            "process_temperature_k": 309.0,          (obrigatório)
            "rotational_speed_rpm":  1550,           (obrigatório)
            "torque_nm":             38.5,           (obrigatório)
            "tool_wear_min":         45,             (obrigatório)
            "run_prediction":        true,           (opcional, default: false)
            "notes":                 "Leitura SCADA" (opcional)
        }

        Retorno (200):
        {
            "success": true,
            "telemetry_id": 123,
            "prediction": { ... }  // presente se run_prediction=true
        }
        """
        try:
            params = request.get_json_data() or kwargs

            # Validação de campos obrigatórios
            required = ['equipment_id', 'air_temperature_k', 'process_temperature_k',
                        'rotational_speed_rpm', 'torque_nm', 'tool_wear_min']
            missing = [f for f in required if f not in params]
            if missing:
                return {'success': False, 'error': f"Campos obrigatórios ausentes: {missing}"}

            # Criação do registro de telemetria
            telemetry = request.env['maintenance.telemetry'].create({
                'equipment_id':          int(params['equipment_id']),
                'air_temperature_k':     float(params['air_temperature_k']),
                'process_temperature_k': float(params['process_temperature_k']),
                'rotational_speed_rpm':  int(params['rotational_speed_rpm']),
                'torque_nm':             float(params['torque_nm']),
                'tool_wear_min':         int(params['tool_wear_min']),
                'source':                'api',
                'notes':                 params.get('notes', ''),
            })

            result = {
                'success':      True,
                'telemetry_id': telemetry.id,
            }

            # Predição imediata (opcional)
            if params.get('run_prediction'):
                equipment = request.env['maintenance.equipment'].browse(int(params['equipment_id']))
                pred = request.env['maintenance.ai.router'].run_prediction_for_equipment(equipment)
                result['prediction'] = {
                    'failure_probability': pred.get('failure_probability'),
                    'is_critical':         pred.get('is_critical'),
                    'message':             pred.get('message'),
                }

            return result

        except Exception as e:
            _logger.error("[API] Erro ao ingerir telemetria: %s", e, exc_info=True)
            return {'success': False, 'error': str(e)}

    # ------------------------------------------------------------------
    # GET /maintenance-advisor/api/v1/equipment/<id>/status
    # Retorna o status preditivo atual de um equipamento.
    # ------------------------------------------------------------------

    @http.route(
        '/maintenance-advisor/api/v1/equipment/<int:equipment_id>/status',
        type='json',
        auth='user',
        methods=['GET'],
    )
    def get_equipment_status(self, equipment_id, **kwargs):
        """
        Retorna o status preditivo atual de um equipamento.

        Retorno:
        {
            "id": 5,
            "name": "CNC-001",
            "ai_category": "milling",
            "predictive_risk_pct": 82.5,
            "is_critical_risk": true,
            "last_prediction_date": "2024-01-15 14:30:00",
            "shap_top_feature": "Tool wear [min]"
        }
        """
        try:
            eq = request.env['maintenance.equipment'].browse(equipment_id)
            if not eq.exists():
                return {'success': False, 'error': f"Equipamento {equipment_id} não encontrado."}

            return {
                'success':               True,
                'id':                    eq.id,
                'name':                  eq.name,
                'ai_category':           eq.ai_category,
                'predictive_risk_pct':   eq.predictive_risk_pct,
                'is_critical_risk':      eq.is_critical_risk,
                'last_prediction_date':  str(eq.last_prediction_date) if eq.last_prediction_date else None,
                'shap_top_feature':      eq.shap_top_feature,
                'ai_model_version':      eq.ai_model_version,
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}
