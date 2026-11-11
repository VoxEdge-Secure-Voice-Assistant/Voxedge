/* ── Dashboard page matching exact VoxEdge UI design ───────────────────────── */

import { useEffect, useState, useCallback, useRef } from 'react';
import { Link } from 'react-router-dom';
import {
  Mic,
  Monitor,
  CheckCircle2,
  Calendar,
  Bell,
  ChevronRight,
  ShieldCheck,
  AlertTriangle,
  Lightbulb,
  Fan,
  FileText,
  Send,
  PhoneCall,
  ListOrdered,
  Sliders,
  Sparkles,
} from 'lucide-react';
import {
  getActivity,
  getSystemStatus,
  listDevices,
  commandDevice,
  processCommand,
  processVoiceAudio,
  triggerEmergency,
} from '../api/client';
import type { ActivityResponse, Device, SystemStatus, VoiceProcessResponse } from '../api/types';
import { AudioRecorder } from '../utils/audioRecorder';

export default function Dashboard() {
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [devices, setDevices] = useState<Device[]>([]);
  const [activity, setActivity] = useState<ActivityResponse | null>(null);
  const [deviceLoading, setDeviceLoading] = useState<string | null>(null);

  // Interaction State (Voice / Text)
  const [inputMode, setInputMode] = useState<'voice' | 'text'>('voice');
  const [textInput, setTextInput] = useState('');
  const [isListening, setIsListening] = useState(false);
  const [listeningFeedback, setListeningFeedback] = useState<string | null>(null);
  const [isProcessing, setIsProcessing] = useState(false);

  // Last Command and Decision state
  const [lastCommand, setLastCommand] = useState({
    text: 'Turn on the bedroom light',
    time: '10:41 AM',
    intent: 'CONTROL_DEVICE',
    device: 'bedroom_light',
    action: 'ON',
    confidence: 0.92,
  });

  const [decisionResult, setDecisionResult] = useState({
    outcome: 'EXECUTE',
    title: 'Valid command. Executing now.',
    reason: 'Clear intent, supported device, and authorized action.',
    status: 'Success',
    message: 'Bedroom light turned ON.',
    time: '10:41 AM',
  });

  // Emergency trigger feedback state
  const [emergencyAlertActive, setEmergencyAlertActive] = useState(false);
  const [emergencyFeedback, setEmergencyFeedback] = useState<string | null>(null);

  // Live time state
  const [currentTime, setCurrentTime] = useState(() => ({
    date: new Date().toLocaleDateString('en-US', { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' }),
    time: new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' }),
  }));

  // Audio Recorder Reference for speaker authentication
  const audioRecorderRef = useRef<AudioRecorder | null>(null);

  // Fetch initial data
  const loadData = useCallback(() => {
    getSystemStatus()
      .then((s) => {
        setStatus(s);
        if (s.active_emergencies > 0) {
          setEmergencyAlertActive(true);
        }
      })
      .catch((err) => console.error('Status fetch error:', err));

    listDevices()
      .then((d) => setDevices(d.devices))
      .catch((err) => console.error('Devices fetch error:', err));

    getActivity(10)
      .then((a) => setActivity(a))
      .catch((err) => console.error('Activity fetch error:', err));
  }, []);

  useEffect(() => {
    loadData();
    const interval = setInterval(() => {
      setCurrentTime({
        date: new Date().toLocaleDateString('en-US', { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' }),
        time: new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' }),
      });
    }, 10000);
    return () => clearInterval(interval);
  }, [loadData]);

  // Execute command pipeline
  const handleExecute = async (commandText: string) => {
    if (!commandText.trim()) return;
    setIsProcessing(true);
    const nowTime = new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });

    try {
      const res: VoiceProcessResponse = await processCommand({
        text: commandText,
        input_mode: inputMode,
      });

      setLastCommand({
        text: res.recognized_text,
        time: nowTime,
        intent: res.intent || 'UNKNOWN',
        device: res.target_device || (res.entities?.device as string) || 'none',
        action: res.requested_action || (res.entities?.action as string) || 'none',
        confidence: res.intent_confidence ?? 0.85,
      });

      const isEmergency = res.decision === 'ESCALATE' || res.intent === 'EMERGENCY';
      setDecisionResult({
        outcome: res.decision,
        title:
          isEmergency
            ? '🚨 Emergency Assistance Triggered'
            : res.decision === 'EXECUTE'
            ? 'Valid command. Executing now.'
            : res.decision === 'CLARIFY'
            ? res.clarification_question || 'Clarification needed.'
            : 'Command safely rejected.',
        reason: res.decision_reason,
        status: isEmergency ? 'Escalated' : res.decision === 'EXECUTE' ? 'Success' : res.decision,
        message: res.message,
        time: nowTime,
      });

      if (isEmergency) {
        setListeningFeedback('🚨 Emergency detected: Notifying emergency contacts.');
        setEmergencyAlertActive(true);
      }

      loadData();
    } catch (err: any) {
      setDecisionResult({
        outcome: 'REJECT',
        title: 'Network or processing error',
        reason: err.message || 'Failed to reach backend',
        status: 'Error',
        message: 'Could not process command',
        time: nowTime,
      });
    } finally {
      setIsProcessing(false);
      setTextInput('');
    }
  };

  // Automatic Voice Authentication Recording
  const toggleVoiceRecording = async () => {
    if (isListening) {
      // User clicked to stop and verify
      setIsListening(false);
      setListeningFeedback('Verifying speaker...');
      setIsProcessing(true);
      const nowTime = new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });

      try {
        const recorder = audioRecorderRef.current;
        if (!recorder) return;
        const audioBlob = await recorder.stop();
        const res = await processVoiceAudio(audioBlob);

        setLastCommand({
          text: res.recognized_text || '[Voice command]',
          time: nowTime,
          intent: res.intent || 'UNKNOWN',
          device: res.target_device || (res.entities?.device as string) || 'none',
          action: res.requested_action || (res.entities?.action as string) || 'none',
          confidence: res.speaker_similarity ?? 0.85,
        });

        const isEmergency = res.decision === 'ESCALATE' || res.intent === 'EMERGENCY';

        setDecisionResult({
          outcome: res.decision,
          title: isEmergency
            ? '🚨 Emergency Assistance Triggered'
            : res.speaker_verified
            ? 'Voice verified. Executing command.'
            : 'Voice verification rejected.',
          reason: res.decision_reason,
          status: isEmergency
            ? 'Escalated'
            : res.speaker_verified
            ? 'Verified'
            : 'Access Denied',
          message: res.message,
          time: nowTime,
        });

        if (isEmergency) {
          setListeningFeedback('🚨 Emergency detected: Notifying emergency contacts.');
          setEmergencyAlertActive(true);
        } else if (res.speaker_verified) {
          setListeningFeedback('Voice verified. Processing command.');
        } else {
          setListeningFeedback(res.message);
        }

        loadData();
      } catch (err: any) {
        setListeningFeedback('Authentication failed due to a technical error.');
        setDecisionResult({
          outcome: 'REJECT',
          title: 'Authentication Error',
          reason: err.message || 'Technical failure',
          status: 'Failed',
          message: 'Voice verification could not be completed.',
          time: nowTime,
        });
      } finally {
        setIsProcessing(false);
        setTimeout(() => setListeningFeedback(null), 4000);
      }
      return;
    }

    // Start recording
    try {
      const recorder = new AudioRecorder();
      audioRecorderRef.current = recorder;
      await recorder.start();
      setIsListening(true);
      setListeningFeedback('Listening... Speak your command now. Click mic again when done.');
    } catch (err: any) {
      setIsListening(false);
      setListeningFeedback(`Microphone error: ${err.message || 'Permission denied'}`);
      setTimeout(() => setListeningFeedback(null), 3500);
    }
  };

  // Toggle device state
  const handleToggleDevice = async (device: Device) => {
    setDeviceLoading(device.id);
    const newAction = device.state === 'ON' ? 'OFF' : 'ON';
    try {
      await commandDevice(device.id, newAction);
      loadData();
    } catch (err: any) {
      setListeningFeedback(
        err?.message?.includes('Authentication required') || err?.message?.includes('401')
          ? 'Voice authentication required. Use the microphone to verify your voice before controlling devices.'
          : err?.message || 'Failed to toggle device'
      );
      setTimeout(() => setListeningFeedback(null), 4000);
    } finally {
      setDeviceLoading(null);
    }
  };

  // Trigger Emergency
  const handleTriggerEmergency = async () => {
    try {
      await triggerEmergency('Emergency trigger button pressed from dashboard', 'CRITICAL');
      setEmergencyAlertActive(true);
      setEmergencyFeedback('Emergency Alert Dispatched! Simulated notifications sent to Caregiver & EMS.');
      loadData();
      setTimeout(() => setEmergencyFeedback(null), 6000);
    } catch (err: any) {
      setEmergencyFeedback(err.message || 'Failed to dispatch emergency');
    }
  };

  return (
    <div className="space-y-6 max-w-7xl pb-10">
      {/* ── Top Header Section ─────────────────────────────────────────────── */}
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-extrabold text-white tracking-tight flex items-center gap-2">
            Welcome to <span className="text-indigo-400">VoxEdge</span>
          </h1>
          <p className="text-slate-400 text-sm mt-1">
            A reliability-aware voice-based assistive system for elderly and bedridden users.
          </p>
        </div>

        {/* Right Status Badges & Time Card */}
        <div className="flex flex-wrap items-center gap-3">
          {/* System Online badge */}
          <div className="flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-[#131d31] border border-[#1e2a40] text-xs font-medium text-slate-300">
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
            System Online
          </div>

          {/* Notification bell */}
          <button
            onClick={() => alert('Notifications: All system services operational. No pending alerts.')}
            className="p-2.5 rounded-full bg-[#131d31] border border-[#1e2a40] text-slate-300 hover:text-white hover:border-indigo-500/40 transition-colors cursor-pointer relative"
          >
            <Bell size={16} />
            <span className="absolute top-1.5 right-1.5 w-1.5 h-1.5 bg-indigo-400 rounded-full" />
          </button>

          {/* User profile */}
          <div className="flex items-center gap-2.5 px-3 py-1.5 rounded-full bg-[#131d31] border border-[#1e2a40] text-xs font-semibold text-white">
            <span className="w-6 h-6 rounded-full bg-indigo-600 flex items-center justify-center text-[11px] font-bold">
              U
            </span>
            User
          </div>

          {/* Date & Time Widget */}
          <div className="flex items-center gap-2.5 px-4 py-2 rounded-xl bg-[#131d31] border border-[#1e2a40] text-xs text-slate-200 shadow-sm">
            <Calendar size={16} className="text-indigo-400" />
            <div className="text-right">
              <span className="block font-medium">{currentTime.date}</span>
              <span className="block text-[11px] text-slate-400 font-mono">{currentTime.time}</span>
            </div>
          </div>
        </div>
      </div>

      {emergencyFeedback && (
        <div className="p-4 rounded-xl bg-rose-500/15 border border-rose-500/30 text-rose-300 text-sm flex items-center gap-3 animate-fade-in">
          <AlertTriangle size={18} className="text-rose-400 flex-shrink-0" />
          <span>{emergencyFeedback}</span>
        </div>
      )}

      {/* ── Top 4 KPI Quick Cards ─────────────────────────────────────────── */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Card 1: Voice Assistant */}
        <Link
          to="/voice"
          className="bg-[#101828] border border-[#1e2a40] hover:border-indigo-500/50 rounded-2xl p-4 flex items-center justify-between transition-all group cursor-pointer shadow-sm"
        >
          <div className="flex items-center gap-3.5">
            <div className="w-11 h-11 rounded-full bg-indigo-600/20 border border-indigo-500/30 flex items-center justify-center text-indigo-400 group-hover:bg-indigo-600 group-hover:text-white transition-colors">
              <Mic size={20} />
            </div>
            <div>
              <p className="text-sm font-semibold text-white">Voice Assistant</p>
              <div className="flex items-center gap-1.5 mt-0.5">
                <span className={`w-2 h-2 rounded-full ${status?.voice_enrolled ? 'bg-emerald-400' : 'bg-amber-400 animate-pulse'}`} />
                <span className="text-xs text-slate-400">
                  {status?.voice_enrolled ? 'Enrolled & Active' : 'Enrollment Required'}
                </span>
              </div>
            </div>
          </div>
          <ChevronRight size={18} className="text-slate-500 group-hover:text-indigo-400 group-hover:translate-x-0.5 transition-all" />
        </Link>

        {/* Card 2: Devices Online */}
        <Link
          to="/devices"
          className="bg-[#101828] border border-[#1e2a40] hover:border-sky-500/50 rounded-2xl p-4 flex items-center justify-between transition-all group cursor-pointer shadow-sm"
        >
          <div className="flex items-center gap-3.5">
            <div className="w-11 h-11 rounded-full bg-sky-600/20 border border-sky-500/30 flex items-center justify-center text-sky-400 group-hover:bg-sky-600 group-hover:text-white transition-colors">
              <Sliders size={20} />
            </div>
            <div>
              <p className="text-sm font-semibold text-white">Devices Online</p>
              <div className="flex items-center gap-1.5 mt-0.5">
                <span className="w-2 h-2 rounded-full bg-emerald-400" />
                <span className="text-xs text-slate-400">
                  {status ? `${status.active_devices} / ${status.total_devices}` : '3 / 3'}
                </span>
              </div>
            </div>
          </div>
          <ChevronRight size={18} className="text-slate-500 group-hover:text-sky-400 group-hover:translate-x-0.5 transition-all" />
        </Link>

        {/* Card 3: System Status */}
        <div className="bg-[#101828] border border-[#1e2a40] rounded-2xl p-4 flex items-center justify-between transition-all shadow-sm">
          <div className="flex items-center gap-3.5">
            <div className="w-11 h-11 rounded-full bg-emerald-600/20 border border-emerald-500/30 flex items-center justify-center text-emerald-400">
              <ShieldCheck size={20} />
            </div>
            <div>
              <p className="text-sm font-semibold text-white">System Status</p>
              <div className="flex items-center gap-1.5 mt-0.5">
                <span className="w-2 h-2 rounded-full bg-emerald-400" />
                <span className="text-xs text-slate-400">All Systems Normal</span>
              </div>
            </div>
          </div>
          <ChevronRight size={18} className="text-slate-500" />
        </div>

        {/* Card 4: Emergency */}
        <Link
          to="/emergency"
          className={`border rounded-2xl p-4 flex items-center justify-between transition-all group cursor-pointer shadow-sm ${
            emergencyAlertActive
              ? 'bg-rose-950/40 border-rose-500/60 hover:border-rose-400'
              : 'bg-[#101828] border-[#1e2a40] hover:border-rose-500/50'
          }`}
        >
          <div className="flex items-center gap-3.5">
            <div
              className={`w-11 h-11 rounded-full flex items-center justify-center transition-colors ${
                emergencyAlertActive
                  ? 'bg-rose-600 text-white animate-pulse'
                  : 'bg-rose-600/20 border border-rose-500/30 text-rose-400 group-hover:bg-rose-600 group-hover:text-white'
              }`}
            >
              <AlertTriangle size={20} />
            </div>
            <div>
              <p className="text-sm font-semibold text-white">Emergency</p>
              <div className="flex items-center gap-1.5 mt-0.5">
                <span
                  className={`w-2 h-2 rounded-full ${
                    emergencyAlertActive ? 'bg-rose-500 animate-ping' : 'bg-emerald-400'
                  }`}
                />
                <span className="text-xs text-slate-400">
                  {emergencyAlertActive ? 'Active Emergency' : 'No Active Alerts'}
                </span>
              </div>
            </div>
          </div>
          <ChevronRight size={18} className="text-slate-500 group-hover:text-rose-400 group-hover:translate-x-0.5 transition-all" />
        </Link>
      </div>

      {/* ── Middle Row 3 Columns (Core Interaction Center) ────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
        {/* Column 1: Voice Assistant (4 cols) */}
        <div className="lg:col-span-4 bg-[#101828] border border-[#1e2a40] rounded-2xl p-5 flex flex-col justify-between shadow-sm">
          <div>
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-sm font-semibold text-white flex items-center gap-2">
                <Mic size={16} className="text-indigo-400" /> Voice Assistant
              </h2>

              {/* Tabs */}
              <div className="flex items-center bg-[#0a0f1d] p-1 rounded-xl border border-[#1b253b]">
                <button
                  onClick={() => setInputMode('voice')}
                  className={`px-3 py-1 rounded-lg text-xs font-medium transition-all cursor-pointer ${
                    inputMode === 'voice'
                      ? 'bg-indigo-600 text-white shadow-sm'
                      : 'text-slate-400 hover:text-white'
                  }`}
                >
                  Voice Input
                </button>
                <button
                  onClick={() => setInputMode('text')}
                  className={`px-3 py-1 rounded-lg text-xs font-medium transition-all cursor-pointer ${
                    inputMode === 'text'
                      ? 'bg-indigo-600 text-white shadow-sm'
                      : 'text-slate-400 hover:text-white'
                  }`}
                >
                  Text Input
                </button>
              </div>
            </div>

            {/* Voice Input Mode */}
            {inputMode === 'voice' ? (
              <div className="py-6 flex flex-col items-center justify-center text-center">
                {/* Glowing Mic Button */}
                <button
                  onClick={toggleVoiceRecording}
                  disabled={isProcessing}
                  className={`w-28 h-28 rounded-full flex items-center justify-center transition-all cursor-pointer shadow-xl relative ${
                    isListening
                      ? 'bg-indigo-600 text-white ring-8 ring-indigo-500/30 scale-105 animate-pulse'
                      : 'bg-gradient-to-br from-indigo-500 to-indigo-700 hover:from-indigo-600 hover:to-indigo-800 text-white ring-8 ring-indigo-500/15 hover:ring-indigo-500/30'
                  }`}
                >
                  <Mic size={38} className={isListening ? 'animate-bounce' : ''} />
                  {isListening && (
                    <span className="absolute inset-0 rounded-full border-2 border-indigo-400 animate-ping opacity-75" />
                  )}
                </button>

                <p className="mt-5 text-sm font-semibold text-white">
                  {isListening ? 'Listening… Speak your command' : 'Click to start speaking'}
                </p>
                <p className="text-xs text-slate-400 mt-1 max-w-[220px]">
                  {listeningFeedback || 'Try saying: "Turn on the bedroom light"'}
                </p>

                {/* Quick chip triggers */}
                <div className="flex flex-wrap gap-1.5 justify-center mt-4">
                  {['Turn on the fan', 'Turn it off', 'Turn off the light'].map((cmd) => (
                    <button
                      key={cmd}
                      onClick={() => handleExecute(cmd)}
                      className="px-2.5 py-1 rounded-lg bg-[#162035] hover:bg-indigo-600/30 hover:border-indigo-500/40 text-[11px] text-slate-300 border border-[#22304d] transition-all cursor-pointer"
                    >
                      {cmd}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              /* Text Input Mode */
              <div className="py-6 space-y-4">
                <form
                  onSubmit={(e) => {
                    e.preventDefault();
                    handleExecute(textInput);
                  }}
                  className="space-y-3"
                >
                  <div className="relative">
                    <input
                      type="text"
                      value={textInput}
                      onChange={(e) => setTextInput(e.target.value)}
                      placeholder="e.g. Turn on the bedroom light..."
                      className="w-full bg-[#0a0f1d] border border-[#232f45] rounded-xl px-4 py-3 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500"
                    />
                    <button
                      type="submit"
                      disabled={isProcessing || !textInput.trim()}
                      className="absolute right-2 top-2 p-1.5 rounded-lg bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-40 cursor-pointer"
                    >
                      <Send size={15} />
                    </button>
                  </div>
                </form>

                <p className="text-[11px] text-slate-400 text-center">
                  Type any voice command to run it through the Decision Engine.
                </p>
              </div>
            )}
          </div>

          <div className="pt-3 border-t border-[#1a2333] flex items-center justify-between text-[11px] text-slate-500">
            <span>Offline Vosk & Resemblyzer</span>
            <span className="text-indigo-400 font-medium">Ready</span>
          </div>
        </div>

        {/* Column 2: Last Command (4 cols) */}
        <div className="lg:col-span-4 bg-[#101828] border border-[#1e2a40] rounded-2xl p-5 flex flex-col justify-between shadow-sm">
          <div>
            <h2 className="text-sm font-semibold text-white flex items-center gap-2 mb-4">
              <Monitor size={16} className="text-indigo-400" /> Last Command
            </h2>

            {/* You said box */}
            <div className="p-4 rounded-xl bg-[#0a0f1d] border border-[#1b253b] mb-4">
              <div className="flex items-center justify-between text-xs text-slate-400 mb-1.5">
                <span className="flex items-center gap-1.5 font-medium">
                  <Monitor size={13} className="text-indigo-400" /> You said:
                </span>
                <span className="text-[11px] font-mono text-slate-500">{lastCommand.time}</span>
              </div>
              <p className="text-sm font-semibold text-white italic">
                "{lastCommand.text}"
              </p>
            </div>

            {/* Parsed Intent Section */}
            <div className="space-y-2.5">
              <div className="flex items-center gap-2 text-xs font-semibold text-indigo-400">
                <Sparkles size={14} /> Parsed Intent
              </div>

              <div className="p-3.5 rounded-xl bg-[#0e1627] border border-[#1b263b] space-y-2 text-xs">
                <div className="flex items-center justify-between">
                  <span className="text-slate-400">Intent:</span>
                  <span className="px-2 py-0.5 rounded bg-indigo-500/20 text-indigo-300 font-mono font-semibold text-[11px]">
                    {lastCommand.intent}
                  </span>
                </div>

                <div className="flex items-center justify-between">
                  <span className="text-slate-400">Device:</span>
                  <span className="px-2 py-0.5 rounded bg-sky-500/20 text-sky-300 font-mono text-[11px]">
                    {lastCommand.device}
                  </span>
                </div>

                <div className="flex items-center justify-between">
                  <span className="text-slate-400">Action:</span>
                  <span className="px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-400 font-mono text-[11px] font-bold">
                    {lastCommand.action}
                  </span>
                </div>

                <div className="flex items-center justify-between">
                  <span className="text-slate-400">Confidence:</span>
                  <span className="font-mono text-slate-200">
                    {lastCommand.confidence.toFixed(2)}
                  </span>
                </div>
              </div>
            </div>
          </div>

          <div className="pt-3 border-t border-[#1a2333] text-[11px] text-slate-500 flex items-center justify-between">
            <span>Intent Extractor</span>
            <span className="text-emerald-400">Multi-Turn Active</span>
          </div>
        </div>

        {/* Column 3: Decision Result (4 cols) */}
        <div className="lg:col-span-4 bg-[#101828] border border-[#1e2a40] rounded-2xl p-5 flex flex-col justify-between shadow-sm">
          <div>
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-sm font-semibold text-white flex items-center gap-2">
                <ShieldCheck size={16} className="text-indigo-400" /> Decision Result
              </h2>
              <span className="text-[11px] text-slate-500">•••</span>
            </div>

            {/* Decision outcome badge box */}
            <div
              className={`p-4 rounded-xl border mb-4 ${
                decisionResult.outcome === 'EXECUTE'
                  ? 'bg-emerald-950/20 border-emerald-500/30'
                  : decisionResult.outcome === 'CLARIFY'
                  ? 'bg-amber-950/20 border-amber-500/30'
                  : decisionResult.outcome === 'ESCALATE'
                  ? 'bg-rose-950/20 border-rose-500/30'
                  : 'bg-slate-900 border-slate-700'
              }`}
            >
              <div className="flex items-center gap-2.5">
                <div
                  className={`w-7 h-7 rounded-full flex items-center justify-center text-white font-bold text-xs ${
                    decisionResult.outcome === 'EXECUTE'
                      ? 'bg-emerald-500'
                      : decisionResult.outcome === 'CLARIFY'
                      ? 'bg-amber-500'
                      : decisionResult.outcome === 'ESCALATE'
                      ? 'bg-rose-500'
                      : 'bg-slate-600'
                  }`}
                >
                  <CheckCircle2 size={16} />
                </div>
                <div>
                  <span
                    className={`font-mono font-bold text-sm ${
                      decisionResult.outcome === 'EXECUTE'
                        ? 'text-emerald-400'
                        : decisionResult.outcome === 'CLARIFY'
                        ? 'text-amber-400'
                        : decisionResult.outcome === 'ESCALATE'
                        ? 'text-rose-400'
                        : 'text-slate-400'
                    }`}
                  >
                    {decisionResult.outcome}
                  </span>
                  <p className="text-xs text-slate-300 font-medium mt-0.5">
                    {decisionResult.title}
                  </p>
                </div>
              </div>
            </div>

            {/* Reason */}
            <div className="mb-4">
              <span className="text-[11px] text-slate-400 font-medium block mb-1">Reason</span>
              <p className="text-xs text-slate-200 leading-relaxed bg-[#0a0f1d] p-3 rounded-xl border border-[#1b253b]">
                {decisionResult.reason}
              </p>
            </div>

            {/* Execution Status */}
            <div>
              <div className="flex items-center justify-between text-[11px] text-slate-400 mb-1">
                <span>Execution Status</span>
                <span className="font-mono text-slate-500">{decisionResult.time}</span>
              </div>
              <div className="p-3 rounded-xl bg-[#0a0f1d] border border-[#1b253b] flex items-center justify-between text-xs">
                <span className="flex items-center gap-1.5 font-semibold text-emerald-400">
                  <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
                  {decisionResult.status}
                </span>
                <span className="text-slate-300 font-medium truncate max-w-[160px]">
                  {decisionResult.message}
                </span>
              </div>
            </div>
          </div>

          <div className="pt-3 border-t border-[#1a2333] text-[11px] text-slate-500 flex items-center justify-between">
            <span>Safety Rule Engine</span>
            <span className="text-emerald-400">100% Deterministic</span>
          </div>
        </div>
      </div>

      {/* ── Second Row 2 Columns: Devices & Emergency ─────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
        {/* Left Column: Smart Home Devices (7 cols) */}
        <div className="lg:col-span-7 bg-[#101828] border border-[#1e2a40] rounded-2xl p-5 shadow-sm">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-semibold text-white flex items-center gap-2">
              <Lightbulb size={16} className="text-amber-400" /> Smart Home Devices
            </h2>
            <Link
              to="/devices"
              className="text-xs font-semibold text-indigo-400 hover:text-indigo-300 transition-colors flex items-center gap-1"
            >
              View All →
            </Link>
          </div>

          {/* 3 Device Cards in a row */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3.5">
            {devices.map((device) => {
              const isOn = device.state === 'ON';
              const isFan = device.device_type === 'fan';

              return (
                <div
                  key={device.id}
                  className={`p-4 rounded-xl border transition-all ${
                    isOn
                      ? 'bg-[#122038] border-indigo-500/40 shadow-lg shadow-indigo-900/20'
                      : 'bg-[#0a0f1d] border-[#1b253b]'
                  }`}
                >
                  <div className="flex items-center justify-between mb-3">
                    <div
                      className={`w-9 h-9 rounded-xl flex items-center justify-center ${
                        isOn
                          ? isFan
                            ? 'bg-sky-500/20 text-sky-400'
                            : 'bg-amber-500/20 text-amber-400'
                          : 'bg-[#162035] text-slate-500'
                      }`}
                    >
                      {isFan ? (
                        <Fan size={20} className={isOn ? 'animate-spin' : ''} />
                      ) : (
                        <Lightbulb size={20} />
                      )}
                    </div>

                    {/* Toggle Switch */}
                    <button
                      onClick={() => handleToggleDevice(device)}
                      disabled={deviceLoading === device.id}
                      className={`w-11 h-6 flex items-center rounded-full p-1 transition-colors cursor-pointer ${
                        isOn ? 'bg-emerald-500' : 'bg-slate-700'
                      }`}
                    >
                      <div
                        className={`bg-white w-4 h-4 rounded-full shadow-md transform transition-transform ${
                          isOn ? 'translate-x-5' : 'translate-x-0'
                        }`}
                      />
                    </button>
                  </div>

                  <p className="text-xs font-bold text-white truncate">{device.name}</p>
                  <p className="text-[11px] text-slate-400 capitalize">
                    {device.location.replace('_', ' ')}
                  </p>

                  <div className="mt-3 pt-2.5 border-t border-[#1a253a] flex items-center gap-1.5 text-[11px]">
                    <span
                      className={`w-2 h-2 rounded-full ${
                        isOn ? 'bg-emerald-400 animate-pulse' : 'bg-slate-600'
                      }`}
                    />
                    <span className={isOn ? 'text-emerald-400 font-semibold' : 'text-slate-400'}>
                      {device.state}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Right Column: Emergency Assistance (5 cols) */}
        <div className="lg:col-span-5 bg-gradient-to-br from-[#1a111b] via-[#14121f] to-[#101828] border border-rose-500/30 rounded-2xl p-5 flex flex-col justify-between shadow-sm relative overflow-hidden">
          {/* Subtle sonar rings graphic in top right */}
          <div className="absolute -right-8 -top-8 w-32 h-32 rounded-full border border-rose-500/20 pointer-events-none" />
          <div className="absolute -right-4 -top-4 w-24 h-24 rounded-full border border-rose-500/30 pointer-events-none" />

          <div>
            <div className="flex items-center justify-between mb-2">
              <h2 className="text-sm font-semibold text-rose-300 flex items-center gap-2">
                <AlertTriangle size={16} className="text-rose-400" /> Emergency Assistance
              </h2>
              {emergencyAlertActive && (
                <span className="px-2 py-0.5 rounded-full bg-rose-500/20 text-rose-400 text-[10px] font-bold animate-pulse">
                  ALERT ACTIVE
                </span>
              )}
            </div>

            <p className="text-xs text-slate-300 leading-relaxed mt-2">
              Need help? Say <span className="font-semibold text-rose-400">"Help"</span> or{' '}
              <span className="font-semibold text-rose-400">"Emergency"</span>.
              <br />
              <span className="text-slate-400 text-[11px]">
                This will trigger an emergency alert (simulation) and notify emergency contacts.
              </span>
            </p>
          </div>

          <div className="space-y-2 mt-5">
            {/* Red primary trigger emergency button */}
            <button
              onClick={handleTriggerEmergency}
              className="w-full py-2.5 px-4 rounded-xl bg-gradient-to-r from-rose-600 to-rose-700 hover:from-rose-500 hover:to-rose-600 text-white font-semibold text-xs flex items-center justify-center gap-2 shadow-lg shadow-rose-900/30 transition-all cursor-pointer"
            >
              <PhoneCall size={15} /> Trigger Emergency
            </button>

            {/* View Emergency History button */}
            <Link
              to="/emergency"
              className="w-full py-2 px-4 rounded-xl bg-[#0a0f1d] hover:bg-[#162035] text-slate-300 hover:text-white border border-[#232f45] font-medium text-xs flex items-center justify-center gap-2 transition-colors cursor-pointer"
            >
              <ListOrdered size={14} /> View Emergency History
            </Link>
          </div>
        </div>
      </div>

      {/* ── Bottom Section: Recent Activity ───────── */}
      <div className="bg-[#101828] border border-[#1e2a40] rounded-2xl p-5 shadow-sm">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-semibold text-white flex items-center gap-2">
            <FileText size={16} className="text-indigo-400" /> Recent Activity
          </h2>
          <Link
            to="/activity"
            className="text-xs font-semibold text-indigo-400 hover:text-indigo-300 transition-colors flex items-center gap-1"
          >
            View All →
          </Link>
        </div>

        {/* Activity Table */}
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="text-slate-400 font-semibold border-b border-[#1b253b] pb-2">
              <tr>
                <th className="pb-2.5 font-medium">Time</th>
                <th className="pb-2.5 font-medium">Type</th>
                <th className="pb-2.5 font-medium">Command / Event</th>
                <th className="pb-2.5 font-medium text-right">Result</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#172033]">
              {activity && activity.interactions.length > 0 ? (
                activity.interactions.slice(0, 5).map((item) => (
                  <tr key={item.id} className="hover:bg-[#0a0f1d]/50 transition-colors">
                    <td className="py-2.5 font-mono text-slate-400 text-[11px]">
                      {new Date(item.created_at).toLocaleTimeString('en-US', {
                        hour: '2-digit',
                        minute: '2-digit',
                      })}
                    </td>
                    <td className="py-2.5">
                      <span className="flex items-center gap-1 text-slate-300">
                        {item.input_mode === 'voice' ? (
                          <Mic size={13} className="text-indigo-400" />
                        ) : (
                          <Monitor size={13} className="text-sky-400" />
                        )}
                        <span className="capitalize">{item.input_mode}</span>
                      </span>
                    </td>
                    <td className="py-2.5 text-slate-200 font-medium truncate max-w-[280px]">
                      {item.recognized_text}
                    </td>
                    <td className="py-2.5 text-right">
                      <span
                        className={`px-2 py-0.5 rounded-full text-[10px] font-semibold ${
                          item.decision_outcome === 'EXECUTE'
                            ? 'bg-emerald-500/15 text-emerald-400'
                            : item.decision_outcome === 'CLARIFY'
                            ? 'bg-amber-500/15 text-amber-400'
                            : item.decision_outcome === 'ESCALATE'
                            ? 'bg-rose-500/15 text-rose-400'
                            : 'bg-slate-500/15 text-slate-400'
                        }`}
                      >
                        {item.decision_outcome === 'EXECUTE'
                          ? 'Executed'
                          : item.decision_outcome === 'CLARIFY'
                          ? 'Clarified'
                          : item.decision_outcome === 'ESCALATE'
                          ? 'Escalated'
                          : 'Rejected'}
                      </span>
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={4} className="py-4 text-center text-slate-500">
                    No recent activities logged yet.
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
