/** @odoo-module **/

import { Component, useState, onWillStart } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { registry } from "@web/core/registry";

const THRESHOLD_CRITICAL = 70;
const THRESHOLD_WARNING  = 40;

class EquipmentRiskCard extends Component {
    static template = "maintenance_advisor.EquipmentRiskCard";
    static props = {
        equipment: Object,
        onRunPrediction: Function,
    };

    get riskClass() {
        const risk = this.props.equipment.predictive_risk_pct || 0;
        if (risk >= THRESHOLD_CRITICAL) return "card-critical";
        if (risk >= THRESHOLD_WARNING)  return "card-warning";
        return "card-safe";
    }

    get riskLabel() {
        const risk = this.props.equipment.predictive_risk_pct || 0;
        if (risk >= THRESHOLD_CRITICAL) return "🔴 CRÍTICO";
        if (risk >= THRESHOLD_WARNING)  return "🟡 MODERADO";
        return "🟢 NORMAL";
    }

    get riskBarWidth() {
        return Math.min(this.props.equipment.predictive_risk_pct || 0, 100);
    }

    get riskBarColor() {
        const risk = this.props.equipment.predictive_risk_pct || 0;
        if (risk >= THRESHOLD_CRITICAL) return "#E74C3C";
        if (risk >= THRESHOLD_WARNING)  return "#F39C12";
        return "#27AE60";
    }

    onRunPrediction() {
        this.props.onRunPrediction(this.props.equipment.id);
    }
}

class PredictiveDashboard extends Component {
    static template = "maintenance_advisor.PredictiveDashboard";
    static components = { EquipmentRiskCard };

    setup() {
        this.orm          = useService("orm");
        this.action       = useService("action");
        this.notification = useService("notification");

        this.state = useState({
            equipments:        [],
            isLoading:         true,
            errorMessage:      null,
            filterStatus:      "all",
            sortBy:            "risk_desc",
            searchTerm:        "",
            lastRefresh:       null,
            runningPrediction: null,
        });

        // Hook correto para OWL 2 — deve ser chamado dentro do setup()
        onWillStart(async () => {
            await this._loadEquipments();
        });
    }

    async _loadEquipments() {
        this.state.isLoading    = true;
        this.state.errorMessage = null;
        try {
            const records = await this.orm.searchRead(
                "maintenance.equipment",
                [["ai_category", "!=", false]],
                [
                    "id", "name", "ai_category", "predictive_risk_pct",
                    "last_prediction_date", "is_critical_risk", "shap_top_feature",
                    "ai_model_version",
                ],
                { limit: 100, order: "predictive_risk_pct DESC" }
            );
            this.state.equipments  = records;
            this.state.lastRefresh = new Date().toLocaleTimeString("pt-BR");
        } catch (err) {
            this.state.errorMessage = `Erro ao carregar equipamentos: ${err.message}`;
        } finally {
            this.state.isLoading = false;
        }
    }

    get filteredEquipments() {
        let eq = [...this.state.equipments];

        if (this.state.filterStatus === "critical") {
            eq = eq.filter(e => (e.predictive_risk_pct || 0) >= THRESHOLD_CRITICAL);
        } else if (this.state.filterStatus === "warning") {
            eq = eq.filter(e => {
                const r = e.predictive_risk_pct || 0;
                return r >= THRESHOLD_WARNING && r < THRESHOLD_CRITICAL;
            });
        } else if (this.state.filterStatus === "safe") {
            eq = eq.filter(e => (e.predictive_risk_pct || 0) < THRESHOLD_WARNING);
        }

        if (this.state.searchTerm.trim()) {
            const term = this.state.searchTerm.toLowerCase();
            eq = eq.filter(e => e.name.toLowerCase().includes(term));
        }

        if (this.state.sortBy === "risk_desc") {
            eq.sort((a, b) => (b.predictive_risk_pct || 0) - (a.predictive_risk_pct || 0));
        } else if (this.state.sortBy === "name") {
            eq.sort((a, b) => a.name.localeCompare(b.name));
        } else if (this.state.sortBy === "last_prediction") {
            eq.sort((a, b) => {
                const da = a.last_prediction_date ? new Date(a.last_prediction_date) : new Date(0);
                const db = b.last_prediction_date ? new Date(b.last_prediction_date) : new Date(0);
                return db - da;
            });
        }

        return eq;
    }

    get summaryStats() {
        const all      = this.state.equipments;
        const critical = all.filter(e => (e.predictive_risk_pct || 0) >= THRESHOLD_CRITICAL).length;
        const warning  = all.filter(e => {
            const r = e.predictive_risk_pct || 0;
            return r >= THRESHOLD_WARNING && r < THRESHOLD_CRITICAL;
        }).length;
        const safe    = all.length - critical - warning;
        const avgRisk = all.length
            ? (all.reduce((s, e) => s + (e.predictive_risk_pct || 0), 0) / all.length).toFixed(1)
            : 0;
        return { total: all.length, critical, warning, safe, avgRisk };
    }

    async onRunPrediction(equipmentId) {
        this.state.runningPrediction = equipmentId;
        try {
            await this.orm.call("maintenance.equipment", "action_run_prediction", [[equipmentId]]);
            this.notification.add("Predição concluída!", { type: "success" });
            await this._loadEquipments();
        } catch (err) {
            this.notification.add(`Erro: ${err.message}`, { type: "danger" });
        } finally {
            this.state.runningPrediction = null;
        }
    }

    onOpenEquipment(equipmentId) {
        this.action.doAction({
            type:      "ir.actions.act_window",
            res_model: "maintenance.equipment",
            res_id:    equipmentId,
            views:     [[false, "form"]],
            target:    "current",
        });
    }

    onRefresh() {
        this._loadEquipments();
    }

    // Método direto — sem arrow function no template para evitar perda de contexto
    onFilterChange(ev) {
        this.state.filterStatus = ev.target.dataset.filter;
    }

    onSortChange(ev) {
        this.state.sortBy = ev.target.value;
    }

    onSearchChange(ev) {
        this.state.searchTerm = ev.target.value;
    }
}

registry.category("actions").add("maintenance_advisor.predictive_dashboard", PredictiveDashboard);

export { PredictiveDashboard, EquipmentRiskCard };