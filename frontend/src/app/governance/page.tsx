"use client";

import { useState, useEffect, useCallback } from "react";

// ── Types ──────────────────────────────────────────────────────────────────

interface ReviewRecord {
  review_id: string;
  request_id: string;
  query_preview: string;
  workflow_type: string;
  confidence: number;
  severity: "critical" | "high" | "medium" | "low";
  escalation_reasons: string[];
  status: "pending_review" | "approved" | "rejected" | "overridden" | "retry_requested";
  reviewed_by: string | null;
  clinician_notes: string | null;
  clinician_override: string | null;
  reviewed_at: string | null;
  created_at: string;
}

interface GovernanceStats {
  total_reviews: number;
  pending: number;
  approved: number;
  rejected: number;
  overridden: number;
  retry_requested: number;
  approval_rate: number | null;
  severity_breakdown: { critical: number; high: number; medium: number };
}

// ── Constants ──────────────────────────────────────────────────────────────

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const SEVERITY_CONFIG = {
  critical: { bg: "bg-red-500/15 border-red-500/40", badge: "bg-red-600 text-white", dot: "bg-red-500", label: "CRITICAL" },
  high:     { bg: "bg-orange-500/15 border-orange-500/40", badge: "bg-orange-500 text-white", dot: "bg-orange-400", label: "HIGH" },
  medium:   { bg: "bg-yellow-500/10 border-yellow-500/30", badge: "bg-yellow-600 text-white", dot: "bg-yellow-400", label: "MEDIUM" },
  low:      { bg: "bg-slate-700/30 border-slate-600/40", badge: "bg-slate-600 text-white", dot: "bg-slate-400", label: "LOW" },
};

const STATUS_CONFIG = {
  pending_review:  { color: "text-amber-400",  icon: "⏳", label: "Pending Review" },
  approved:        { color: "text-emerald-400", icon: "✅", label: "Approved" },
  rejected:        { color: "text-red-400",     icon: "❌", label: "Rejected" },
  overridden:      { color: "text-violet-400",  icon: "✏️", label: "Overridden" },
  retry_requested: { color: "text-blue-400",    icon: "🔄", label: "Retry Requested" },
};

// ── Helpers ────────────────────────────────────────────────────────────────

const fmt = (iso: string | null) =>
  iso ? new Date(iso).toLocaleString() : "—";

// ── Components ─────────────────────────────────────────────────────────────

function StatCard({ label, value, sub }: { label: string; value: number | string; sub?: string }) {
  return (
    <div className="rounded-xl border border-slate-700/60 bg-slate-800/60 p-5">
      <p className="text-xs font-medium uppercase tracking-widest text-slate-400">{label}</p>
      <p className="mt-1 text-3xl font-bold text-white">{value}</p>
      {sub && <p className="mt-0.5 text-xs text-slate-500">{sub}</p>}
    </div>
  );
}

