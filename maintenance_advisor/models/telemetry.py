# -*- coding: utf-8 -*-
# ==============================================================================
# Modelo: maintenance.telemetry
# Armazena leituras de sensores espelhando as variáveis do AI4I 2020 Dataset.
#
# Referência do Dataset:
#   Stephan Matzka, 'Explainable Artificial Intelligence for Predictive
#   Maintenance Applications', 2020 Third ICAISC, pp. 69-74.
#   UCI Machine Learning Repository - ID 601
# ==============================================================================

import logging
import random
from datetime import datetime
from odoo import models, fields, api
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Faixas operacionais do AI4I 2020 Dataset (usadas para validação e mock)
# ------------------------------------------------------------------
AI4I_RANGES = {
    'air_temperature_k':     (295.0, 304.5),    # ~295-305 K (22–31 °C)
    'process_temperature_k': (305.7, 313.8),    # ~306-314 K (33–41 °C)
    'rotational_speed_rpm':  (1168,  2886),     # rpm
    'torque_nm':             (3.8,   76.6),     # Nm
    'tool_wear_min':         (0,     253),      # minutos de uso acumulado
}


class MaintenanceTelemetry(models.Model):
    """
    Registro de telemetria de sensores para um equipamento monitorado.

    Cada linha representa uma "leitura" dos sensores em um instante de tempo,
    espelhando exatamente as features do AI4I 2020 Predictive Maintenance Dataset:

    +---------------------------+--------+-----------------------------------------------+
    | Campo                     | Tipo   | Descrição                                     |
    +---------------------------+--------+-----------------------------------------------+
    | air_temperature_k         | Float  | Temperatura do ar (Kelvin)                    |
    | process_temperature_k     | Float  | Temperatura do processo (Kelvin)              |
    | rotational_speed_rpm      | Int    | Velocidade de rotação (RPM)                   |
    | torque_nm                 | Float  | Torque aplicado (Newton-metro)               |
    | tool_wear_min             | Int    | Desgaste acumulado da ferramenta (minutos)    |
    +---------------------------+--------+-----------------------------------------------+
    """

    _name = 'maintenance.telemetry'
    _description = 'Telemetria de Sensores — Manutenção Preditiva'
    _order = 'reading_datetime desc, id desc'
    _rec_name = 'display_name'

    # ------------------------------------------------------------------
    # CAMPOS PRINCIPAIS
    # ------------------------------------------------------------------

    display_name = fields.Char(
        string='Identificação',
        compute='_compute_display_name',
        store=True,
    )

    equipment_id = fields.Many2one(
        comodel_name='maintenance.equipment',
        string='Equipamento',
        required=True,
        ondelete='cascade',
        index=True,
        help="Equipamento ao qual esta leitura de telemetria pertence.",
    )

    reading_datetime = fields.Datetime(
        string='Data/Hora da Leitura',
        required=True,
        default=fields.Datetime.now,
        index=True,
        help="Timestamp UTC da coleta dos dados pelo sensor.",
    )

    # ------------------------------------------------------------------
    # FEATURES DO AI4I 2020 DATASET
    # ------------------------------------------------------------------

    air_temperature_k = fields.Float(
        string='Temperatura do Ar [°C]',
        help='Temperatura do ar ambiente em graus Celsius. Convertida para Kelvin internamente pelo motor de IA.',
    )
    process_temperature_k = fields.Float(
        string='Temperatura do Processo [°C]',
        help='Temperatura do processo em graus Celsius. Convertida para Kelvin internamente pelo motor de IA.',
    )

    rotational_speed_rpm = fields.Integer(
        string='Velocidade Rotacional [rpm]',
        required=True,
        help=(
            "Velocidade de rotação do eixo principal em RPM.\n"
            "Faixa operacional típica (AI4I): 1168 – 2886 rpm."
        ),
    )

    torque_nm = fields.Float(
        string='Torque [Nm]',
        digits=(8, 2),
        required=True,
        help=(
            "Torque aplicado pelo motor ao eixo em Newton-metro.\n"
            "Faixa operacional típica (AI4I): 3.8 – 76.6 Nm."
        ),
    )

    tool_wear_min = fields.Integer(
        string='Desgaste da Ferramenta [min]',
        required=True,
        help=(
            "Tempo acumulado de uso da ferramenta de corte em minutos.\n"
            "Faixa operacional típica (AI4I): 0 – 253 min. "
            "Valores > 200 min aumentam significativamente o risco de falha."
        ),
    )

    # ------------------------------------------------------------------
    # CAMPOS DERIVADOS / DIAGNÓSTICOS
    # ------------------------------------------------------------------

    temp_delta_k = fields.Float(
        string='ΔT Processo-Ar [K]',
        compute='_compute_derived_features',
        store=True,
        digits=(8, 2),
        help=(
            "Diferença entre a temperatura do processo e do ar (ΔT = T_process − T_air).\n"
            "Feature derivada importante: ΔT elevado pode indicar superaquecimento."
        ),
    )

    power_proxy_w = fields.Float(
        string='Potência Estimada [W]',
        compute='_compute_derived_features',
        store=True,
        digits=(10, 2),
        help=(
            "Estimativa de potência mecânica: P ≈ (2π × RPM × Torque) / 60.\n"
            "Não é medição direta; serve como feature proxy para o modelo de IA."
        ),
    )

    source = fields.Selection(
        selection=[
            ('manual',   'Entrada Manual'),
            ('cron',     'CRON — Simulação Automática'),
            ('api',      'API / Integração Externa'),
            ('csv',      'Importação CSV'),
        ],
        string='Fonte',
        default='manual',
        required=True,
        help="Origem desta leitura de telemetria.",
    )

    anomaly_flag = fields.Boolean(
        string='Anomalia Detectada',
        default=False,
        readonly=True,
        help="Marcado automaticamente quando o motor de pré-processamento detecta valores fora de faixa.",
    )

    notes = fields.Text(
        string='Observações',
        help="Campo livre para anotações do operador ou do sistema.",
    )

    # ------------------------------------------------------------------
    # COMPUTES
    # ------------------------------------------------------------------

    @api.depends('equipment_id', 'reading_datetime')
    def _compute_display_name(self):
        for rec in self:
            eq_name = rec.equipment_id.name if rec.equipment_id else 'N/A'
            dt_str = fields.Datetime.to_string(rec.reading_datetime) if rec.reading_datetime else '—'
            rec.display_name = f'{eq_name} @ {dt_str}'

    @api.depends('air_temperature_k', 'process_temperature_k', 'rotational_speed_rpm', 'torque_nm')
    def _compute_derived_features(self):
        """Calcula features derivadas para enriquecer o vetor de entrada do modelo."""
        import math
        for rec in self:
            # ΔT entre processo e ar
            rec.temp_delta_k = rec.process_temperature_k - rec.air_temperature_k

            # Potência mecânica estimada: P = (2π × n × T) / 60
            if rec.rotational_speed_rpm and rec.torque_nm:
                rec.power_proxy_w = (2 * math.pi * rec.rotational_speed_rpm * rec.torque_nm) / 60.0
            else:
                rec.power_proxy_w = 0.0

    # ------------------------------------------------------------------
    # VALIDAÇÕES
    # ------------------------------------------------------------------

    @api.constrains('air_temperature_k', 'process_temperature_k',
                    'rotational_speed_rpm', 'torque_nm', 'tool_wear_min')
    def _check_sensor_ranges(self):
        """
        Valida se os valores dos sensores estão dentro de faixas fisicamente possíveis.
        Valores extremamente fora do range são rejeitados (dados corrompidos / erro de entrada).
        """
        for rec in self:
            errors = []

            # Temperaturas: não podem ser negativas nem absurdamente altas
            if rec.air_temperature_k <= 0:
                errors.append("Temperatura do Ar deve ser > 0 K.")
            if rec.air_temperature_k > 1000:
                errors.append("Temperatura do Ar parece inválida (> 1000 K).")
            if rec.process_temperature_k <= 0:
                errors.append("Temperatura do Processo deve ser > 0 K.")

            # RPM: não pode ser negativo
            if rec.rotational_speed_rpm < 0:
                errors.append("Velocidade Rotacional não pode ser negativa.")

            # Torque: não pode ser negativo
            if rec.torque_nm < 0:
                errors.append("Torque não pode ser negativo.")

            # Tool wear: não pode ser negativo
            if rec.tool_wear_min < 0:
                errors.append("Desgaste da Ferramenta não pode ser negativo.")

            if errors:
                raise ValidationError(
                    f"Leitura de telemetria inválida para '{rec.equipment_id.name}':\n"
                    + "\n".join(f"  • {e}" for e in errors)
                )

    # ------------------------------------------------------------------
    # MÉTODO DE SIMULAÇÃO (Mock do AI4I 2020)
    # ------------------------------------------------------------------

    @api.model
    def simulate_ai4i_reading(self, equipment_id, scenario='normal'):
        """
        Gera uma leitura de telemetria simulada baseada nas distribuições do AI4I 2020 Dataset.

        Args:
            equipment_id (int): ID do equipamento alvo.
            scenario (str): Perfil de simulação:
                - 'normal'   → valores dentro da faixa operacional saudável.
                - 'degraded' → valores nas bordas superiores (desgaste elevado).
                - 'critical' → valores extremos que tipicamente causam falha no dataset.

        Returns:
            maintenance.telemetry: Registro criado.

        Uso:
            env['maintenance.telemetry'].simulate_ai4i_reading(equipment_id=5, scenario='critical')
        """
        scenarios = {
            'normal': {
                'air_temperature_k':     random.uniform(297.0, 300.0),
                'process_temperature_k': random.uniform(308.0, 310.5),
                'rotational_speed_rpm':  random.randint(1400, 1700),
                'torque_nm':             random.uniform(30.0, 45.0),
                'tool_wear_min':         random.randint(10, 80),
            },
            'degraded': {
                'air_temperature_k':     random.uniform(301.0, 303.5),
                'process_temperature_k': random.uniform(311.0, 313.0),
                'rotational_speed_rpm':  random.randint(1200, 1400),
                'torque_nm':             random.uniform(55.0, 65.0),
                'tool_wear_min':         random.randint(150, 200),
            },
            'critical': {
                'air_temperature_k':     random.uniform(303.0, 304.5),
                'process_temperature_k': random.uniform(312.5, 313.8),
                'rotational_speed_rpm':  random.randint(1168, 1300),
                'torque_nm':             random.uniform(65.0, 76.6),
                'tool_wear_min':         random.randint(200, 253),
            },
        }

        values = scenarios.get(scenario, scenarios['normal'])
        values.update({
            'equipment_id':    equipment_id,
            'reading_datetime': fields.Datetime.now(),
            'source':          'cron',
            'notes':           f'[SIMULAÇÃO] Cenário: {scenario} — AI4I 2020 Mock',
        })

        record = self.create(values)
        _logger.info(
            "Telemetria simulada criada: equipamento_id=%s, cenário=%s, "
            "torque=%.2f Nm, tool_wear=%d min",
            equipment_id, scenario, values['torque_nm'], values['tool_wear_min']
        )
        return record

    @api.model
    def cron_simulate_telemetry(self, category='milling', limit=10):
        """
        Método chamado pelo CRON para simular leituras de telemetria.

        Encapsula a lógica de seleção aleatória de cenário, evitando o uso
        de 'import' no código do cron (proibido pelo safe_eval do Odoo).

        Args:
            category (str): Categoria AI dos equipamentos a simular. Default: 'milling'.
            limit (int): Número máximo de equipamentos a processar. Default: 10.
        """
        equipments = self.env['maintenance.equipment'].search(
            [('ai_category', '=', category)], limit=limit
        )
        scenarios = ['normal', 'normal', 'normal', 'degraded', 'critical']
        for eq in equipments:
            scenario = random.choice(scenarios)
            self.simulate_ai4i_reading(equipment_id=eq.id, scenario=scenario)

    # ------------------------------------------------------------------
    # MÉTODO: Exportar para vetor NumPy/Pandas-ready
    # ------------------------------------------------------------------

    def to_feature_dict(self):
        """
        Converte o registro atual para um dicionário de features pronto para inferência.

        Returns:
            dict: Features na mesma ordem esperada pelo modelo XGBoost treinado no AI4I 2020.

        Exemplo de uso no AIEngine:
            features = telemetry_record.to_feature_dict()
            df = pd.DataFrame([features])
        """
        self.ensure_one()
        return {
            'Air temperature [K]':     self.air_temperature_k,
            'Process temperature [K]': self.process_temperature_k,
            'Rotational speed [rpm]':  float(self.rotational_speed_rpm),
            'Torque [Nm]':             self.torque_nm,
            'Tool wear [min]':         float(self.tool_wear_min),
        }
