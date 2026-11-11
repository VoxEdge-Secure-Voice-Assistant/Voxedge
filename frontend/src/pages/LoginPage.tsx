/* ── Login page — matches VoxEdge dark theme ─────────────────────────────── */

import { useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';

export default function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();

  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      await login(username, password);
      navigate('/', { replace: true });
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Login failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-[#0a0f1d] px-4">
      <div className="w-full max-w-sm">
        {/* Logo */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center gap-1 p-2.5 rounded-xl bg-indigo-500/15 border border-indigo-500/20 text-indigo-400 mb-4">
            <span className="w-1 h-5 bg-indigo-400 rounded-full animate-pulse" />
            <span className="w-1 h-3 bg-indigo-400 rounded-full" />
            <span className="w-1 h-6 bg-indigo-400 rounded-full animate-pulse" />
            <span className="w-1 h-4 bg-indigo-400 rounded-full" />
          </div>
          <h1 className="text-2xl font-bold text-white">
            Vox<span className="text-indigo-400">Edge</span>
          </h1>
          <p className="text-sm text-slate-400 mt-1">
            Voice-Based Assistive System
          </p>
        </div>

        {/* Card */}
        <form
          onSubmit={handleSubmit}
          className="bg-[#0d1527] border border-[#1a2333] rounded-2xl p-6 space-y-5"
        >
          <h2 className="text-lg font-semibold text-white text-center">
            Sign In
          </h2>

          {error && (
            <div className="text-sm text-red-400 bg-red-400/10 border border-red-400/20 rounded-xl px-4 py-2.5 text-center">
              {error}
            </div>
          )}

          <div className="space-y-1.5">
            <label className="text-xs text-slate-400 font-medium" htmlFor="username">
              Username
            </label>
            <input
              id="username"
              type="text"
              required
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="w-full px-4 py-2.5 rounded-xl bg-[#0b111e] border border-[#1b263b] text-white text-sm placeholder-slate-500 focus:outline-none focus:border-indigo-500 transition-colors"
              placeholder="Enter username"
              autoComplete="username"
            />
          </div>

          <div className="space-y-1.5">
            <label className="text-xs text-slate-400 font-medium" htmlFor="password">
              Password
            </label>
            <input
              id="password"
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full px-4 py-2.5 rounded-xl bg-[#0b111e] border border-[#1b263b] text-white text-sm placeholder-slate-500 focus:outline-none focus:border-indigo-500 transition-colors"
              placeholder="Enter password"
              autoComplete="current-password"
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white font-medium text-sm transition-colors"
          >
            {loading ? 'Signing in…' : 'Sign In'}
          </button>

          <p className="text-xs text-slate-400 text-center">
            Don't have an account?{' '}
            <Link
              to="/register"
              className="text-indigo-400 hover:text-indigo-300 font-medium"
            >
              Register
            </Link>
          </p>
        </form>
      </div>
    </div>
  );
}

