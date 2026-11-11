/* ── Sidebar navigation layout matching VoxEdge design ──────────────────────── */

import { useState } from 'react';
import { NavLink, Outlet } from 'react-router-dom';
import {
  Activity,
  AlertTriangle,
  BarChart3,
  Home,
  Mic,
  Lightbulb,
  Settings as SettingsIcon,
  X,
  ShieldCheck,
  Cpu,
  Database,
  Radio,
  LogOut,
  User,
} from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';

const NAV = [
  { to: '/', icon: Home, label: 'Dashboard' },
  { to: '/voice', icon: Mic, label: 'Voice Assistant' },
  { to: '/devices', icon: Lightbulb, label: 'Device Control' },
  { to: '/activity', icon: Activity, label: 'Activity & Safety' },
  { to: '/emergency', icon: AlertTriangle, label: 'Emergency' },
  { to: '/evaluation', icon: BarChart3, label: 'Evaluation' },
];

export default function Layout() {
  const [showSettings, setShowSettings] = useState(false);
  const { user, logout } = useAuth();

  return (
    <div className="flex h-screen overflow-hidden bg-[#0a0f1d] text-[#f1f5f9]">
      {/* Sidebar */}
      <aside className="w-64 flex-shrink-0 bg-[#0d1527] border-r border-[#1a2333] flex flex-col justify-between">
        <div>
          {/* Logo & Header */}
          <div className="p-6 border-b border-[#1a2333]">
            <div className="flex items-center gap-3">
              <div className="flex items-center gap-1 p-2 rounded-xl bg-indigo-500/15 border border-indigo-500/20 text-indigo-400">
                <span className="w-1 h-5 bg-indigo-400 rounded-full animate-pulse" />
                <span className="w-1 h-3 bg-indigo-400 rounded-full" />
                <span className="w-1 h-6 bg-indigo-400 rounded-full animate-pulse" />
                <span className="w-1 h-4 bg-indigo-400 rounded-full" />
              </div>
              <div>
                <h1 className="text-xl font-bold tracking-tight text-white flex items-center gap-1.5">
                  Vox<span className="text-indigo-400">Edge</span>
                </h1>
                <p className="text-[11px] text-slate-400 font-medium">
                  Voice-Based Assistive System
                </p>
              </div>
            </div>
          </div>

          {/* Navigation Links */}
          <nav className="py-4 space-y-1 px-3">
            {NAV.map(({ to, icon: Icon, label }) => (
              <NavLink
                key={to}
                to={to}
                end={to === '/'}
                className={({ isActive }) =>
                  `flex items-center gap-3.5 px-4 py-3 rounded-xl text-sm font-medium transition-all ${
                    isActive
                      ? 'bg-gradient-to-r from-indigo-600 to-indigo-700 text-white shadow-lg shadow-indigo-600/30'
                      : 'text-slate-400 hover:bg-[#131c2e] hover:text-slate-200'
                  }`
                }
              >
                <Icon size={18} />
                {label}
              </NavLink>
            ))}

            <button
              onClick={() => setShowSettings(true)}
              className="w-full flex items-center gap-3.5 px-4 py-3 rounded-xl text-sm font-medium text-slate-400 hover:bg-[#131c2e] hover:text-slate-200 transition-all cursor-pointer text-left"
            >
              <SettingsIcon size={18} />
              Settings
            </button>
          </nav>
        </div>

        {/* User & Logout */}
        <div>
          {user && (
            <div className="mx-3 mb-2 p-3 rounded-xl bg-[#0b111e] border border-[#1b263b] flex items-center justify-between">
              <div className="flex items-center gap-2.5 min-w-0">
                <div className="w-8 h-8 rounded-lg bg-indigo-500/20 border border-indigo-500/30 flex items-center justify-center flex-shrink-0">
                  <User size={14} className="text-indigo-400" />
                </div>
                <div className="min-w-0">
                  <p className="text-xs font-medium text-white truncate">
                    {user.full_name || user.username}
                  </p>
                  <p className="text-[10px] text-slate-500 truncate">
                    @{user.username}
                  </p>
                </div>
              </div>
              <button
                onClick={logout}
                title="Sign out"
                className="p-1.5 rounded-lg text-slate-400 hover:text-red-400 hover:bg-red-400/10 transition-colors flex-shrink-0"
              >
                <LogOut size={14} />
              </button>
            </div>
          )}

          {/* Bottom Banner Card */}
          <div className="p-4 m-3 rounded-2xl bg-gradient-to-b from-[#131d31] to-[#0e1626] border border-[#1e2a40] relative overflow-hidden">
            <div className="flex items-center gap-2 mb-2 text-indigo-400 text-xs font-semibold uppercase tracking-wider">
              <Radio size={14} className="animate-pulse" /> Live Assist
            </div>
            <p className="text-xs font-medium text-slate-200 leading-snug">
              Smart Assistance for a Safer, Independent Life
            </p>
            <div className="w-full bg-[#1b253b] h-1.5 rounded-full mt-3 overflow-hidden">
              <div className="bg-indigo-500 h-full w-2/3 rounded-full" />
            </div>
            <div className="mt-2.5 flex items-center justify-between text-[10px] text-slate-500">
              <span>v2.0.0 · Phase 2</span>
              <span className="text-emerald-400 flex items-center gap-1">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-ping" /> Online
              </span>
            </div>
          </div>
        </div>
      </aside>

      {/* Main Content Area */}
      <main className="flex-1 overflow-y-auto bg-[#0a0f1d] p-6 lg:p-8">
        <Outlet />
      </main>

      {/* Settings Modal */}
      {showSettings && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-[#10192b] border border-[#232f45] rounded-2xl p-6 max-w-md w-full shadow-2xl relative">
            <button
              onClick={() => setShowSettings(false)}
              className="absolute top-5 right-5 text-slate-400 hover:text-white"
            >
              <X size={20} />
            </button>

            <h3 className="text-lg font-bold text-white flex items-center gap-2 mb-4">
              <SettingsIcon className="text-indigo-400" size={20} /> System Configuration
            </h3>

            <div className="space-y-3.5 text-xs">
              <div className="p-3 rounded-xl bg-[#0b111e] border border-[#1b263b] flex items-center justify-between">
                <span className="text-slate-400 flex items-center gap-2">
                  <Cpu size={15} className="text-sky-400" /> ASR Engine:
                </span>
                <span className="text-white font-mono">Vosk (Offline Kaldi)</span>
              </div>

              <div className="p-3 rounded-xl bg-[#0b111e] border border-[#1b263b] flex items-center justify-between">
                <span className="text-slate-400 flex items-center gap-2">
                  <ShieldCheck size={15} className="text-emerald-400" /> Speaker Verification:
                </span>
                <span className="text-white font-mono">Resemblyzer (GE2E 256-dim)</span>
              </div>

              <div className="p-3 rounded-xl bg-[#0b111e] border border-[#1b263b] flex items-center justify-between">
                <span className="text-slate-400">Similarity Threshold:</span>
                <span className="text-indigo-400 font-mono font-bold">0.65</span>
              </div>

              <div className="p-3 rounded-xl bg-[#0b111e] border border-[#1b263b] flex items-center justify-between">
                <span className="text-slate-400 flex items-center gap-2">
                  <Database size={15} className="text-indigo-400" /> Database:
                </span>
                <span className="text-white font-mono">SQLite (SQLAlchemy ORM)</span>
              </div>

              <div className="p-3 rounded-xl bg-[#0b111e] border border-[#1b263b] flex items-center justify-between">
                <span className="text-slate-400">Backend API:</span>
                <span className="text-emerald-400 font-mono">http://127.0.0.1:8000</span>
              </div>
            </div>

            <button
              onClick={() => setShowSettings(false)}
              className="mt-6 w-full py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white font-medium text-xs transition-colors"
            >
              Close
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
