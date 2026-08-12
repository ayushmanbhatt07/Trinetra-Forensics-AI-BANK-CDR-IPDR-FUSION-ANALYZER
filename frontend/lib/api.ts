
export interface DossierIntelligence {
  kind: string;
  value: string;
  primary: {
    timestamp?: string;
    amount?: number;
    risk_score: number;
    risk_band: string;
    fraud_probability?: number;
    confidence: number;
    type?: string;
    channel?: string;
    bank?: string;
    status?: string;
    reference?: string;
  };
  sender: {
    name?: string;
    customer_id?: string;
    account_no?: string;
    bank?: string;
    ifsc?: string;
    phone?: string;
    email?: string;
    upi?: string;
    balance?: number;
    risk_category?: string;
    str_count?: number;
    linked_devices?: string[];
    linked_ips?: string[];
    linked_sims?: string[];
    locations?: string[];
    kyc_status?: string;
  };
  receivers: {
    name?: string;
    account_no?: string;
    bank?: string;
    phone?: string;
    upi?: string;
    risk_score?: number;
    total_received?: number;
    first_seen?: string;
    last_seen?: string;
    shared_device?: boolean;
    shared_ip?: boolean;
    shared_phone?: boolean;
  }[];
  ai: {
    money_flow_summary?: string;
    flow_stats?: {
      total_value: number;
      hops: number;
      accounts: number;
      banks: number;
      circular: boolean;
      layering: boolean;
      structuring: boolean;
    };
    investigation_summary: string[];
    recommendations: string[];
  };
  journey: {
    timestamp: string;
    event: string;
  }[];
  rules: {
    rule: string;
    points: number;
    meaning: string;
    evidence: string;
  }[];
  connections: Record<string, string[]>;
  network: {
    degree?: number;
    community?: string;
    centrality?: number;
    bridge_score?: number;
    connected_accounts?: number;
  };
  history: {
    avg_daily_txns?: number;
    avg_amount?: number;
    max_amount?: number;
    normal_hours?: string;
    frequent_beneficiaries?: string[];
  };
  correlations: {
    dataset: string;
    evidence: string;
    confidence: number;
    impact: string;
  }[];
}

export interface PipelineStatus {
  status: string;
  progress: number;
  ready: boolean;
  fused_ready?: boolean;
  anomalies_ready?: boolean;
  graphs_ready?: boolean;
  dataset_id: string | null;
  error?: string | null;
}

/**
 * Backend API client.
 *
 * Base URL resolution order:
 *   1. NEXT_PUBLIC_API_URL env var (use http://<host>:8000 in the browser,
 *      or the same-origin proxy when deployed behind nginx with /api prefix)
 *   2. window.location.origin + "/api" when served by the same origin
 *   3. http://localhost:8000 (local dev fallback)
 */

const DEFAULT_API_URL = "http://localhost:8000";

export function apiBaseUrl(): string {
  if (typeof window === "undefined") {
    return process.env.NEXT_PUBLIC_API_URL || DEFAULT_API_URL;
  }
  const envUrl = process.env.NEXT_PUBLIC_API_URL;
  if (envUrl) return envUrl.replace(/\/+$/, "");
  return window.location.origin + "/api";
}

function bearerToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem("backend_token");
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export function isPipelineNotReady(err: unknown): boolean {
  return err instanceof ApiError && err.status === 425;
}

export function isNoDataLoaded(err: unknown): boolean {
  return err instanceof ApiError && err.status === 409;
}

