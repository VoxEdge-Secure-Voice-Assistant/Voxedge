/* ── Emergency page ───────────────────────────────────────────────────────── */

import { useEffect, useState } from 'react';
import {
  AlertTriangle,
  CheckCircle2,
  Phone,
  ShieldAlert,
  XCircle,
} from 'lucide-react';
import {
  listEmergencies,
  triggerEmergency,
  updateEmergency,
} from '../api/client';
import type { EmergencyEvent } from '../api/types';

const STATUS_STYLE: Record<string, { bg: string; text: string }> = {
  ACTIVE: { bg: 'bg-danger/15', text: 'text-danger' },
  ACKNOWLEDGED: { bg: 'bg-warning/15', text: 'text-warning' },
  COMPLETED: { bg: 'bg-success/15', text: 'text-success' },
  CANCELLED: { bg: 'bg-bg-hover', text: 'text-text-muted' },
};

export default function EmergencyPage() {
  const [events, setEvents] = useState<EmergencyEvent[]>([]);
  const [triggering, setTriggering] = useState(false);

  const load = () => {
    listEmergencies()
      .then(setEvents)
      .catch(() => {});
  };

  useEffect(load, []);

  const handleTrigger = async () => {
    setTriggering(true);
    try {
      await triggerEmergency('Emergency button pressed (manual)', 'HIGH');
      load();
    } catch {
      /* handled by UI */
    } finally {
      setTriggering(false);
    }
  };

  const handleUpdate = async (id: number, status: string) => {
    try {
      await updateEmergency(id, status);
      load();
    } catch {
      /* handled by UI */
    }
  };

  const active = events.find((e) => e.status === 'ACTIVE');

  return (
    <div className="max-w-4xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold mb-1 flex items-center gap-2">
          <ShieldAlert size={24} className="text-danger" /> Emergency Assistance
        </h1>
        <p className="text-text-secondary text-sm">
          Simulated emergency workflow — no real contacts are notified
        </p>
      </div>

      {/* Active emergency */}
      {active && (
        <div className="bg-danger/10 border-2 border-danger/40 rounded-xl p-6 animate-fade-in">
          <div className="flex items-start gap-4">
            <div className="bg-danger/20 p-3 rounded-xl">
              <AlertTriangle size={28} className="text-danger" />
            </div>
            <div className="flex-1">
              <h2 className="text-lg font-bold text-danger mb-1">
                EMERGENCY ACTIVE
              </h2>
              <p className="text-sm text-text-secondary mb-3">
                {active.trigger_text}
              </p>
              <p className="text-xs text-text-muted mb-4">
                Category: <span className="font-semibold text-danger">{active.category || 'GENERAL'}</span> · Severity: {active.severity} · Triggered:{' '}
                {new Date(active.created_at).toLocaleString()}
              </p>

              {/* Contacts */}
              <div className="space-y-2 mb-4">
                <p className="text-xs text-text-muted uppercase tracking-wide font-semibold">
                  Simulated contacts notified
                </p>
                {active.contacts.map((c, i) => (
                  <div
                    key={i}
                    className="flex items-center gap-3 bg-bg-primary/50 rounded-lg px-4 py-2"
                  >
                    <Phone size={14} className="text-danger" />
                    <div>
                      <p className="text-sm font-medium">{c.name}</p>
                      <p className="text-xs text-text-muted">
                        {c.relationship} · {c.phone}
                      </p>
                    </div>
                    <span className="ml-auto text-xs text-warning">
                      [SIMULATED]
                    </span>
                  </div>
                ))}
              </div>

              {active.notes && (
                <p className="text-xs text-text-muted italic mb-4">
                  {active.notes}
                </p>
              )}

              <div className="flex gap-2">
                <button
                  onClick={() => handleUpdate(active.id, 'ACKNOWLEDGED')}
                  className="bg-warning/15 text-warning hover:bg-warning/25 border border-warning/20 px-4 py-2 rounded-lg text-sm font-semibold transition-colors"
                >
                  Acknowledge
                </button>
                <button
                  onClick={() => handleUpdate(active.id, 'CANCELLED')}
                  className="bg-bg-hover text-text-muted hover:text-text-primary border border-border px-4 py-2 rounded-lg text-sm font-semibold transition-colors"
                >
                  Cancel
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Trigger button */}
      {!active && (
        <div className="bg-bg-card border border-border rounded-xl p-8 text-center">
          <ShieldAlert
            size={48}
            className="mx-auto text-text-muted mb-4 opacity-30"
          />
          <p className="text-text-secondary mb-4">
            No active emergency. Use voice ("help me") or the button below.
          </p>
          <button
            onClick={handleTrigger}
            disabled={triggering}
            className="bg-danger hover:bg-danger/80 text-white font-bold px-8 py-3 rounded-xl text-lg transition-colors disabled:opacity-50"
          >
            {triggering ? 'Triggering…' : '🚨 Trigger Emergency'}
          </button>
        </div>
      )}

      {/* History */}
      {events.length > 0 && (
        <div>
          <h2 className="text-lg font-semibold mb-3">Event History</h2>
          <div className="space-y-2">
            {events.map((e) => {
              const st = STATUS_STYLE[e.status] ?? STATUS_STYLE.CANCELLED;
              return (
                <div
                  key={e.id}
                  className="flex items-center gap-4 bg-bg-card border border-border rounded-xl px-5 py-3"
                >
                  {e.status === 'COMPLETED' ? (
                    <CheckCircle2 size={18} className="text-success" />
                  ) : e.status === 'CANCELLED' ? (
                    <XCircle size={18} className="text-text-muted" />
                  ) : (
                    <AlertTriangle size={18} className="text-danger" />
                  )}
                  <div className="flex-1">
                    <p className="text-sm">{e.trigger_text}</p>
                    <p className="text-xs text-text-muted">
                      {new Date(e.created_at).toLocaleString()}
                    </p>
                  </div>
                  <span
                    className={`px-3 py-1 rounded-full text-xs font-semibold ${st.bg} ${st.text}`}
                  >
                    {e.status}
                  </span>
                  {e.status === 'ACKNOWLEDGED' && (
                    <button
                      onClick={() => handleUpdate(e.id, 'COMPLETED')}
                      className="text-xs text-success hover:underline"
                    >
                      Mark Complete
                    </button>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
