/* ── Voice Assistant page with Enrollment & Automatic Speaker Verification ──── */

import { useCallback, useEffect, useRef, useState } from 'react';
import {
  AlertCircle,
  ArrowRight,
  CheckCircle2,
  HelpCircle,
  Lock,
  Mic,
  MicOff,
  RefreshCw,
  Send,
  Shield,
  ShieldAlert,
  ShieldCheck,
  Trash2,
  UserCheck,
  UserPlus,
  Volume2,
  XCircle,
} from 'lucide-react';
import {
  confirmDecision,
  deleteVoiceProfile,
  enrollVoice,
  getEnrollmentStatus,
  processCommand,
  processVoiceAudio,
} from '../api/client';
import type { EnrollmentStatus, VoiceProcessResponse } from '../api/types';
import { AudioRecorder } from '../utils/audioRecorder';

const DECISION_STYLE: Record<
  string,
  { bg: string; border: string; icon: React.ElementType; label: string }
> = {
  EXECUTE: { bg: 'bg-emerald-500/10', border: 'border-emerald-500/30', icon: CheckCircle2, label: 'Executed' },
  CLARIFY: { bg: 'bg-amber-500/10', border: 'border-amber-500/30', icon: HelpCircle, label: 'Clarification Needed' },
  REJECT: { bg: 'bg-rose-500/10', border: 'border-rose-500/30', icon: XCircle, label: 'Rejected' },
  ESCALATE: { bg: 'bg-purple-500/10', border: 'border-purple-500/30', icon: ShieldAlert, label: 'Escalated' },
};

type EnrollmentState =
  | 'idle'
  | 'recording'
  | 'processing'
  | 'success'
  | 'failed';

interface HistoryEntry {
  role: 'user' | 'system';
  text: string;
  response?: VoiceProcessResponse;
  speakerVerified?: boolean | null;
  similarity?: number | null;
}