export function isNetworkOrWarmupError(err: unknown): boolean {
  return err instanceof ApiError && (err.status === 0 || err.status === 503);
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = {};
  const token = bearerToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  if (!(init?.body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
  }
  try {
    const res = await fetch(apiBaseUrl() + path, { ...init, headers });
    if (!res.ok) {
      if (res.status === 401) {
        if (typeof window !== "undefined") {
          window.dispatchEvent(new CustomEvent("api:401"));
        }
      } else if (res.status === 409) {
        if (typeof window !== "undefined") {
          window.dispatchEvent(new CustomEvent("api:409"));
        }
      }

      let detail = `HTTP ${res.status}`;
      try {
        const body = await res.json();
        detail = body.detail || detail;
      } catch {
        /* keep default */
      }
      throw new ApiError(res.status, detail);
    }
    return (await res.json()) as T;
  } catch (err) {
    if (err instanceof ApiError) throw err;
    const msg = err instanceof Error ? err.message : "";
    if (!msg || msg.toLowerCase().includes("failed to fetch") || msg.toLowerCase().includes("networkerror")) {
      throw new ApiError(0, "Backend unreachable. If the server was sleeping (Render cold-start), please wait 15 seconds and retry.");
    }
    throw new ApiError(0, msg);
  }
}



export interface IngestStatus {
  loaded: boolean;
  last_ingested: string | null;
  bank: number;
  cdr: number;
  ipdr: number;
  complaints: number;
  files_ok: number;
  files_skipped: number;
  errors: string[];
}

export interface Summary {
  bank_records: number;
  cdr_records: number;
  ipdr_records: number;
  complaints: number;
  files: { ok: string[]; skipped: string[]; errors: string[] };
  entities: {
    phones: number;
    accounts: number;
    upi_ids: number;
    imeis: number;
    imsis: number;
    ips: number;
  };
  top_risk_accounts: { account_no: string; score: number; flags: string[] }[];
  top_risk_phones: { phone: string; score: number; flags: string[] }[];
  last_ingested: string | null;
}

export interface Alert {
  transaction_id: string;
  sender_customer_id: string;
  amount_usd: number;
  risk_score: number;
  risk_band: string;
  rules_fired: string;
  ncrp_states: string[];
  bank: string;
  mode?: string;
  customer_name?: string;
  customer_phone?: string;
  date?: string;
  time?: string;
  explain_plain?: string;
}

export interface TimelineEvent {
  ts: number | null;
  date: string;
  kind: "bank" | "cdr" | "ipdr" | "complaint";
  entity: string;
  detail?: string;
  label?: string;
  record_id?: string;
}

export interface EgoNet {
  node: string;
  nodes: { id: string; degree: number; risk?: number; kind?: string }[];
  edges: {
    source: string;
    target: string;
    weight: number;
    seconds?: number;
    amount?: number;
    kind?: string;
    evidence?: string[];
  }[];
  filtered?: boolean;
  kept?: number;
  total?: number;
  fallback?: boolean;
  window_min?: number;
}

export interface RiskBreakdown {
  rule: string;
  points: number;
  reason: string;
}

export interface EntityIntelligence {
  kind: string;
  value: string;
  risk_score: number;
  risk_band: string;
  confidence: number;
  flags: string[];
  breakdown: RiskBreakdown[];
  counts: {
    transactions: number;
    calls: number;
    sms: number;
    ip_sessions: number;
  };
  volumes: {
    credit: number;
    debit: number;
    avg_amount: number;
    max_amount: number;
    txns: number;
    round_amounts: number;
  };
  activity: { first: string | null; last: string | null };
  links: Record<string, string[]>;
  patterns: { label: string; evidence: string }[];
  ncrp: { account_no?: string; police_station?: string; state?: string }[];
  records: {
    kind: string;
    ts: number | null;
    date: string;
    time: string;
    label: string;
    amount: number | null;
  }[];
}

export interface RelationshipIntel {
  a: string;
  b: string;
  relationship: "call" | "money" | "mixed" | null;
  calls?: {
    count: number;
    total_seconds: number;
    avg_seconds: number;
    max_seconds: number;
    first: string | null;
    last: string | null;
    by_type: Record<string, number>;
  } | null;
  money?: {
    legs: {
      direction: string;
      count: number;
      total: number;
      avg: number;
      max: number;
      round_amounts: number;
      modes: Record<string, number>;
      first: string | null;
      last: string | null;
    }[];
    net: number;
  } | null;
  coincidences: {
    txn_ts: string;
    amount: number;
    mode: string;
    calls_in_window: { ts: string; type: string; b: string }[];
    window_min: number;
  }[];
  indicators: { code: string; label: string; evidence: string }[];
  evidence: string[];
}

export interface Phone {
  phone: string;
  records: number;
  contacts: number;
  unique_contacts: number;
  score: number;
  flags: string[];
}

export interface Account {
  account_no: string;
  bank: string;
  txns: number;
  credit: number;
  debit: number;
  score: number;
  flags: string[];
}

export interface Payout {
  txn_id: string;
  account_no: string;
  date: string;
  amount: number;
  mode: string;
  phone: string;
  narration: string;
}

export interface Payouts {
  rapid: { account_no: string; count: number; window_min: number; first: string; last: string }[];
  round: Payout[];
}

export interface UploadResult {
  detail: string;
  files: { name: string }[];
  skipped: string[];
  errors: string[];
  bank: number;
  cdr: number;
  ipdr: number;
  complaints: number;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
  user: { username: string; role: string };
}

export interface SearchResult {
  query: string;
  total: number;
  results: {
    kind: string;
    key: string;
    label: string;
    account_no?: string;
    amount?: number;
    date?: string;
    txns?: number;
    bank?: string;
  }[];
}

export interface MoneyGraph {
  nodes: { id: string; kind: string }[];
  edges: { source: string; target: string; weight: number; amount: number }[];
  stats: { nodes: number; edges: number };
}

export interface FlowPatterns {
  circular: { accounts: string[]; length: number; total_flow: number; min_leg: number }[];
  rapid_in_out: {
    account_no: string;
    in_ts: number;
    out_ts: number;
    window_min: number;
    in_amount: number;
    out_amount: number;
    in_txn: string;
    out_txn: string;
    mode: string;
  }[];
}

export interface MlOutliers {
  fitted: boolean;
  method: string;
  accounts: {
    account_no: string;
    txn_count: number;
    total_credit: number;
    total_debit: number;
    avg_amount: number;
    max_amount: number;
    counterparties: number;
    phones: number;
    round_share: number;
    night_share: number;
    rapid_payouts: number;
  }[];
}

export interface CoincidenceHit {
  phone: string;
  account_no: string;
  txn_date: string;
  mode: string;
  amount: number;
  phone_cdr_records: number;
  window_count: number;
}

export interface FusedLinkedCall {
  cdr_id: string;
  ts: number | null;
  type: string;
  dur: number | null;
  bts: string;
  phone: string;
}

export interface FusedLinkedSession {
  ipdr_id: string;
  ts: number | null;
  ip: string;
  dur: number | null;
}

export interface FusedRow {
  transaction_id: string;
  date: string;
  time: string;
  ts: number | null;
  mode: string;
  amount: number | null;
  direction: string;
  account_no: string;
  account_name: string;
  bank: string;
  counterparty_name: string;
  counterparty_bank: string;
  receiver_account: string;
  sender_phone: string;
  receiver_phone: string;
  linked_calls: FusedLinkedCall[];
  call_count: number;
  linked_sessions: FusedLinkedSession[];
  ipdr_count: number;
  ncrp: boolean;
  risk_score?: number | null;
  risk_band?: string | null;
  explain_plain?: string;
  rules_fired?: string;
  ncrp_states?: string[];
}

export interface FusedPage {
  total: number;
  offset: number;
  limit: number;
  rows: FusedRow[];
}


export interface CopilotGraphEdge {
  source: string;
  target: string;
  hop_distance: number;
  edge_type: string;
  amount?: number;
  timestamp?: string;
  tx_id?: string;
  mode?: string;
  cdr_id?: string;
  bts?: string;
  call_type?: string;
  delta_sec?: number;
}

export interface CopilotTreeNode {
  id: string;
  type: string;
  name: string;
  phone: string | null;
  hop_distance: number;
}

export interface CopilotTreeCall {
  cdr_id: string;
  call_time: string;
  duration_sec: number;
  call_type: string;
  bts: string;
  a: string;
  b: string;
}

export interface CopilotTreeLayer {
  layer: number;
  label: string;
  entities: CopilotTreeNode[];
  transactions: {
    txn_id: string;
    amount: number;
    timestamp: string;
    mode: string;
    sender: string;
    receiver: string;
    sender_phone: string;
    receiver_phone: string;
  }[];
  phones: { phone: string; calls: CopilotTreeCall[] }[];
}

export interface LinkingTree {
  entity_id?: string;
  root?: string;
  start_node?: string;
  found: boolean;
  max_hops: number;
  total_nodes?: number;
  total_edges?: number;
  nodes?: CopilotTreeNode[];
  edges?: CopilotGraphEdge[];
  layers: CopilotTreeLayer[];
}

export interface CopilotRecord {
  [key: string]: string | number | null;
}

export interface EntityResolution {
  entity_id: string;
  entity_type: string;
  resolved: boolean;
}

export interface InvestigationSummary {
  found_transactions: number;
  total_amount: number;
  highest_risk: number;
  primary_account: string;
  common_phone: string;
  linked_ips: number;
  linked_beneficiaries: number;
  top_receiver: string;
  narrative: string;
}

export interface CopilotMetrics {
  records: number;
  total_amount: number;
  accounts: number;
  phones: number;
  ips: number;
  beneficiaries: number;
  highest_risk: number;
  avg_risk: number;
}

export interface CopilotInsight {
  title: string;
  detail: string;
  severity: string;
}

export interface CopilotSuggestion {
  action: string;
  target: string;
  why: string;
  query: string;
}

export interface CopilotRetrievedEvidence {
  table: string;
  id: string;
  snippet: string;
}

export interface CopilotQueryResult {
  query: string;
  intent: string;
  generated_sql: string;
  execution_success: boolean;
  row_count: number;
  records: CopilotRecord[];
  graph_traversal: LinkingTree | null;
  linking_tree: LinkingTree | null;
  chain_of_thought: { step: number; title: string; content: string }[];
  executive_summary: string;
  entity_resolution: EntityResolution;
  investigation_summary: InvestigationSummary;
  metrics: CopilotMetrics;
  insights: CopilotInsight[];
  suggestions: CopilotSuggestion[];
  explanation: string[];
  mode?: "sql" | "general" | "deterministic";
  llm_provider?: string;
  llm_model?: string;
  llm_latency_ms?: number;
  general_answer?: string;
  answer?: string;
  explainability?: string;
  retrieved_evidence?: CopilotRetrievedEvidence[];
}

export interface CopilotStats {
  dataset_source: string;
  tables: {
    bank_transactions: number;
    cdr_records: number;
    ipdr_records: number;
    bank_cdr_links: number;
    cdr_ipdr_links: number;
    anomaly_records: number;
    complaints: number;
    subscribers: number;
  };
  graph_nodes: number;
  graph_edges: number;
  max_graph_hops: number;
}

export interface CopilotSchemaTable {
  name: string;
  columns: { name: string; type: string }[];
}

export interface CopilotClusterSummary {
  entity_id: string;
  total_entities_in_cluster: number;
  graph_analysis: LinkingTree;
  executive_summary: string;
}

export interface LlmTreeNode {
  id: string;
  kind: string;
  label: string;
  hop_distance: number;
  attrs: Record<string, string | number>;
  risk: number;
  role?: string;
  suspicion?: string;
}

export interface LlmTreeEdge {
  source: string;
  target: string;
  kind: string;
  amount: number;
  duration: number;
  reason?: string;
}

export interface LlmTreeResult {
  root: string;
  max_hops: number;
  nodes: LlmTreeNode[];
  edges: LlmTreeEdge[];
  narrative: string | null;
  llm_provider: string | null;
  annotated: boolean;
  graph: { nodes: number; edges: number; found: boolean };
}

export interface InvestigationFinding {
  id: number;
  kind: string;
  title: string;
  detail: string;
  severity: string;
  created: string;
}

export interface Investigation {
  id: number;
  title: string;
  notes: string;
  status: string;
  created: string;
  updated: string;
  findings: InvestigationFinding[];
}

export interface InvestigationTreeLeg {
  transaction_id: string;
  risk_score: number;
  risk_band: string;
  rules_fired: string[];
  evidence: string[];
  receiver_account?: string | null;
}

export interface InvestigationTree {
  investigation: Omit<Investigation, "findings">;
  findings: InvestigationFinding[];
  flagged_transactions: InvestigationTreeLeg[];
}

export interface EventDossier {
  event_id: string;
  source_type: string;
  timestamp: string | null;
  primary_entity: Record<string, any>;
  source_record: Record<string, any>;
  risk: Record<string, any>;
  identities: Array<{ type: string; value: string }>;
  correlations: Array<{
    type: string;
    time_diff_sec: number;
    description: string;
    id: string;
    ts: string;
  }>;
  evidence: Array<{ rule: string; points: number; reason: string }>;
}

export const api = {
  dossier: (kind: string, value: string) => request<DossierIntelligence>(`/dossier/${kind}/${encodeURIComponent(value)}`),
  eventDossier: (sourceType: string, eventId: string) => request<EventDossier>(`/timeline/event/${sourceType}/${encodeURIComponent(eventId)}`),
  login: (username: string, password: string) =>
    request<AuthResponse>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),
  register: (username: string, password: string) =>
    request<AuthResponse>("/auth/register", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),

  me: () => request<{ user: { username: string; role: string } }>("/auth/me"),
  health: () => request<{ status: string; loaded: boolean; last_ingested: string | null }>("/health"),
  status: () => request<IngestStatus>("/ingest/status"),
  summary: () => request<Summary>("/summary"),
  alerts: (minRisk = 50, limit = 200) =>
    request<{ results: Alert[]; total: number }>(`/scoring/alerts?min_risk=${minRisk}&limit=${limit}`),
  accounts: (minScore = 0, limit = 50) =>
    request<{ accounts: Account[] }>(`/accounts?min_score=${minScore}&limit=${limit}`),
  phones: (minScore = 0, limit = 50) =>
    request<{ phones: Phone[] }>(`/phones?min_score=${minScore}&limit=${limit}`),
  timeline: (limit = 2000) => request<{ count: number; events: TimelineEvent[] }>(`/timeline?limit=${limit}`),
  egonet: (phone: string, depth = 1, mode = "evidence") =>
    request<EgoNet>(
      `/phone/${encodeURIComponent(phone)}/egonet?depth=${depth}&mode=${mode}`
    ),
  entity: (kind: string, value: string) =>
    request<EntityIntelligence>(
      `/entity/${encodeURIComponent(kind)}/${encodeURIComponent(value)}`
    ),
  relationship: (a: string, b: string) =>
    request<RelationshipIntel>(
      `/relationship/${encodeURIComponent(a)}/${encodeURIComponent(b)}`
    ),
  deviceGraph: (phone: string) =>
    request<EgoNet>(`/graph/device?phone=${encodeURIComponent(phone)}`),
  ipGraph: (phone: string) =>
    request<EgoNet>(`/graph/ip?phone=${encodeURIComponent(phone)}`),
  payouts: () => request<Payouts>("/payouts"),
  coincidence: (windowSec = 3600, limit = 100) =>
    request<{ window_sec: number; hits: CoincidenceHit[]; total: number }>(
      `/coincidence?window_sec=${windowSec}&limit=${limit}`
    ),
  moneyGraph: (minAmount = 0, limit = 300) =>
    request<MoneyGraph>(`/graph/money?min_amount=${minAmount}&limit=${limit}`),
  accountPhoneGraph: (limit = 200) => request<MoneyGraph>(`/graph/account-phone?limit=${limit}`),
  centralPhones: (top = 15) => request<{ phones: { phone: string; degree: number; calls: number }[] }>(`/graph/central-phones?top=${top}`),
  flowPatterns: (minAmount = 10000) =>
    request<FlowPatterns>(`/flows/patterns?min_amount=${minAmount}`),
  mlOutliers: (contamination = 0.05) =>
    request<MlOutliers>(`/ml/outliers?contamination=${contamination}`),
  search: (q: string, limit = 50) =>
    request<SearchResult>(`/search?q=${encodeURIComponent(q)}&limit=${limit}`),
  ingestFolder: (folder: string) =>
    request<{ files_ok: number; errors: string[] }>("/ingest", {
      method: "POST",
      body: JSON.stringify({ folder }),
    }),
  pipelineStatus: () => request<PipelineStatus>("/ingest/pipeline-status"),
  clearData: () => request<{ cleared: boolean }>("/ingest", { method: "DELETE" }),
  uploadFiles: (files: File[]) => {
    const fd = new FormData();
    files.forEach((f) => fd.append("files", f));
    return request<UploadResult>("/upload/parse-multi", { method: "POST", body: fd });
  },
  downloadReport: async (): Promise<void> => {
    await downloadBlob("/report", "STR_Report.pdf");
  },
  transactionReport: async (transactionId: string): Promise<void> => {
    await downloadBlob(
      `/report/transaction/${encodeURIComponent(transactionId)}`,
      `STR_${transactionId}.pdf`
    );
  },
  downloadEntityReport: async (kind: string, value: string): Promise<void> => {
    await downloadBlob(
      `/report/entity/${encodeURIComponent(kind)}/${encodeURIComponent(value)}`,
      `STR_${kind}_${value.replace(/[^a-zA-Z0-9]/g, "_").slice(0, 32)}.pdf`
    );
  },
  fused: (offset = 0, limit = 25, q = "", account = "", mode = "", riskAnnotate = false) => {
    const params = new URLSearchParams({ offset: String(offset), limit: String(limit) });
    if (q) params.set("q", q);
    if (account) params.set("account", account);
    if (mode && mode !== "all") params.set("mode", mode);
    if (riskAnnotate) params.set("risk_annotate", "1");
    return request<FusedPage>(`/data/fused?${params.toString()}`);
  },

  fusedCsv: async (q = "", account = "", mode = ""): Promise<void> => {
    const params = new URLSearchParams();
    if (q) params.set("q", q);
    if (account) params.set("account", account);
    if (mode && mode !== "all") params.set("mode", mode);
    const token = bearerToken();
    const res = await fetch(
      apiBaseUrl() + `/data/fused.csv?${params.toString()}`,
      { headers: token ? { Authorization: `Bearer ${token}` } : {} }
    );
    if (!res.ok) {
      let detail = `HTTP ${res.status}`;
      try {
        const body = await res.json();
        detail = body.detail || detail;
      } catch {
        /* keep default */
      }
      throw new ApiError(res.status, detail);
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "fused_records.csv";
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  },

  copilotStats: () => request<CopilotStats>("/api/v1/copilot/stats"),
  copilotSchema: () =>
    request<{ database: string; tables: CopilotSchemaTable[] }>("/api/v1/copilot/schema"),
  copilotQuery: (query: string) =>
    request<CopilotQueryResult>("/api/v1/copilot/query", {
      method: "POST",
      body: JSON.stringify({ query }),
    }),
  copilotTree: (entityId: string, maxHops = 3) =>
    request<LinkingTree>(
      `/api/v1/copilot/tree/${encodeURIComponent(entityId)}?max_hops=${maxHops}`
    ),
  copilotGraph: (entityId: string, maxHops = 3) =>
    request<LinkingTree>(
      `/api/v1/copilot/graph/${encodeURIComponent(entityId)}?max_hops=${maxHops}`
    ),
  copilotClusterSummary: (entityIds: string[]) =>
    request<CopilotClusterSummary>("/api/v1/copilot/cluster-summary", {
      method: "POST",
      body: JSON.stringify({ entity_ids: entityIds }),
    }),
  copilotGraphBuild: (entityId: string, maxHops = 3) =>
    request<any>("/api/v1/copilot/graph/build", {
      method: "POST",
      body: JSON.stringify({ entity_id: entityId, max_hops: maxHops }),
    }),
  copilotInsightsGenerate: (payload: any) =>
    request<any>("/api/v1/copilot/insights/generate", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  copilotEntityDetails: (entityId: string) =>
    request<any>(`/api/v1/copilot/entity/${encodeURIComponent(entityId)}/details`),
  copilotLlmTree: (entityId: string, maxHops = 3) =>
    request<LlmTreeResult>("/api/v1/copilot/llm-tree", {
      method: "POST",
      body: JSON.stringify({ entity_id: entityId, max_hops: maxHops }),
    }),

  logout: () =>
    request<{ detail: string }>("/auth/logout", { method: "POST" }),
  changePassword: (currentPassword: string, newPassword: string) =>
    request<{ detail: string }>("/auth/change-password", {
      method: "POST",
      body: JSON.stringify({
        current_password: currentPassword,
        new_password: newPassword,
      }),
    }),
  investigations: () => request<{ investigations: Investigation[] }>("/investigations"),
  investigation: (id: number) =>
    request<{ investigation: Investigation }>(`/investigations/${id}`),
  createInvestigation: (title: string, notes = "") =>
    request<{ investigation: Investigation }>("/investigations", {
      method: "POST",
      body: JSON.stringify({ title, notes }),
    }),
  updateInvestigation: (id: number, patch: { title?: string; notes?: string }) =>
    request<{ investigation: Investigation }>(`/investigations/${id}`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    }),
  deleteInvestigation: (id: number) =>
    request<{ deleted: number }>(`/investigations/${id}`, { method: "DELETE" }),
  addFinding: (
    id: number,
    finding: { kind: string; title: string; detail?: string; severity?: string }
  ) =>
    request<{ finding: InvestigationFinding }>(`/investigations/${id}/findings`, {
      method: "POST",
      body: JSON.stringify(finding),
    }),
  investigationTree: (id: number) =>
    request<InvestigationTree>(`/investigations/${id}/tree`),
};

async function downloadBlob(path: string, filename: string): Promise<void> {
  const token = bearerToken();
  const res = await fetch(apiBaseUrl() + path, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      detail = body.detail || detail;
    } catch {
      /* keep default */
    }
    throw new ApiError(res.status, detail);
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
