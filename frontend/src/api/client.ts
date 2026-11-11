/* ── API client — all fetch calls to the FastAPI backend ──────────────────── */

import type {
  ActivityResponse,
  AuthTokenResponse,
  ConfirmationRequest,
  Device,
  DeviceListResponse,
  EmergencyEvent,
  EnrollmentStatus,
  LoginRequest,
  RegisterRequest,
  SystemStatus,
  UserProfile,
  VoiceEnrollResponse,
  VoiceProcessRequest,
  VoiceProcessResponse,
} from './types';

const BASE = '/api';

let cachedAuthToken: string | null = localStorage.getItem('voxedge_auth_token');

export const getAuthToken = () => cachedAuthToken;

export const setAuthToken = (token: string | null) => {
  cachedAuthToken = token;
  if (token) {
    localStorage.setItem('voxedge_auth_token', token);
  } else {
    localStorage.removeItem('voxedge_auth_token');
  }
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(cachedAuthToken ? { Authorization: `Bearer ${cachedAuthToken}` } : {}),
    ...(init?.headers as Record<string, string>),
  };

  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers,
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `API error ${res.status}`);
  }
  return res.json();
}

/* ── Voice & Authentication ────────────────────────────────────────────────── */

export const getEnrollmentStatus = () =>
  request<EnrollmentStatus>('/voice/enrollment-status');

export const deleteVoiceProfile = async () => {
  setAuthToken(null);
  return request<{ success: boolean; message: string }>('/voice/profile', {
    method: 'DELETE',
  });
};

export const enrollVoice = async (
  audioBlob: Blob,
  force = false,
): Promise<VoiceEnrollResponse> => {
  const formData = new FormData();
  formData.append('file', audioBlob, 'enrollment.wav');
  formData.append('force', String(force));

  const headers: Record<string, string> = {
    ...(cachedAuthToken ? { Authorization: `Bearer ${cachedAuthToken}` } : {}),
  };

  const res = await fetch(`${BASE}/voice/enroll`, {
    method: 'POST',
    headers,
    body: formData,
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Enrollment failed with status ${res.status}`);
  }
  const data: VoiceEnrollResponse = await res.json();
  if (data.auth_token) {
    setAuthToken(data.auth_token);
  }
  return data;
};

export const processVoiceAudio = async (
  audioBlob: Blob,
  sessionId?: string,
): Promise<VoiceProcessResponse> => {
  const formData = new FormData();
  formData.append('file', audioBlob, 'command.wav');
  if (sessionId) {
    formData.append('session_id', sessionId);
  }

  const res = await fetch(`${BASE}/voice/process-audio`, {
    method: 'POST',
    body: formData,
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Audio command failed with status ${res.status}`);
  }

  const data: VoiceProcessResponse = await res.json();
  if (data.auth_token) {
    setAuthToken(data.auth_token);
  }
  return data;
};

export const processCommand = async (body: VoiceProcessRequest) => {
  const data = await request<VoiceProcessResponse>('/voice/process', {
    method: 'POST',
    body: JSON.stringify(body),
  });
  if (data.auth_token) {
    setAuthToken(data.auth_token);
  }
  return data;
};

export const confirmDecision = (body: ConfirmationRequest) =>
  request<VoiceProcessResponse>('/decisions/confirm', {
    method: 'POST',
    body: JSON.stringify(body),
  });

/* ── Conversation History & Context ────────────────────────────────────────── */

export const getConversationHistory = (sessionId: string, limit?: number) =>
  request<import('./types').ConversationHistoryResponse>(
    `/voice/history?session_id=${encodeURIComponent(sessionId)}${limit ? `&limit=${limit}` : ''}`
  );

export const getContextSummary = (sessionId: string) =>
  request<import('./types').ContextSummaryResponse>(
    `/voice/context?session_id=${encodeURIComponent(sessionId)}`
  );

export const clearConversationHistory = (sessionId: string) =>
  request<{ success: boolean; deleted_turns: number }>(
    `/voice/history?session_id=${encodeURIComponent(sessionId)}`,
    { method: 'DELETE' }
  );

/* ── Devices ───────────────────────────────────────────────────────────────── */

export const listDevices = () =>
  request<DeviceListResponse>('/devices');

export const getDevice = (id: string) =>
  request<Device>(`/devices/${id}`);

export const commandDevice = (id: string, action: string) =>
  request<{ device_id: string; action: string; previous_state: string; new_state: string; success: boolean; message: string }>(
    `/devices/${id}/command`,
    { method: 'POST', body: JSON.stringify({ action }) },
  );

/* ── Activity ──────────────────────────────────────────────────────────────── */

export const getActivity = (limit = 50) =>
  request<ActivityResponse>(`/activity?limit=${limit}`);

/* ── Emergency ─────────────────────────────────────────────────────────────── */

export const triggerEmergency = (text = 'Emergency button pressed', severity = 'HIGH') =>
  request<EmergencyEvent>('/emergency/trigger', {
    method: 'POST',
    body: JSON.stringify({ trigger_text: text, severity }),
  });

export const listEmergencies = () =>
  request<EmergencyEvent[]>('/emergency');

export const updateEmergency = (id: number, status: string, notes?: string) =>
  request<EmergencyEvent>(`/emergency/${id}`, {
    method: 'PUT',
    body: JSON.stringify({ status, notes }),
  });

/* ── System ────────────────────────────────────────────────────────────────── */

export const getSystemStatus = () =>
  request<SystemStatus>('/system/status');

/* ── Auth ──────────────────────────────────────────────────────────────────── */

export const loginUser = (body: LoginRequest) =>
  request<AuthTokenResponse>('/auth/login', {
    method: 'POST',
    body: JSON.stringify(body),
  });

export const registerUser = (body: RegisterRequest) =>
  request<AuthTokenResponse>('/auth/register', {
    method: 'POST',
    body: JSON.stringify(body),
  });

export const logoutUser = () =>
  request<{ success: boolean; message: string }>('/auth/logout', {
    method: 'POST',
  });

export const getMe = () =>
  request<UserProfile>('/auth/me');
