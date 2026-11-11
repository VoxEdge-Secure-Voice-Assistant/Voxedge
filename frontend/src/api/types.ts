/* ── API types matching the Pydantic schemas ─────────────────────────────── */

/* ── Auth types ────────────────────────────────────────────────────────────── */

export interface UserProfile {
  id: number;
  username: string;
  full_name: string | null;
  email: string | null;
  voice_enrolled: boolean;
  voice_profile_path: string | null;
  created_at: string;
}

export interface AuthTokenResponse {
  access_token: string;
  token_type: string;
  user: UserProfile;
}

export interface LoginRequest {
  username: string;
  password: string;
}

export interface RegisterRequest {
  username: string;
  password: string;
  full_name?: string;
  email?: string;
}

export interface Device {
  id: string;
  name: string;
  device_type: string;
  location: string;
  state: string;
  supported_actions: string[];
  is_active: boolean;
  updated_at: string;
}

export interface DeviceListResponse {
  devices: Device[];
  count: number;
}

export interface EnrollmentStatus {
  is_enrolled: boolean;
  similarity_threshold: number;
  message: string;
}

export interface VoiceEnrollResponse {
  success: boolean;
  is_enrolled: boolean;
  message: string;
  dimensions?: number;
  similarity_threshold?: number;
}

export interface StructuredIntent {
  raw_text: string;
  intent: string;
  device?: string | null;
  device_type?: string | null;
  location?: string | null;
  action?: string | null;
  is_ambiguous: boolean;
  requires_clarification: boolean;
  clarification_prompt?: string | null;
  confidence: number;
  reason: string;
  is_indirect: boolean;
  suggested_action?: string | null;
  suggested_device?: string | null;
}

export interface VoiceProcessRequest {
  text: string;
  input_mode?: string;
  session_id?: string;
}

export interface VoiceProcessResponse {
  interaction_id: number;
  session_id: string;
  recognized_text: string;
  intent: string | null;
  intent_confidence: number | null;
  entities: Record<string, unknown>;
  structured_intent?: StructuredIntent | null;
  slm_proposal?: Record<string, unknown> | null;
  is_ambiguous?: boolean;
  requires_clarification?: boolean;
  decision: string;
  decision_reason: string;
  target_device: string | null;
  requested_action: string | null;
  execution_status: string | null;
  new_device_state: string | null;
  clarification_question: string | null;
  requires_confirmation: boolean;
  message: string;
  speaker_verified?: boolean | null;
  speaker_similarity?: number | null;
  similarity_threshold?: number | null;
  auth_token?: string | null;
}

export interface ConfirmationRequest {
  session_id: string;
  response: string;
  interaction_id?: number;
}

export interface InteractionSummary {
  id: number;
  session_id: string;
  recognized_text: string | null;
  intent: string | null;
  decision_outcome: string | null;
  decision_reason: string | null;
  target_device_id: string | null;
  requested_action: string | null;
  execution_status: string | null;
  created_at: string;
}

export interface ActivityEntry {
  id: number;
  interaction_id: number | null;
  device_id: string;
  action: string;
  previous_state: string;
  new_state: string;
  success: boolean;
  error_message: string | null;
  created_at: string;
}

export interface ActivityResponse {
  interactions: InteractionSummary[];
  device_actions: ActivityEntry[];
  total_interactions: number;
  total_actions: number;
}

export interface EmergencyContact {
  name: string;
  relationship: string;
  phone: string;
  notified: boolean;
  notified_at: string | null;
}

export interface EmergencyEvent {
  id: number;
  trigger_text: string;
  status: string;
  severity: string;
  category?: string | null;
  contacts: EmergencyContact[];
  notes: string | null;
  created_at: string;
  updated_at: string;
  resolved_at: string | null;
}

export interface SystemStatus {
  status: string;
  version: string;
  vosk_model_loaded: boolean;
  voice_enrolled: boolean;
  total_devices: number;
  active_devices: number;
  total_interactions: number;
  active_emergencies: number;
  uptime_seconds: number;
  timestamp: string;
}

export interface ConversationTurn {
  id: number;
  session_id: string;
  timestamp: string;
  user_text?: string | null;
  assistant_response?: string | null;
  intent?: string | null;
  device_id?: string | null;
  action?: string | null;
  decision_outcome?: string | null;
  execution_status?: string | null;
  is_clarification: boolean;
  clarification_question?: string | null;
  clarification_answer?: string | null;
  is_follow_up: boolean;
}

export interface ConversationHistoryResponse {
  session_id: string;
  total_turns: number;
  max_limit: number;
  turns: ConversationTurn[];
}

export interface ContextSummaryResponse {
  session_id: string;
  last_device?: string | null;
  last_device_type?: string | null;
  last_action?: string | null;
  last_command?: string | null;
  has_pending_clarification: boolean;
  pending_clarification_question?: string | null;
  pending_action?: string | null;
  current_device_states: Record<string, string>;
}
