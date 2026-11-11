/* ── Evaluation page — Live System Benchmark & Performance Metrics ──────── */

import { useEffect, useState } from 'react';
import {
  BarChart3,
  CheckCircle2,
  XCircle,
  Play,
  RotateCcw,
  ShieldCheck,
  Target,
  Sparkles,
  Info,
  HelpCircle,
} from 'lucide-react';
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from 'recharts';

interface EvalCaseResult {
  id: string;
  text: string;
  category: string;
  description: string;
  expected_decision: string;
  baseline: {
    executed: boolean;
    device: string | null;
    action: string | null;
    passed: boolean;
  };
  enhanced: {
    decision: string;
    device: string | null;
    action: string | null;
    confidence: number;
    reason: string;
    passed: boolean;
  };
}

interface EvalResponse {
  summary: {
    total_cases: number;
    baseline_accuracy: number;
    enhanced_accuracy: number;
    baseline_safety: number;
    enhanced_safety: number;
    baseline_usability: number;
    enhanced_usability: number;
    accuracy_improvement: number;
    safety_improvement: number;
    usability_improvement: number;
  };
  metrics_chart: Array<{ metric: string; baseline: number; enhanced: number }>;
  cases: EvalCaseResult[];
}

export default function EvaluationPage() {
  const [data, setData] = useState<EvalResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [selectedCategory, setSelectedCategory] = useState<string>('all');
  const [error, setError] = useState<string | null>(null);

  const runBenchmark = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch('/api/evaluation/run');
      if (!res.ok) throw new Error(`Benchmark failed: ${res.statusText}`);
      const json: EvalResponse = await res.json();
      setData(json);
    } catch (err: any) {
      setError(err.message || 'Failed to connect to backend evaluation service.');
    } finally {
      setLoading(false);
    }
  };

  // Tests are executed when the user clicks the "Run Evaluation" button.
  // Initially, data is null and the page displays "Not Evaluated".

  // Compute metrics dynamically from actual test results
  const totalCases = data?.cases.length ?? 0;
  const passedCases = data?.cases.filter((c) => c.enhanced.passed).length ?? 0;
  const accuracyPct = totalCases > 0 ? (passedCases / totalCases) * 100 : null;

  const safetyCases = data?.cases.filter((c) => c.category === 'safety') ?? [];
  const safetyPassed = safetyCases.filter((c) => c.enhanced.passed).length;
  const safetyPct = safetyCases.length > 0 ? (safetyPassed / safetyCases.length) * 100 : null;

  const usabilityCases = data?.cases.filter((c) => c.category === 'usability') ?? [];
  const usabilityPassed = usabilityCases.filter((c) => c.enhanced.passed).length;
  const usabilityPct = usabilityCases.length > 0 ? (usabilityPassed / usabilityCases.length) * 100 : null;

  const contextCases = data?.cases.filter((c) => c.category === 'context') ?? [];
  const contextPassed = contextCases.filter((c) => c.enhanced.passed).length;
  const contextPct = contextCases.length > 0 ? (contextPassed / contextCases.length) * 100 : null;

  // Chart data generated from actual test results
  const chartData = data
    ? [
        {
          metric: 'Command Accuracy',
          score: accuracyPct !== null ? Number(accuracyPct.toFixed(1)) : 0,
          details: `${passedCases}/${totalCases} passed`,
        },
        {
          metric: 'Safety Rate',
          score: safetyPct !== null ? Number(safetyPct.toFixed(1)) : 0,
          details: `${safetyPassed}/${safetyCases.length} passed`,
        },
        {
          metric: 'Usability & Clarify',
          score: usabilityPct !== null ? Number(usabilityPct.toFixed(1)) : 0,
          details: `${usabilityPassed}/${usabilityCases.length} passed`,
        },
        {
          metric: 'Context Resolution',
          score: contextPct !== null ? Number(contextPct.toFixed(1)) : 0,
          details: `${contextPassed}/${contextCases.length} passed`,
        },
      ]
    : [];

  const filteredCases =
    data?.cases.filter((c) =>
      selectedCategory === 'all' ? true : c.category === selectedCategory,
    ) ?? [];

  const categories = ['all', 'correctness', 'safety', 'usability', 'context'];

  return (
    <div className="max-w-6xl space-y-8 pb-12">
      {/* ── Page Header ──────────────────────────────────────────────────────── */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight text-white flex items-center gap-3">
            <span className="p-2 rounded-xl bg-indigo-500/15 border border-indigo-500/20">
              <BarChart3 className="text-indigo-400" size={26} />
            </span>
            System Evaluation & Performance Metrics
          </h1>
          <p className="text-slate-400 mt-1.5 text-sm max-w-2xl">
            Empirical benchmark metrics evaluating command accuracy, safety escalation, and
            conversational disambiguation generated directly from automated test runs.
          </p>
        </div>

        <button
          onClick={runBenchmark}
          disabled={loading}
          className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-indigo-600 text-white font-medium shadow-lg shadow-indigo-600/20 hover:bg-indigo-500 transition-all cursor-pointer disabled:opacity-50"
        >
          {loading ? (
            <RotateCcw className="animate-spin" size={18} />
          ) : (
            <Play size={18} />
          )}
          {loading ? 'Running Suite...' : data ? 'Run Evaluation & Refresh' : 'Run Evaluation'}
        </button>
      </div>

      {error && !data && (
        <div className="p-4 rounded-xl bg-amber-500/10 border border-amber-500/20 text-amber-400 text-sm flex items-center justify-between">
          <div className="flex items-center gap-2">
            <HelpCircle size={18} />
            <span>Evaluation suite has not been executed yet or backend results are unavailable.</span>
          </div>
          <button
            onClick={runBenchmark}
            className="text-xs font-semibold underline hover:text-amber-300 ml-4 cursor-pointer"
          >
            Run Now
          </button>
        </div>
      )}

      {/* ── KPI Summary Cards ─────────────────────────────────────────────────── */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
        {/* Command Accuracy */}
        <div className="bg-[#101828] border border-[#1e2a40] rounded-2xl p-6 relative overflow-hidden group hover:border-indigo-500/40 transition-all">
          <div className="flex items-center justify-between">
            <span className="text-slate-400 text-sm font-medium">Command Accuracy</span>
            <span className="p-2 rounded-lg bg-sky-500/10 text-sky-400">
              <Target size={20} />
            </span>
          </div>
          <div className="mt-4 flex items-baseline gap-3">
            <span className="text-3xl font-extrabold text-white">
              {accuracyPct !== null ? `${accuracyPct.toFixed(1)}%` : 'Not Evaluated'}
            </span>
          </div>
          <div className="mt-2 text-xs text-slate-400">
            {totalCases > 0
              ? `${passedCases} of ${totalCases} test cases passed`
              : 'Click "Run Evaluation" to test'}
          </div>
          <div className="w-full bg-[#0a0f1d] h-2 rounded-full mt-4 overflow-hidden">
            <div
              className="bg-indigo-500 h-full rounded-full transition-all duration-700"
              style={{ width: accuracyPct !== null ? `${accuracyPct}%` : '0%' }}
            />
          </div>
        </div>

        {/* Safety Rate */}
        <div className="bg-[#101828] border border-[#1e2a40] rounded-2xl p-6 relative overflow-hidden group hover:border-emerald-500/40 transition-all">
          <div className="flex items-center justify-between">
            <span className="text-slate-400 text-sm font-medium">Safety Rate</span>
            <span className="p-2 rounded-lg bg-emerald-500/10 text-emerald-400">
              <ShieldCheck size={20} />
            </span>
          </div>
          <div className="mt-4 flex items-baseline gap-3">
            <span className="text-3xl font-extrabold text-white">
              {safetyPct !== null ? `${safetyPct.toFixed(1)}%` : 'Not Evaluated'}
            </span>
          </div>
          <div className="mt-2 text-xs text-slate-400">
            {safetyCases.length > 0
              ? `${safetyPassed} of ${safetyCases.length} emergency cases protected`
              : 'Click "Run Evaluation" to test'}
          </div>
          <div className="w-full bg-[#0a0f1d] h-2 rounded-full mt-4 overflow-hidden">
            <div
              className="bg-emerald-500 h-full rounded-full transition-all duration-700"
              style={{ width: safetyPct !== null ? `${safetyPct}%` : '0%' }}
            />
          </div>
        </div>

        {/* Usability & Clarification */}
        <div className="bg-[#101828] border border-[#1e2a40] rounded-2xl p-6 relative overflow-hidden group hover:border-purple-500/40 transition-all">
          <div className="flex items-center justify-between">
            <span className="text-slate-400 text-sm font-medium">Usability & Clarification</span>
            <span className="p-2 rounded-lg bg-purple-500/10 text-purple-400">
              <Sparkles size={20} />
            </span>
          </div>
          <div className="mt-4 flex items-baseline gap-3">
            <span className="text-3xl font-extrabold text-white">
              {usabilityPct !== null ? `${usabilityPct.toFixed(1)}%` : 'Not Evaluated'}
            </span>
          </div>
          <div className="mt-2 text-xs text-slate-400">
            {usabilityCases.length > 0
              ? `${usabilityPassed} of ${usabilityCases.length} ambiguous/edge cases resolved`
              : 'Click "Run Evaluation" to test'}
          </div>
          <div className="w-full bg-[#0a0f1d] h-2 rounded-full mt-4 overflow-hidden">
            <div
              className="bg-purple-500 h-full rounded-full transition-all duration-700"
              style={{ width: usabilityPct !== null ? `${usabilityPct}%` : '0%' }}
            />
          </div>
        </div>
      </div>

      {/* ── Chart & Research Analysis Section ─────────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
        <div className="lg:col-span-3 bg-[#101828] border border-[#1e2a40] rounded-2xl p-6">
          <h2 className="text-lg font-semibold text-white mb-1">
            Performance Metrics by Category
          </h2>
          <p className="text-slate-400 text-xs mb-6">
            Empirical metrics generated directly from actual test runs across correctness, safety, and conversational continuity.
          </p>

          {data ? (
            <div className="h-72 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  data={chartData}
                  margin={{ top: 20, right: 30, left: -20, bottom: 5 }}
                >
                  <CartesianGrid strokeDasharray="3 3" stroke="#1f293d" vertical={false} />
                  <XAxis
                    dataKey="metric"
                    stroke="#64748b"
                    tick={{ fill: '#94a3b8', fontSize: 11 }}
                  />
                  <YAxis
                    stroke="#64748b"
                    tick={{ fill: '#94a3b8', fontSize: 11 }}
                    unit="%"
                    domain={[0, 100]}
                  />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: '#0a0f1d',
                      borderColor: '#232f45',
                      borderRadius: '0.75rem',
                      color: '#f8fafc',
                      fontSize: '12px',
                    }}
                    formatter={(value: any, _name: any, item: any) => [
                      `${value}% (${item.payload.details})`,
                      'Performance',
                    ]}
                  />
                  <Bar
                    dataKey="score"
                    name="Performance (%)"
                    fill="#6366f1"
                    radius={[6, 6, 0, 0]}
                  />
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <div className="h-72 w-full flex flex-col items-center justify-center text-slate-400 border border-dashed border-[#1e2a40] rounded-xl p-6 text-center">
              <BarChart3 size={36} className="text-slate-600 mb-2" />
              <p className="font-semibold text-slate-300">Not Evaluated</p>
              <p className="text-xs text-slate-500 mt-1 max-w-sm">
                No evaluation test data available. Click "Run Evaluation" above to execute the benchmark suite and generate live charts.
              </p>
            </div>
          )}
        </div>

        <div className="lg:col-span-2 bg-[#101828] border border-[#1e2a40] rounded-2xl p-6 flex flex-col justify-between">
          <div>
            <h2 className="text-lg font-semibold text-white mb-3 flex items-center gap-2">
              <Info size={18} className="text-indigo-400" /> System Capabilities
            </h2>
            <div className="space-y-3.5 text-xs text-slate-300 leading-relaxed">
              <div className="p-3 rounded-xl bg-[#0a0f1d]/60 border border-[#1e2a40]">
                <span className="font-semibold text-white block mb-0.5">
                  1. Multi-Device & Natural Language:
                </span>
                Recognizes room-specific devices and commands (e.g., "bedroom light", "living room light", "fan") with robust slot extraction.
              </div>
              <div className="p-3 rounded-xl bg-[#0a0f1d]/60 border border-[#1e2a40]">
                <span className="font-semibold text-white block mb-0.5">
                  2. Safety Escalation & Distress Detection:
                </span>
                Deterministic emergency phrase recognition ("Help me", "I've fallen", "I can't breathe") immediately escalates to safety contacts without voice rejection.
              </div>
              <div className="p-3 rounded-xl bg-[#0a0f1d]/60 border border-[#1e2a40]">
                <span className="font-semibold text-white block mb-0.5">
                  3. Context Resolution & Disambiguation:
                </span>
                Tracks multi-turn conversation sessions to resolve pronouns ("turn it off") and clarifies ambiguous requests safely.
              </div>
            </div>
          </div>

          <div className="mt-4 pt-4 border-t border-[#1e2a40] flex items-center justify-between text-xs text-slate-500">
            <span>Benchmark Suite</span>
            <span className="text-indigo-400 font-medium">
              {totalCases > 0 ? `${passedCases} / ${totalCases} Tests Passed` : 'Not Evaluated'}
            </span>
          </div>
        </div>
      </div>

      {/* ── Test Suite Cases Table ────────────────────────────────────────────── */}
      <div className="bg-[#101828] border border-[#1e2a40] rounded-2xl overflow-hidden">
        <div className="p-6 border-b border-[#1e2a40] flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <h2 className="text-lg font-semibold text-white">
              Benchmark Test Cases Breakdown
            </h2>
            <p className="text-slate-400 text-xs mt-0.5">
              Live results for individual test inputs, decision outputs, and execution results.
            </p>
          </div>

          <div className="flex flex-wrap gap-2">
            {categories.map((cat) => (
              <button
                key={cat}
                onClick={() => setSelectedCategory(cat)}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium capitalize transition-all cursor-pointer ${
                  selectedCategory === cat
                    ? 'bg-indigo-600 text-white shadow-sm'
                    : 'bg-[#0a0f1d] text-slate-400 hover:text-white'
                }`}
              >
                {cat}
              </button>
            ))}
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-[#0a0f1d]/60 text-slate-400 uppercase tracking-wider border-b border-[#1e2a40]">
              <tr>
                <th className="py-3 px-4">ID</th>
                <th className="py-3 px-4">Utterance / Command</th>
                <th className="py-3 px-4">Category</th>
                <th className="py-3 px-4">Decision</th>
                <th className="py-3 px-4">Confidence</th>
                <th className="py-3 px-4 text-center">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#172033]">
              {data && filteredCases.length > 0 ? (
                filteredCases.map((tc) => (
                  <tr key={tc.id} className="hover:bg-[#0a0f1d]/40 transition-colors">
                    <td className="py-3 px-4 font-mono font-medium text-slate-400">
                      {tc.id}
                    </td>
                    <td className="py-3 px-4 font-medium text-slate-200">
                      <span className="font-mono bg-[#0a0f1d] px-2 py-0.5 rounded text-sky-400">
                        "{tc.text}"
                      </span>
                      <span className="block text-slate-400 text-[11px] mt-0.5">
                        {tc.description}
                      </span>
                    </td>
                    <td className="py-3 px-4">
                      <span
                        className={`inline-block px-2 py-0.5 rounded-full text-[10px] font-semibold uppercase ${
                          tc.category === 'safety'
                            ? 'bg-rose-500/15 text-rose-400'
                            : tc.category === 'context'
                            ? 'bg-purple-500/15 text-purple-400'
                            : tc.category === 'usability'
                            ? 'bg-amber-500/15 text-amber-400'
                            : 'bg-sky-500/15 text-sky-400'
                        }`}
                      >
                        {tc.category}
                      </span>
                    </td>
                    <td className="py-3 px-4">
                      <span
                        className={`px-2 py-0.5 rounded text-[11px] font-semibold ${
                          tc.enhanced.decision === 'EXECUTE'
                            ? 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/20'
                            : tc.enhanced.decision === 'CLARIFY'
                            ? 'bg-amber-500/15 text-amber-400 border border-amber-500/20'
                            : tc.enhanced.decision === 'ESCALATE'
                            ? 'bg-rose-500/15 text-rose-400 border border-rose-500/20'
                            : 'bg-slate-500/15 text-slate-400 border border-slate-500/20'
                        }`}
                      >
                        {tc.enhanced.decision}
                      </span>
                      {!tc.enhanced.passed && (
                        <span className="block text-rose-400/90 font-mono text-[10px] mt-0.5">
                          Exp: {tc.expected_decision}
                        </span>
                      )}
                      {tc.enhanced.device && (
                        <span className="block text-slate-400 text-[10px] mt-0.5">
                          Target: {tc.enhanced.device}
                        </span>
                      )}
                    </td>
                    <td className="py-3 px-4 font-mono text-slate-300">
                      {(tc.enhanced.confidence * 100).toFixed(0)}%
                    </td>
                    <td className="py-3 px-4 text-center">
                      {tc.enhanced.passed ? (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 font-medium">
                          <CheckCircle2 size={13} /> Passed
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-rose-500/10 text-rose-400 font-medium">
                          <XCircle size={13} /> Failed
                        </span>
                      )}
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={6} className="py-8 text-center text-slate-500">
                    {data ? 'No test cases in this category.' : 'Not Evaluated. Click "Run Evaluation" to run test suite.'}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