function ReviewModal({
  record,
  onClose,
  onSubmit,
}: {
  record: ReviewRecord;
  onClose: () => void;
  onSubmit: (action: string, reviewedBy: string, notes: string, override?: string) => Promise<void>;
}) {
  const [action, setAction] = useState<string>("");
  const [reviewedBy, setReviewedBy] = useState("");
  const [notes, setNotes] = useState("");
  const [override, setOverride] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  const sev = SEVERITY_CONFIG[record.severity] ?? SEVERITY_CONFIG.low;

  const handleSubmit = async () => {
    if (!action) { setError("Select an action."); return; }
    if (!reviewedBy.trim()) { setError("Reviewer name is required."); return; }
    if (action === "override" && !override.trim()) { setError("Override text is required."); return; }
    setError("");
    setSubmitting(true);
    try {
      await onSubmit(action, reviewedBy, notes, override || undefined);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
      <div className="w-full max-w-2xl rounded-2xl border border-slate-700 bg-slate-900 shadow-2xl overflow-hidden">
        {/* Header */}
        <div className={`border-b border-slate-700 px-6 py-4 flex items-center justify-between ${sev.bg}`}>
          <div className="flex items-center gap-3">
            <span className={`h-2.5 w-2.5 rounded-full animate-pulse ${sev.dot}`} />
            <h2 className="font-semibold text-white">Review Escalated Output</h2>
            <span className={`rounded-full px-2 py-0.5 text-xs font-bold ${sev.badge}`}>{sev.label}</span>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-white transition-colors text-xl leading-none">×</button>
        </div>

        <div className="p-6 space-y-5 max-h-[70vh] overflow-y-auto">
          {/* Meta */}
          <div className="grid grid-cols-2 gap-3 text-sm">
            <div className="rounded-lg bg-slate-800 p-3">
              <p className="text-xs text-slate-400 mb-0.5">Review ID</p>
              <p className="font-mono text-xs text-slate-300 truncate">{record.review_id}</p>
            </div>
            <div className="rounded-lg bg-slate-800 p-3">
              <p className="text-xs text-slate-400 mb-0.5">Workflow</p>
              <p className="text-slate-300 capitalize">{record.workflow_type}</p>
            </div>
            <div className="rounded-lg bg-slate-800 p-3">
              <p className="text-xs text-slate-400 mb-0.5">Confidence</p>
              <p className="text-slate-300">{(record.confidence * 100).toFixed(1)}%</p>
            </div>
            <div className="rounded-lg bg-slate-800 p-3">
              <p className="text-xs text-slate-400 mb-0.5">Escalated At</p>
              <p className="text-slate-300 text-xs">{fmt(record.created_at)}</p>
            </div>
          </div>

          {/* Query preview */}
          <div>
            <p className="text-xs font-medium text-slate-400 mb-1 uppercase tracking-wide">Query Preview</p>
            <p className="rounded-lg bg-slate-800 p-3 text-sm text-slate-300 italic">
              &ldquo;{record.query_preview}&rdquo;
            </p>
          </div>

          {/* Escalation reasons */}
          <div>
            <p className="text-xs font-medium text-slate-400 mb-2 uppercase tracking-wide">Escalation Triggers</p>
            <div className="flex flex-wrap gap-2">
              {record.escalation_reasons.map((r, i) => (
                <span key={i} className="rounded-full bg-red-900/40 border border-red-700/40 px-2.5 py-1 text-xs text-red-300 font-mono">
                  {r}
                </span>
              ))}
            </div>
          </div>

          {/* Action selection */}
          <div>
            <p className="text-xs font-medium text-slate-400 mb-2 uppercase tracking-wide">Clinician Action</p>
            <div className="grid grid-cols-2 gap-2">
              {[
                { v: "approve",        icon: "✅", label: "Approve AI Output", color: "border-emerald-600 bg-emerald-900/20 hover:bg-emerald-900/40" },
                { v: "reject",         icon: "❌", label: "Reject Output", color: "border-red-600 bg-red-900/20 hover:bg-red-900/40" },
                { v: "override",       icon: "✏️", label: "Override with Correction", color: "border-violet-600 bg-violet-900/20 hover:bg-violet-900/40" },
                { v: "request_retry",  icon: "🔄", label: "Request Retry", color: "border-blue-600 bg-blue-900/20 hover:bg-blue-900/40" },
              ].map(opt => (
                <button
                  key={opt.v}
                  onClick={() => setAction(opt.v)}
                  className={`rounded-lg border p-3 text-left text-sm text-white transition-all ${opt.color} ${action === opt.v ? "ring-2 ring-white/30 scale-[1.02]" : "opacity-70"}`}
                >
                  <span className="mr-2">{opt.icon}</span>{opt.label}
                </button>
              ))}
            </div>
          </div>

          {/* Override text */}
          {action === "override" && (
            <div>
              <p className="text-xs font-medium text-slate-400 mb-1 uppercase tracking-wide">Clinician Correction</p>
              <textarea
                value={override}
                onChange={e => setOverride(e.target.value)}
                rows={4}
                placeholder="Enter your clinical assessment to replace the AI output..."
                className="w-full rounded-lg bg-slate-800 border border-slate-600 p-3 text-sm text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-violet-500 resize-none"
              />
            </div>
          )}

          {/* Reviewer identity */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <p className="text-xs font-medium text-slate-400 mb-1 uppercase tracking-wide">Reviewer ID / Name</p>
              <input
                value={reviewedBy}
                onChange={e => setReviewedBy(e.target.value)}
                placeholder="e.g. Dr. Smith / ID-4421"
                className="w-full rounded-lg bg-slate-800 border border-slate-600 px-3 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div>
              <p className="text-xs font-medium text-slate-400 mb-1 uppercase tracking-wide">Notes (optional)</p>
              <input
                value={notes}
                onChange={e => setNotes(e.target.value)}
                placeholder="Clinical rationale..."
                className="w-full rounded-lg bg-slate-800 border border-slate-600 px-3 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
          </div>

          {error && <p className="text-red-400 text-sm">{error}</p>}
        </div>

        {/* Footer */}
        <div className="border-t border-slate-700 px-6 py-4 flex justify-end gap-3">
          <button onClick={onClose} className="rounded-lg px-4 py-2 text-sm text-slate-400 hover:text-white transition-colors">
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={submitting}
            className="rounded-lg bg-blue-600 hover:bg-blue-500 disabled:opacity-50 px-6 py-2 text-sm font-semibold text-white transition-colors"
          >
            {submitting ? "Submitting…" : "Submit Review"}
          </button>
        </div>
      </div>
    </div>
  );
}

function ReviewRow({ record, onClick }: { record: ReviewRecord; onClick: () => void }) {
  const sev = SEVERITY_CONFIG[record.severity] ?? SEVERITY_CONFIG.low;
  const st  = STATUS_CONFIG[record.status]     ?? STATUS_CONFIG.pending_review;

  return (
    <tr
      onClick={onClick}
      className="border-b border-slate-700/50 hover:bg-slate-700/30 cursor-pointer transition-colors"
    >
      <td className="px-4 py-3">
        <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-bold ${sev.badge}`}>
          <span className={`h-1.5 w-1.5 rounded-full ${sev.dot} animate-pulse`} />
          {sev.label}
        </span>
      </td>
      <td className="px-4 py-3 max-w-[280px]">
        <p className="text-sm text-slate-300 truncate">{record.query_preview}</p>
      </td>
      <td className="px-4 py-3">
        <span className="rounded-full bg-slate-700 px-2 py-0.5 text-xs text-slate-300 capitalize">{record.workflow_type}</span>
      </td>
      <td className="px-4 py-3">
        <span className={`text-sm font-medium ${st.color}`}>{st.icon} {st.label}</span>
      </td>
      <td className="px-4 py-3 text-xs text-slate-400">{(record.confidence * 100).toFixed(1)}%</td>
      <td className="px-4 py-3 text-xs text-slate-500">{fmt(record.created_at)}</td>
      <td className="px-4 py-3 text-xs text-slate-400">{record.reviewed_by ?? "—"}</td>
    </tr>
  );
}

// ── Main Page ──────────────────────────────────────────────────────────────

export default function GovernanceDashboard() {
  const [tab, setTab]           = useState<"pending" | "all" | "audit">("pending");
  const [reviews, setReviews]   = useState<ReviewRecord[]>([]);
  const [audit, setAudit]       = useState<Record<string, unknown>[]>([]);
  const [stats, setStats]       = useState<GovernanceStats | null>(null);
  const [selected, setSelected] = useState<ReviewRecord | null>(null);
  const [loading, setLoading]   = useState(false);
  const [toast, setToast]       = useState<{ msg: string; ok: boolean } | null>(null);

  const showToast = (msg: string, ok = true) => {
    setToast({ msg, ok });
    setTimeout(() => setToast(null), 3500);
  };

  const fetchStats = useCallback(async () => {
    try {
      const r = await fetch(`${API_BASE}/governance/stats`);
      if (r.ok) setStats(await r.json());
    } catch {}
  }, []);

  const fetchReviews = useCallback(async () => {
    setLoading(true);
    try {
      const url = tab === "pending"
        ? `${API_BASE}/governance/reviews/pending`
        : `${API_BASE}/governance/reviews/all`;
      const r = await fetch(url);
      if (r.ok) {
        const data = await r.json();
        setReviews(data.reviews ?? []);
      }
    } catch {
      showToast("Failed to fetch reviews", false);
    } finally {
      setLoading(false);
    }
  }, [tab]);

  const fetchAudit = useCallback(async () => {
    if (tab !== "audit") return;
    setLoading(true);
    try {
      const r = await fetch(`${API_BASE}/governance/audit?limit=100`);
      if (r.ok) setAudit((await r.json()).events ?? []);
    } catch {} finally {
      setLoading(false);
    }
  }, [tab]);

  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { fetchStats(); }, [fetchStats]);
  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { if (tab !== "audit") fetchReviews(); else fetchAudit(); }, [tab, fetchReviews, fetchAudit]);

  const handleSubmitReview = async (action: string, reviewedBy: string, notes: string, override?: string) => {
    if (!selected) return;
    const body: Record<string, unknown> = { action, reviewed_by: reviewedBy, notes };
    if (override) body.override_text = override;

    const r = await fetch(`${API_BASE}/governance/reviews/${selected.review_id}/action`, {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify(body),
    });

    if (!r.ok) {
      const err = await r.json().catch(() => ({}));
      showToast(err.detail ?? "Review submission failed.", false);
      return;
    }

    showToast(`Review ${action.replace("_", " ")} submitted successfully.`);
    setSelected(null);
    fetchReviews();
    fetchStats();
  };

  return (
    <div className="min-h-screen bg-background text-foreground font-sans">
      {/* Toast */}
      {toast && (
        <div className={`fixed top-4 right-4 z-50 rounded-xl px-5 py-3 text-sm font-medium shadow-xl transition-all ${toast.ok ? "bg-emerald-600" : "bg-red-600"}`}>
          {toast.ok ? "✅" : "❌"} {toast.msg}
        </div>
      )}

      {/* Review modal */}
      {selected && (
        <ReviewModal record={selected} onClose={() => setSelected(null)} onSubmit={handleSubmitReview} />
      )}

      {/* Top bar */}
      <header className="border-b border-slate-800 bg-slate-900/80 backdrop-blur-md sticky top-0 z-20">
        <div className="mx-auto max-w-7xl flex items-center justify-between px-6 py-4">
          <div className="flex items-center gap-3">
            <div className="h-8 w-8 rounded-lg bg-gradient-to-br from-violet-500 to-blue-600 flex items-center justify-center text-sm font-bold">
              Æ
            </div>
            <div>
              <h1 className="text-sm font-bold text-white">Aegis Clinical AI</h1>
              <p className="text-xs text-slate-400">Governance & HITL Dashboard</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {stats?.pending != null && stats.pending > 0 && (
              <span className="animate-pulse rounded-full bg-red-600 px-2.5 py-0.5 text-xs font-bold">
                {stats.pending} PENDING
              </span>
            )}
            <button
              onClick={() => { fetchStats(); if (tab !== "audit") fetchReviews(); else fetchAudit(); }}
              className="rounded-lg bg-slate-700 hover:bg-slate-600 px-3 py-1.5 text-xs font-medium transition-colors"
            >
              ↻ Refresh
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-6 py-8 space-y-8">
        {/* Stats row */}
        {stats && (
          <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-4">
            <StatCard label="Total Reviews" value={stats.total_reviews} />
            <StatCard label="Pending" value={stats.pending} sub="awaiting review" />
            <StatCard label="Approved" value={stats.approved} />
            <StatCard label="Rejected" value={stats.rejected} />
            <StatCard label="Overridden" value={stats.overridden} sub="clinician corrected" />
            <StatCard label="Retried" value={stats.retry_requested} />
            <StatCard
              label="Approval Rate"
              value={stats.approval_rate != null ? `${(stats.approval_rate * 100).toFixed(0)}%` : "N/A"}
            />
          </div>
        )}

        {/* Severity breakdown */}
        {stats && (
          <div className="rounded-xl border border-slate-700/60 bg-slate-800/40 p-5">
            <p className="text-xs font-medium uppercase tracking-widest text-slate-400 mb-4">Severity Breakdown</p>
            <div className="flex gap-4 flex-wrap">
              {([
                ["critical", "bg-red-500",    stats.severity_breakdown.critical],
                ["high",     "bg-orange-400", stats.severity_breakdown.high],
                ["medium",   "bg-yellow-400", stats.severity_breakdown.medium],
              ] as [string, string, number][]).map(([label, color, count]) => (
                <div key={label} className="flex items-center gap-2">
                  <span className={`h-3 w-3 rounded-full ${color}`} />
                  <span className="text-sm text-slate-300 capitalize">{label}</span>
                  <span className="font-bold text-white">{count}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Tabs */}
        <div className="flex gap-1 rounded-lg bg-slate-800/60 p-1 w-fit border border-slate-700/60">
          {(["pending", "all", "audit"] as const).map(t => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`rounded-md px-4 py-1.5 text-sm font-medium transition-colors capitalize ${
                tab === t
                  ? "bg-slate-600 text-white shadow"
                  : "text-slate-400 hover:text-white"
              }`}
            >
              {t === "pending" ? "⏳ Pending" : t === "all" ? "📋 All Reviews" : "📜 Audit Log"}
            </button>
          ))}
        </div>

        {/* Content */}
        {loading ? (
          <div className="flex items-center justify-center py-20 text-slate-500">
            <div className="h-6 w-6 animate-spin rounded-full border-2 border-slate-600 border-t-blue-400 mr-3" />
            Loading…
          </div>
        ) : tab !== "audit" ? (
          reviews.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-20 text-center">
              <div className="text-5xl mb-4">{tab === "pending" ? "✅" : "📋"}</div>
              <p className="text-slate-300 font-medium">
                {tab === "pending" ? "No pending reviews." : "No reviews found."}
              </p>
              <p className="text-slate-500 text-sm mt-1">
                {tab === "pending"
                  ? "All AI outputs have been cleared or reviewed."
                  : "Submit queries to generate governance records."}
              </p>
            </div>
          ) : (
            <div className="rounded-xl border border-slate-700/60 bg-slate-800/40 overflow-hidden">
              <table className="w-full text-left">
                <thead>
                  <tr className="border-b border-slate-700 bg-slate-800/80">
                    {["Severity", "Query Preview", "Workflow", "Status", "Confidence", "Created", "Reviewer"].map(h => (
                      <th key={h} className="px-4 py-3 text-xs font-medium uppercase tracking-wider text-slate-400">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {reviews.map(r => (
                    <ReviewRow
                      key={r.review_id}
                      record={r}
                      onClick={() => r.status === "pending_review" ? setSelected(r) : undefined}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          )
        ) : (
          /* Audit log tab */
          audit.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-20 text-center">
              <div className="text-5xl mb-4">📜</div>
              <p className="text-slate-300 font-medium">Audit log is empty.</p>
              <p className="text-slate-500 text-sm mt-1">Events are logged as AI outputs are reviewed.</p>
            </div>
          ) : (
            <div className="rounded-xl border border-slate-700/60 bg-slate-800/40 overflow-hidden">
              <table className="w-full text-left">
                <thead>
                  <tr className="border-b border-slate-700 bg-slate-800/80">
                    {["Event", "Request ID", "Actor", "Severity", "Workflow", "Confidence", "Timestamp", "Notes"].map(h => (
                      <th key={h} className="px-4 py-3 text-xs font-medium uppercase tracking-wider text-slate-400">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {audit.map((ev, i) => {
                    const evType = String(ev.event_type ?? "");
                    const evColor = evType === "APPROVED" ? "text-emerald-400"
                      : evType === "REJECTED" ? "text-red-400"
                      : evType === "OVERRIDE" ? "text-violet-400"
                      : evType === "ESCALATED" ? "text-amber-400"
                      : "text-slate-300";
                    return (
                      <tr key={i} className="border-b border-slate-700/40 hover:bg-slate-700/20 transition-colors">
                        <td className={`px-4 py-3 text-xs font-bold font-mono ${evColor}`}>{evType}</td>
                        <td className="px-4 py-3 text-xs font-mono text-slate-400 truncate max-w-[140px]">{String(ev.request_id ?? "").slice(0, 12)}…</td>
                        <td className="px-4 py-3 text-xs text-slate-300">{String(ev.actor ?? "system")}</td>
                        <td className="px-4 py-3">
                          {ev.severity != null && (
                            <span className={`text-xs font-bold ${SEVERITY_CONFIG[String(ev.severity) as keyof typeof SEVERITY_CONFIG]?.badge ?? "bg-slate-600 text-white"} rounded-full px-2 py-0.5`}>
                              {String(ev.severity).toUpperCase()}
                            </span>
                          )}
                        </td>
                        <td className="px-4 py-3 text-xs text-slate-400 capitalize">{String(ev.workflow_type ?? "—")}</td>
                        <td className="px-4 py-3 text-xs text-slate-400">
                          {ev.confidence != null ? `${(Number(ev.confidence) * 100).toFixed(1)}%` : "—"}
                        </td>
                        <td className="px-4 py-3 text-xs text-slate-500">{fmt(String(ev.created_at ?? ""))}</td>
                        <td className="px-4 py-3 text-xs text-slate-400 max-w-[160px] truncate">{String(ev.notes ?? "—")}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )
        )}
      </main>
    </div>
  );
}
