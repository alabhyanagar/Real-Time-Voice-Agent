export class TelemetryPanel {
    constructor(element) {
        this.element = element;
        this.values = {};
    }

    update(measurements = {}) {
        Object.assign(this.values, measurements);
        if (!this.element) return;
        this.element.textContent = Object.entries(this.values)
            .map(([key, value]) => `${key.replaceAll('_', ' ')}: ${value}${key.endsWith('_ms') ? ' ms' : ''}`)
            .join(' • ');
    }

    reset() {
        this.values = {};
        if (this.element) this.element.textContent = 'Waiting for telemetry…';
    }
}
