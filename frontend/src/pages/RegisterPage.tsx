/* ── Register page — matches VoxEdge dark theme ──────────────────────────── */

import { useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';

export default function RegisterPage() {
  const { register } = useAuth();
  const navigate = useNavigate();

  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError('');

    if (password !== confirmPassword) {
      setError('Passwords do not match');
      return;
    }

    setLoading(true);
    try {
      await register(
        username,
        password,
        fullName || undefined,
        email || undefined,
      );
      navigate('/', { replace: true });
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Registration failed');
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
            Create your account
          </p>
        </div>

        {/* Card */}
        <form
          onSubmit={handleSubmit}
          className="bg-[#0d1527] border border-[#1a2333] rounded-2xl p-6 space-y-4"
        >
          <h2 className="text-lg font-semibold text-white text-center">
            Register
          </h2>

          {error && (
            <div className="text-sm text-red-400 bg-red-400/10 border border-red-400/20 rounded-xl px-4 py-2.5 text-center">
              {error}
            </div>
          )}

          <div className="space-y-1.5">
            <label className="text-xs text-slate-400 font-medium" htmlFor="reg-username">
              Username <span className="text-red-400">*</span>
            </label>
            <input
              id="reg-username"
              type="text"
              required
              minLength={3}
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="w-full px-4 py-2.5 rounded-xl bg-[#0b111e] border border-[#1b263b] text-white text-sm placeholder-slate-500 focus:outline-none focus:border-indigo-500 transition-colors"
              placeholder="Choose a username"
              autoComplete="username"
            />
          </div>

          <div className="space-y-1.5">
            <label className="text-xs text-slate-400 font-medium" htmlFor="reg-fullname">
              Full Name
            </label>
            <input
              id="reg-fullname"
              type="text"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              className="w-full px-4 py-2.5 rounded-xl bg-[#0b111e] border border-[#1b263b] text-white text-sm placeholder-slate-500 focus:outline-none focus:border-indigo-500 transition-colors"
              placeholder="Your full name (optional)"
              autoComplete="name"
            />
          </div>

          <div className="space-y-1.5">
            <label className="text-xs text-slate-400 font-medium" htmlFor="reg-email">
              Email
            </label>
            <input
              id="reg-email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full px-4 py-2.5 rounded-xl bg-[#0b111e] border border-[#1b263b] text-white text-sm placeholder-slate-500 focus:outline-none focus:border-indigo-500 transition-colors"
              placeholder="Email address (optional)"
              autoComplete="email"
            />
          </div>

          <div className="space-y-1.5">
            <label className="text-xs text-slate-400 font-medium" htmlFor="reg-password">
              Password <span className="text-red-400">*</span>
            </label>
            <input
              id="reg-password"
              type="password"
              required
              minLength={6}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full px-4 py-2.5 rounded-xl bg-[#0b111e] border border-[#1b263b] text-white text-sm placeholder-slate-500 focus:outline-none focus:border-indigo-500 transition-colors"
              placeholder="At least 6 characters"
              autoComplete="new-password"
            />
          </div>

          <div className="space-y-1.5">
            <label className="text-xs text-slate-400 font-medium" htmlFor="reg-confirm">
              Confirm Password <span className="text-red-400">*</span>
            </label>
            <input
              id="reg-confirm"
              type="password"
              required
              minLength={6}
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              className="w-full px-4 py-2.5 rounded-xl bg-[#0b111e] border border-[#1b263b] text-white text-sm placeholder-slate-500 focus:outline-none focus:border-indigo-500 transition-colors"
              placeholder="Repeat password"
              autoComplete="new-password"
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white font-medium text-sm transition-colors"
          >
            {loading ? 'Creating account…' : 'Create Account'}
          </button>

          <p className="text-xs text-slate-400 text-center">
            Already have an account?{' '}
            <Link
              to="/login"
              className="text-indigo-400 hover:text-indigo-300 font-medium"
            >
              Sign In
            </Link>
          </p>
        </form>
      </div>
    </div>
  );
}