export default function VoiceAssistant() {
  // ── Enrollment State ───────────────────────────────────────────────────────
  const [enrollmentStatus, setEnrollmentStatus] = useState<EnrollmentStatus | null>(null);
  const [enrollState, setEnrollState] = useState<EnrollmentState>('idle');
  const [enrollMessage, setEnrollMessage] = useState<string>('');
  const [showReEnrollConfirm, setShowReEnrollConfirm] = useState(false);
  const [enrollCountdown, setEnrollCountdown] = useState(0);

  // ── Command Interaction State ──────────────────────────────────────────────
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [commandRecording, setCommandRecording] = useState(false);
  const [commandStatusText, setCommandStatusText] = useState<string>('');
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [pendingClarification, setPendingClarification] = useState(false);
  const [lastInteractionId, setLastInteractionId] = useState<number | null>(null);

  // Recorder references
  const enrollRecorderRef = useRef<AudioRecorder | null>(null);
  const commandRecorderRef = useRef<AudioRecorder | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const countdownIntervalRef = useRef<any>(null);
  const commandTimeoutRef = useRef<any>(null);

  const scrollToBottom = useCallback(() => {
    setTimeout(
      () => scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' }),
      100,
    );
  }, []);

  // Fetch enrollment status on mount
  const loadStatus = useCallback(() => {
    getEnrollmentStatus()
      .then((s) => {
        setEnrollmentStatus(s);
      })
      .catch((err) => {
        setEnrollmentStatus({
          is_enrolled: false,
          similarity_threshold: 0.65,
          message: err.message || 'Unable to check status',
        });
      });
  }, []);

  useEffect(() => {
    loadStatus();
  }, [loadStatus]);

  // Clean up timers on unmount
  useEffect(() => {
    return () => {
      if (countdownIntervalRef.current) clearInterval(countdownIntervalRef.current);
    };
  }, []);

  // ── 1. Voice Enrollment Workflow ───────────────────────────────────────────

  const handleResetProfile = async () => {
    try {
      setEnrollState('processing');
      setEnrollMessage('Resetting voice profile...');
      await deleteVoiceProfile();
      loadStatus();
      setEnrollState('idle');
      setEnrollMessage('Voice profile removed. You can now enroll your voice fresh.');
      setTimeout(() => setEnrollMessage(''), 4000);
    } catch (err: unknown) {
      setEnrollState('failed');
      setEnrollMessage(err instanceof Error ? err.message : 'Failed to reset profile.');
    }
  };

  const startEnrollmentRecording = async (force = false) => {
    if (enrollmentStatus?.is_enrolled && !force) {
      setShowReEnrollConfirm(true);
      return;
    }
    setShowReEnrollConfirm(false);

    try {
      setEnrollState('recording');
      setEnrollMessage('Recording voice sample... Please speak clearly for 4 seconds');
      setEnrollCountdown(4);

      const recorder = new AudioRecorder();
      enrollRecorderRef.current = recorder;
      await recorder.start();

      let timeLeft = 4;
      countdownIntervalRef.current = setInterval(async () => {
        timeLeft -= 1;
        setEnrollCountdown(timeLeft);
        if (timeLeft <= 0) {
          clearInterval(countdownIntervalRef.current);
          await finishEnrollment(recorder, force);
        }
      }, 1000);
    } catch (err: unknown) {
      setEnrollState('failed');
      setEnrollMessage(
        err instanceof Error ? err.message : 'Microphone permission denied or unavailable.',
      );
    }
  };

  const finishEnrollment = async (recorder: AudioRecorder, force: boolean) => {
    try {
      setEnrollState('processing');
      setEnrollMessage('Processing voice sample with Resemblyzer...');

      const audioBlob = await recorder.stop();
      const res = await enrollVoice(audioBlob, force);

      setEnrollState('success');
      setEnrollMessage(res.message || 'Voice enrolled successfully.');
      loadStatus();
      setTimeout(() => {
        setEnrollState('idle');
      }, 4000);
    } catch (err: unknown) {
      setEnrollState('failed');
      setEnrollMessage(err instanceof Error ? err.message : 'Enrollment failed.');
    }
  };

  // ── 2. Automatic Voice Authentication Command Workflow ─────────────────────

  const toggleCommandRecording = async () => {
    if (commandRecording) {
      // User clicked stop recording
      await stopCommandRecording();
    } else {
      // User clicked start recording
      await startCommandRecording();
    }
  };

  const startCommandRecording = async () => {
    try {
      setCommandRecording(true);
      setCommandStatusText('Recording... Speak your command (e.g. "Turn on the fan" or "Help me")');

      const recorder = new AudioRecorder();
      commandRecorderRef.current = recorder;
      await recorder.start();

      // Auto-stop recording after 4.5 seconds if user does not manually stop
      if (commandTimeoutRef.current) clearTimeout(commandTimeoutRef.current);
      commandTimeoutRef.current = setTimeout(() => {
        stopCommandRecording();
      }, 4500);
    } catch (err: unknown) {
      setCommandRecording(false);
      setCommandStatusText(
        err instanceof Error ? err.message : 'Microphone access denied.',
      );
      setTimeout(() => setCommandStatusText(''), 4000);
    }
  };

  const stopCommandRecording = async () => {
    if (commandTimeoutRef.current) {
      clearTimeout(commandTimeoutRef.current);
      commandTimeoutRef.current = null;
    }

    const recorder = commandRecorderRef.current;
    if (!recorder) return;

    setCommandRecording(false);
    setLoading(true);
    setCommandStatusText('Verifying speaker...');

    try {
      const audioBlob = await recorder.stop();
      const resp = await processVoiceAudio(audioBlob, sessionId ?? undefined);

      setSessionId(resp.session_id);
      setLastInteractionId(resp.interaction_id);
      setPendingClarification(resp.decision === 'CLARIFY');

      // Feedback display
      if (resp.decision === 'ESCALATE' || resp.intent === 'EMERGENCY') {
        setCommandStatusText('🚨 Emergency assistance triggered! Emergency contacts notified.');
      } else if (resp.speaker_verified) {
        setCommandStatusText('Voice verified. Processing command.');
      } else {
        setCommandStatusText('Voice not recognized. Command rejected.');
      }

      setHistory((h) => [
        ...h,
        {
          role: 'user',
          text: resp.recognized_text || '[Voice Command]',
          speakerVerified: resp.speaker_verified,
          similarity: resp.speaker_similarity,
        },
        {
          role: 'system',
          text: resp.message,
          response: resp,
          speakerVerified: resp.speaker_verified,
          similarity: resp.speaker_similarity,
        },
      ]);
    } catch (err: unknown) {
      setCommandStatusText('Authentication failed due to a technical error.');
      setHistory((h) => [
        ...h,
        {
          role: 'system',
          text: `Authentication error: ${err instanceof Error ? err.message : 'Technical error'}`,
          speakerVerified: false,
        },
      ]);
    } finally {
      setLoading(false);
      scrollToBottom();
      setTimeout(() => setCommandStatusText(''), 4000);
    }
  };

  // ── 3. Text Command Submission ─────────────────────────────────────────────

  const handleTextSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || loading) return;

    const text = input.trim();
    setInput('');
    setHistory((h) => [...h, { role: 'user', text }]);
    setLoading(true);

    try {
      let resp: VoiceProcessResponse;

      if (pendingClarification && sessionId) {
        resp = await confirmDecision({
          session_id: sessionId,
          response: text,
          interaction_id: lastInteractionId ?? undefined,
        });
      } else {
        resp = await processCommand({
          text,
          input_mode: 'text',
          session_id: sessionId ?? undefined,
        });
      }

      setSessionId(resp.session_id);
      setLastInteractionId(resp.interaction_id);
      setPendingClarification(resp.decision === 'CLARIFY');

      setHistory((h) => [
        ...h,
        {
          role: 'system',
          text: resp.message,
          response: resp,
          speakerVerified: resp.speaker_verified,
        },
      ]);
    } catch (err: unknown) {
      setHistory((h) => [
        ...h,
        { role: 'system', text: `Error: ${err instanceof Error ? err.message : 'Unknown error'}` },
      ]);
    } finally {
      setLoading(false);
      scrollToBottom();
    }
  };

  return (
    <div className="max-w-4xl mx-auto flex flex-col h-[calc(100vh-3.5rem)] space-y-4">
      {/* ── Top Header ──────────────────────────────────────────────────────── */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-2 border-b border-[#1b253b]">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2">
            <Mic size={24} className="text-indigo-400" /> Voice Assistant & Verification
          </h1>
          <p className="text-slate-400 text-xs">
            Reliability-aware voice system with backend speaker authentication.
          </p>
        </div>

        <div className="flex items-center gap-2">
          {sessionId && (
            <span className="px-2.5 py-1 rounded-lg bg-[#0e1627] border border-[#1e2a40] text-xs font-mono text-slate-400">
              Session: {sessionId.slice(0, 8)}…
            </span>
          )}
          <button
            onClick={loadStatus}
            className="p-1.5 rounded-lg bg-[#0e1627] hover:bg-[#162035] text-slate-400 hover:text-white border border-[#1e2a40] transition-colors"
            title="Refresh status"
          >
            <RefreshCw size={14} />
          </button>
        </div>
      </div>

      {/* ── Section 1: Voice Enrollment Card ─────────────────────────────────── */}
      <div className="bg-[#101828] border border-[#1e2a40] rounded-2xl p-4 shadow-sm">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <div
              className={`w-10 h-10 rounded-xl flex items-center justify-center ${
                enrollmentStatus?.is_enrolled
                  ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
                  : 'bg-amber-500/20 text-amber-400 border border-amber-500/30'
              }`}
            >
              {enrollmentStatus?.is_enrolled ? <ShieldCheck size={20} /> : <ShieldAlert size={20} />}
            </div>

            <div>
              <div className="flex items-center gap-2">
                <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                  Voice Profile Status:
                </span>
                <span
                  className={`text-xs font-bold px-2 py-0.5 rounded-full ${
                    enrollmentStatus?.is_enrolled
                      ? 'bg-emerald-500/15 text-emerald-400'
                      : 'bg-amber-500/15 text-amber-400'
                  }`}
                >
                  {enrollmentStatus?.is_enrolled ? 'Enrolled' : 'Not Enrolled'}
                </span>
                <span className="text-[11px] text-slate-500 font-mono">
                  (Threshold: {enrollmentStatus?.similarity_threshold ?? 0.65})
                </span>
              </div>

              <p className="text-xs text-slate-300 mt-0.5">
                {enrollmentStatus?.is_enrolled
                  ? 'Enrolled speaker profile active. Every command is automatically authenticated.'
                  : 'No profile found. Commands are strictly blocked until voice enrollment.'}
              </p>
            </div>
          </div>

          {/* Action button */}
          <div className="flex items-center gap-2">
            {enrollState === 'recording' ? (
              <div className="flex items-center gap-2 px-4 py-2 rounded-xl bg-rose-600 text-white font-semibold text-xs animate-pulse">
                <span className="w-2 h-2 rounded-full bg-white animate-ping" />
                Recording sample ({enrollCountdown}s)…
              </div>
            ) : enrollState === 'processing' ? (
              <div className="flex items-center gap-2 px-4 py-2 rounded-xl bg-indigo-600/30 text-indigo-300 border border-indigo-500/40 font-semibold text-xs animate-pulse">
                <RefreshCw size={14} className="animate-spin" />
                Processing profile…
              </div>
            ) : (
              <div className="flex items-center gap-2">
                <button
                  onClick={() => startEnrollmentRecording(false)}
                  className={`px-4 py-2 rounded-xl text-xs font-semibold flex items-center gap-2 transition-all cursor-pointer ${
                    enrollmentStatus?.is_enrolled
                      ? 'bg-[#182338] hover:bg-[#202e48] text-slate-200 border border-[#23324d]'
                      : 'bg-gradient-to-r from-indigo-600 to-indigo-700 hover:from-indigo-500 hover:to-indigo-600 text-white shadow-lg shadow-indigo-600/30'
                  }`}
                >
                  {enrollmentStatus?.is_enrolled ? (
                    <>
                      <RefreshCw size={14} /> Re-enroll Voice
                    </>
                  ) : (
                    <>
                      <UserPlus size={14} /> Enroll Voice
                    </>
                  )}
                </button>
                {enrollmentStatus?.is_enrolled && (
                  <button
                    onClick={handleResetProfile}
                    className="px-3 py-2 rounded-xl text-xs font-semibold flex items-center gap-1.5 bg-rose-500/10 hover:bg-rose-500/20 text-rose-300 border border-rose-500/30 transition-all cursor-pointer"
                    title="Remove enrolled voice profile"
                  >
                    <Trash2 size={13} /> Reset
                  </button>
                )}
              </div>
            )}
          </div>
        </div>

        {/* Re-enrollment Confirmation Modal / Dialog */}
        {showReEnrollConfirm && (
          <div className="mt-3 p-3.5 rounded-xl bg-amber-500/10 border border-amber-500/30 text-amber-200 text-xs animate-fade-in flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <AlertCircle size={16} className="text-amber-400 flex-shrink-0" />
              <span>
                <strong>Authorized Re-enrollment:</strong> An enrolled profile exists. Replacing it will
                update the baseline embedding. Proceed?
              </span>
            </div>
            <div className="flex items-center gap-2 flex-shrink-0">
              <button
                onClick={() => startEnrollmentRecording(true)}
                className="px-3 py-1.5 rounded-lg bg-amber-600 hover:bg-amber-500 text-white font-semibold text-xs cursor-pointer"
              >
                Confirm Replacement
              </button>
              <button
                onClick={() => setShowReEnrollConfirm(false)}
                className="px-3 py-1.5 rounded-lg bg-[#162033] hover:bg-[#1d2b42] text-slate-300 text-xs cursor-pointer"
              >
                Cancel
              </button>
            </div>
          </div>
        )}

        {/* Feedback message banner */}
        {enrollMessage && (
          <div
            className={`mt-3 p-2.5 rounded-xl text-xs flex items-center gap-2 animate-fade-in ${
              enrollState === 'success'
                ? 'bg-emerald-500/15 border border-emerald-500/30 text-emerald-300'
                : enrollState === 'failed'
                ? 'bg-rose-500/15 border border-rose-500/30 text-rose-300'
                : 'bg-indigo-500/15 border border-indigo-500/30 text-indigo-300'
            }`}
          >
            {enrollState === 'success' ? (
              <CheckCircle2 size={15} />
            ) : enrollState === 'failed' ? (
              <XCircle size={15} />
            ) : (
              <RefreshCw size={14} className="animate-spin" />
            )}
            <span>{enrollMessage}</span>
          </div>
        )}
      </div>

      {/* ── Section 2: Conversational Stream & Responses ─────────────────────── */}
      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto space-y-3 pr-2 bg-[#0a0f1d]/60 rounded-2xl p-4 border border-[#182337]"
      >
        {history.length === 0 && (
          <div className="text-center py-12 text-slate-500 space-y-3">
            <div className="w-16 h-16 rounded-full bg-indigo-600/10 border border-indigo-500/20 flex items-center justify-center mx-auto text-indigo-400">
              <Shield size={32} />
            </div>
            <div>
              <p className="text-base font-semibold text-slate-300">Voice Authentication Active</p>
              <p className="text-xs text-slate-500 max-w-md mx-auto mt-1">
                Speak a command below. The backend extracts your 256-dim embedding, computes cosine
                similarity, and enforces authentication before executing any device command.
              </p>
            </div>
            <div className="flex flex-wrap gap-2 justify-center text-xs text-slate-400 pt-2">
              <span className="px-3 py-1 rounded-full bg-[#101828] border border-[#1e2a40]">
                "Turn on the bedroom light"
              </span>
              <span className="px-3 py-1 rounded-full bg-[#101828] border border-[#1e2a40]">
                "Turn off the fan"
              </span>
              <span className="px-3 py-1 rounded-full bg-[#101828] border border-[#1e2a40]">
                "Turn it off" (Context)
              </span>
              <span className="px-3 py-1 rounded-full bg-[#101828] border border-[#1e2a40]">
                "Help me" (Emergency)
              </span>
            </div>
          </div>
        )}

        {history.map((entry, idx) => (
          <div
            key={idx}
            className={`animate-fade-in ${entry.role === 'user' ? 'flex justify-end' : 'flex justify-start'}`}
          >
            {entry.role === 'user' ? (
              <div className="bg-gradient-to-r from-indigo-600/20 to-indigo-700/20 text-indigo-200 border border-indigo-500/30 rounded-2xl rounded-br-sm px-4 py-3 max-w-md shadow-sm">
                <div className="flex items-center justify-between text-[11px] text-indigo-400 mb-1 gap-4">
                  <span className="flex items-center gap-1 font-semibold">
                    <UserCheck size={12} /> You (Speaker)
                  </span>
                  {entry.speakerVerified !== undefined && (
                    <span
                      className={`px-1.5 py-0.2 rounded font-mono text-[10px] ${
                        entry.speakerVerified
                          ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
                          : 'bg-rose-500/20 text-rose-300 border border-rose-500/30'
                      }`}
                    >
                      {entry.speakerVerified ? '✓ Verified' : '✕ Unauthenticated'}
                      {entry.similarity != null && ` (${entry.similarity.toFixed(2)})`}
                    </span>
                  )}
                </div>
                <p className="text-sm font-medium text-white">{entry.text}</p>
              </div>
            ) : (
              <ResponseBubble entry={entry} />
            )}
          </div>
        ))}

        {loading && (
          <div className="flex items-center gap-2 px-4 py-3 bg-[#101828] border border-[#1e2a40] rounded-xl w-fit text-xs text-indigo-300 animate-fade-in">
            <span className="w-2 h-2 bg-indigo-400 rounded-full animate-ping" />
            <span>{commandStatusText || 'Verifying speaker and processing command...'}</span>
          </div>
        )}
      </div>

      {/* ── Section 3: Voice Command Controls & Input Bar ───────────────────── */}
      <div className="space-y-2">
        {/* Real-time status banner */}
        {commandStatusText && (
          <div
            className={`p-2.5 rounded-xl text-xs flex items-center justify-between animate-fade-in ${
              commandStatusText.includes('verified')
                ? 'bg-emerald-500/15 border border-emerald-500/30 text-emerald-300'
                : commandStatusText.includes('rejected') || commandStatusText.includes('not enrolled')
                ? 'bg-rose-500/15 border border-rose-500/30 text-rose-300'
                : 'bg-indigo-500/15 border border-indigo-500/30 text-indigo-300'
            }`}
          >
            <div className="flex items-center gap-2">
              <Volume2 size={15} />
              <span>{commandStatusText}</span>
            </div>
            {commandRecording && (
              <span className="text-[10px] uppercase font-bold tracking-wider text-rose-400 animate-pulse">
                LIVE RECORDING
              </span>
            )}
          </div>
        )}

        <div className="flex gap-2 bg-[#101828] border border-[#1e2a40] rounded-2xl p-2 items-center shadow-lg">
          {/* Live Mic Button for Voice Authentication */}
          <button
            type="button"
            onClick={toggleCommandRecording}
            disabled={loading}
            className={`p-3 rounded-xl transition-all flex items-center justify-center cursor-pointer ${
              commandRecording
                ? 'bg-rose-600 hover:bg-rose-700 text-white shadow-lg shadow-rose-900/50 animate-pulse'
                : 'bg-indigo-600 hover:bg-indigo-500 text-white shadow-lg shadow-indigo-900/40'
            } disabled:opacity-40`}
            title={commandRecording ? 'Click to stop & verify command' : 'Click to speak command'}
          >
            {commandRecording ? <MicOff size={20} /> : <Mic size={20} />}
          </button>

          {/* Fallback Text Input */}
          <form onSubmit={handleTextSubmit} className="flex-1 flex gap-2">
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder={
                pendingClarification
                  ? 'Answer clarification question…'
                  : commandRecording
                  ? 'Listening to microphone… click red mic when finished speaking'
                  : 'Speak with mic or type a command…'
              }
              className="flex-1 bg-transparent px-3 py-2 text-sm text-white placeholder-slate-500 outline-none"
              disabled={loading || commandRecording}
            />
            <button
              type="submit"
              disabled={loading || !input.trim() || commandRecording}
              className="bg-[#1b273d] hover:bg-indigo-600 disabled:opacity-30 text-slate-200 hover:text-white font-semibold px-4 py-2 rounded-xl text-sm transition-colors flex items-center gap-1.5 cursor-pointer"
            >
              <Send size={15} />
              <span className="hidden sm:inline">Send</span>
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}

/* ── System response bubble ───────────────────────────────────────────────── */

function ResponseBubble({ entry }: { entry: HistoryEntry }) {
  const resp = entry.response;
  const style = resp ? DECISION_STYLE[resp.decision] : null;
  const Icon = style?.icon ?? ArrowRight;

  return (
    <div
      className={`rounded-2xl rounded-bl-sm px-4 py-3.5 max-w-lg border ${
        style ? `${style.bg} ${style.border}` : 'bg-[#101828] border-[#1e2a40]'
      }`}
    >
      {/* Decision badge and authentication tag */}
      <div className="flex items-center justify-between gap-2 mb-2">
        {style && (
          <div className="flex items-center gap-1.5">
            <Icon size={14} />
            <span className="text-xs font-bold uppercase tracking-wide">{style.label}</span>
          </div>
        )}

        {resp?.speaker_verified !== undefined && (
          <span
            className={`text-[10px] font-mono px-2 py-0.5 rounded-full flex items-center gap-1 ${
              resp.speaker_verified
                ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
                : 'bg-rose-500/20 text-rose-300 border border-rose-500/30'
            }`}
          >
            {resp.speaker_verified ? <ShieldCheck size={11} /> : <Lock size={11} />}
            {resp.speaker_verified ? 'Speaker Verified' : 'Access Denied'}
            {resp.speaker_similarity != null && ` (${resp.speaker_similarity.toFixed(2)})`}
          </span>
        )}
      </div>

      <p className="text-sm text-slate-100">{entry.text}</p>

      {/* Feature 4 & 5: Ambiguity, Indirect, & SLM Badges */}
      {(resp?.is_ambiguous || resp?.structured_intent?.is_ambiguous || resp?.structured_intent?.is_indirect || resp?.slm_proposal) && (
        <div className="flex flex-wrap gap-1.5 mt-2">
          {(resp?.is_ambiguous || resp?.structured_intent?.is_ambiguous) && (
            <span className="px-2 py-0.5 rounded-md text-[10px] font-semibold bg-amber-500/15 text-amber-300 border border-amber-500/30 flex items-center gap-1">
              <HelpCircle size={10} /> Ambiguous Command
            </span>
          )}
          {resp?.structured_intent?.is_indirect && (
            <span className="px-2 py-0.5 rounded-md text-[10px] font-semibold bg-sky-500/15 text-sky-300 border border-sky-500/30 flex items-center gap-1">
              💬 Indirect Statement
            </span>
          )}
          {resp?.slm_proposal && (
            <span className="px-2 py-0.5 rounded-md text-[10px] font-semibold bg-indigo-500/15 text-indigo-300 border border-indigo-500/30 flex items-center gap-1">
              🧠 SLM Context Assessed
            </span>
          )}
        </div>
      )}

      {/* Structured Details */}
      {resp && (
        <div className="mt-3 space-y-1.5 text-xs text-slate-300 border-t border-[#1e2a40] pt-2 font-sans">
          {resp.intent && (
            <p className="flex justify-between">
              <span className="text-slate-400">Intent:</span>
              <span className="font-mono text-indigo-300">
                {resp.intent}
                {resp.intent_confidence != null &&
                  ` (${(resp.intent_confidence * 100).toFixed(0)}%)`}
              </span>
            </p>
          )}
          {resp.target_device && (
            <p className="flex justify-between">
              <span className="text-slate-400">Target Device:</span>
              <span className="font-mono text-sky-300">{resp.target_device}</span>
            </p>
          )}
          {resp.requested_action && (
            <p className="flex justify-between">
              <span className="text-slate-400">Action:</span>
              <span className="font-mono text-emerald-400 font-bold">{resp.requested_action}</span>
            </p>
          )}
          {resp.structured_intent?.suggested_action && (
            <p className="flex justify-between text-amber-300">
              <span className="text-slate-400">Suggested Action:</span>
              <span className="font-mono font-medium">
                {resp.structured_intent.suggested_action}{' '}
                {resp.structured_intent.suggested_device ? `(${resp.structured_intent.suggested_device})` : ''}
              </span>
            </p>
          )}
          {resp.decision_reason && (
            <p className="text-[11px] text-slate-400 mt-1 italic">
              ↳ {resp.decision_reason}
            </p>
          )}
        </div>
      )}

      {/* Clarification prompt */}
      {(resp?.clarification_question || resp?.structured_intent?.clarification_prompt) && (
        <div className="mt-3 p-3 rounded-xl bg-amber-500/15 border border-amber-500/30 text-xs font-medium text-amber-200 space-y-1.5">
          <div className="flex items-center gap-1.5 font-bold uppercase tracking-wider text-[10px] text-amber-400">
            <HelpCircle size={13} className="flex-shrink-0" />
            <span>Clarification Required</span>
          </div>
          <p className="text-sm text-amber-100 font-semibold">
            {resp.clarification_question || resp?.structured_intent?.clarification_prompt}
          </p>
          <p className="text-[11px] text-amber-300/70">
            Please speak or type your answer to clarify.
          </p>
        </div>
      )}
    </div>
  );
}
