// Relativo por padrao: casa com o basePath "/smartmoney" do next.config.ts,
// que reescreve /smartmoney/api/* pro backend (porta 8100) no proprio
// servidor do Next — funciona igual acessando direto (:3100/smartmoney/...)
// ou via proxy do Hub (:8000/smartmoney/...) ou pelo dominio publico ngrok.
const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "/smartmoney";

async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`API ${path} -> ${res.status}`);
  }
  return res.json() as Promise<T>;
}

async function apiPost<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { method: "POST" });
  if (!res.ok) {
    throw new Error(`API ${path} -> ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export interface Fund {
  id: number;
  cnpj: string;
  name: string;
  fund_class_type: string | null;
  net_asset_value: number | null;
  n_shareholders: number | null;
  financials_ref_date: string | null;
  return_pct_12m: number | null;
  return_pct_mtd: number | null;
  return_pct_ytd: number | null;
}

export type FundSortField =
  | "name"
  | "net_asset_value"
  | "n_shareholders"
  | "financials_ref_date"
  | "return_pct_12m"
  | "return_pct_mtd"
  | "return_pct_ytd";

export interface FundFilters {
  search?: string;
  minNetAssetValue?: number;
  maxNetAssetValue?: number;
  minShareholders?: number;
  maxShareholders?: number;
  refDateFrom?: string;
  refDateTo?: string;
  minReturnPct?: number;
  maxReturnPct?: number;
  sortBy?: FundSortField;
  sortDir?: "asc" | "desc";
  limit?: number;
}

export interface Holding {
  asset_id: number;
  ticker: string;
  company_name: string | null;
  quantity: number;
  market_value: number;
  pct_of_equity_book: number | null;
  ref_date: string;
}

export interface Movement {
  asset_id: number;
  ticker: string;
  classification: string;
  ref_date: string;
  prior_ref_date: string | null;
  qty_current: number;
  qty_prior: number;
  value_current: number;
  value_prior: number;
  qty_delta: number;
  value_delta: number;
  pct_delta: number | null;
}

export interface AssetHistoryPoint {
  ref_date: string;
  quantity: number;
  market_value: number;
  classification: string | null;
  qty_delta: number | null;
}

export interface Asset {
  id: number;
  ticker: string;
  company_name: string | null;
  asset_type: "equity" | "bdr";
  total_market_value: number | null;
  financials_ref_date: string | null;
  return_pct_12m: number | null;
}

export type AssetSortField = "ticker" | "total_market_value" | "return_pct_12m";

export interface AssetFilters {
  search?: string;
  assetType?: "equity" | "bdr" | "";
  minTotalMarketValue?: number;
  minReturnPct?: number;
  maxReturnPct?: number;
  sortBy?: AssetSortField;
  sortDir?: "asc" | "desc";
  limit?: number;
}

export interface AssetHolder {
  fund_id: number;
  fund_name: string;
  fund_cnpj: string;
  quantity: number;
  market_value: number;
  classification: string | null;
  qty_delta: number | null;
  ref_date: string;
  fund_net_asset_value: number | null;
  fund_n_shareholders: number | null;
}

export interface AssetTimelinePoint {
  ref_date: string;
  n_holders: number;
  total_quantity: number;
  total_value: number;
}

export interface RankingRow {
  asset_id: number;
  ticker: string;
  company_name: string | null;
  n_funds: number;
  net_qty_delta: number;
  net_value_delta: number;
}

// Consensus is a snapshot ranking (who holds the most), not a movement
// ranking — it has no delta, just current aggregate exposure.
export interface ConsensusRow {
  asset_id: number;
  ticker: string;
  company_name: string | null;
  n_funds: number;
  total_value: number;
}

export interface TopPerformerRow {
  fund_id: number;
  fund_name: string | null;
  fund_cnpj: string | null;
  pct_return: number;
  first_date: string;
  last_date: string;
  net_asset_value: number | null;
  n_shareholders: number | null;
  financials_ref_date: string | null;
}

export interface PerformanceMovement {
  asset_id: number;
  ticker: string;
  company_name: string | null;
  classification: string;
  qty_current: number;
  qty_prior: number;
  qty_delta: number;
  value_current: number;
  value_delta: number;
  pct_delta: number | null;
  pct_of_equity_book: number | null;
}

export interface Buyback {
  id: number;
  cnpj: string;
  company_name: string;
  ticker: string | null;
  declared_at: string;
  deadline: string | null;
  status: string;
  operation_type: string | null;
  reason: string | null;
  purpose: string | null;
  qty_common_shares: number | null;
  qty_preferred_shares: number | null;
}

export type BuybackSortField = "ticker" | "company_name" | "declared_at" | "deadline" | "qty_common_shares" | "qty_preferred_shares";

export interface BuybackFilters {
  search?: string;
  status?: "Em Andamento" | "Encerrado" | "";
  sortBy?: BuybackSortField;
  sortDir?: "asc" | "desc";
  limit?: number;
}

export interface InsiderTrade {
  id: number;
  cnpj_companhia: string;
  company_name: string;
  ticker: string | null;
  data_referencia: string;
  tipo_empresa: string | null;
  empresa: string | null;
  tipo_cargo: string | null;
  tipo_movimentacao: string;
  direction: "COMPRA" | "VENDA" | null;
  tipo_operacao: string | null;
  tipo_ativo: string | null;
  intermediario: string | null;
  data_movimentacao: string | null;
  quantidade: number | null;
  preco_unitario: number | null;
  volume: number | null;
}

export type InsiderSortField = "data_movimentacao" | "ticker" | "company_name" | "quantidade" | "volume" | "preco_unitario";

export interface InsiderFilters {
  search?: string;
  direction?: "COMPRA" | "VENDA" | "";
  cargo?: string;
  dateFrom?: string;
  dateTo?: string;
  sortBy?: InsiderSortField;
  sortDir?: "asc" | "desc";
  limit?: number;
}

export interface PricePoint {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number | null;
}

export interface Alert {
  id: number;
  type: string;
  severity: string;
  title: string;
  message: string | null;
  entity_type: string | null;
  entity_id: number | null;
  ref_date: string;
  is_read: boolean;
  created_at: string;
}

export interface FlowMonth {
  ref_date: string;
  total_value_bought: number;
  n_funds_buying: number;
  n_funds_active: number;
  pct_funds_buying: number | null;
  value_vs_avg: number;
  funds_vs_avg: number;
  coordination_score: number;
}

export interface FlowEvolution {
  months: FlowMonth[];
  avg_total_value_bought: number | null;
  avg_n_funds_buying: number | null;
}

export interface FundPerformance {
  ref_date: string | null;
  principais_alteracoes: PerformanceMovement[];
  top_posicoes_compradas: PerformanceMovement[];
  o_que_aumentou: PerformanceMovement[];
  o_que_diminuiu: PerformanceMovement[];
  novas_posicoes: PerformanceMovement[];
  zeragens: PerformanceMovement[];
  evolucao_posicoes_compradas: { ref_date: string; total_bought: number; n_positions: number }[];
}

export interface QuotaPoint {
  ref_date: string;
  quota_value: number;
  indexed: number | null;
}

export interface FundQuotaHistory {
  points: QuotaPoint[];
  window_start: string | null;
}

function buildQuery(params: Record<string, string | number | undefined>): string {
  const q = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") q.set(key, String(value));
  }
  return q.toString();
}

export const api = {
  searchFunds: (filters: FundFilters = {}) =>
    apiGet<Fund[]>(
      `/api/funds?${buildQuery({
        search: filters.search,
        min_net_asset_value: filters.minNetAssetValue,
        max_net_asset_value: filters.maxNetAssetValue,
        min_shareholders: filters.minShareholders,
        max_shareholders: filters.maxShareholders,
        ref_date_from: filters.refDateFrom,
        ref_date_to: filters.refDateTo,
        min_return_pct: filters.minReturnPct,
        max_return_pct: filters.maxReturnPct,
        sort_by: filters.sortBy,
        sort_dir: filters.sortDir,
        limit: filters.limit,
      })}`
    ),
  getFund: (id: number) => apiGet<Fund>(`/api/funds/${id}`),
  getFundHoldings: (id: number) => apiGet<Holding[]>(`/api/funds/${id}/holdings`),
  getFundMovements: (id: number) => apiGet<Movement[]>(`/api/funds/${id}/movements`),
  getFundAssetHistory: (id: number, assetId: number) =>
    apiGet<AssetHistoryPoint[]>(`/api/funds/${id}/history?asset_id=${assetId}`),
  getFundPerformance: (id: number) => apiGet<FundPerformance>(`/api/funds/${id}/performance`),
  getFundQuotaHistory: (id: number, years = 20) => apiGet<FundQuotaHistory>(`/api/funds/${id}/quota-history?years=${years}`),

  getTopPerformers: (years: number = 20) =>
    apiGet<{ window_years: number; as_of: string | null; rows: TopPerformerRow[] }>(
      `/api/rankings/top-performers?years=${years}`
    ),

  searchAssets: (filters: AssetFilters = {}) =>
    apiGet<Asset[]>(
      `/api/assets?${buildQuery({
        search: filters.search,
        asset_type: filters.assetType,
        min_total_market_value: filters.minTotalMarketValue,
        min_return_pct: filters.minReturnPct,
        max_return_pct: filters.maxReturnPct,
        sort_by: filters.sortBy,
        sort_dir: filters.sortDir,
        limit: filters.limit,
      })}`
    ),
  getAsset: (id: number) => apiGet<Asset>(`/api/assets/${id}`),
  getAssetHolders: (id: number, includeClosed = false) =>
    apiGet<AssetHolder[]>(`/api/assets/${id}/holders?${buildQuery({ include_closed: includeClosed ? "true" : undefined })}`),
  getAssetMovements: (id: number) =>
    apiGet<{
      ref_date: string;
      net_qty_delta: number;
      net_value_delta: number;
      n_funds_buying: number;
      n_funds_selling: number;
      movements: unknown[];
    }>(`/api/assets/${id}/movements`),
  getAssetTimeline: (id: number) => apiGet<AssetTimelinePoint[]>(`/api/assets/${id}/timeline`),

  getRanking: (kind: string) => apiGet<{ ref_date: string; rows: RankingRow[] }>(`/api/rankings/${kind}`),
  getConsensus: () => apiGet<{ ref_date: string; rows: ConsensusRow[] }>(`/api/rankings/consensus/top`),

  getBuybacks: (filters: BuybackFilters = {}) =>
    apiGet<Buyback[]>(
      `/api/buybacks?${buildQuery({
        search: filters.search,
        status: filters.status,
        sort_by: filters.sortBy,
        sort_dir: filters.sortDir,
        limit: filters.limit,
      })}`
    ),

  getInsiderTrades: (filters: InsiderFilters = {}) =>
    apiGet<InsiderTrade[]>(
      `/api/insiders?${buildQuery({
        search: filters.search,
        direction: filters.direction,
        cargo: filters.cargo,
        date_from: filters.dateFrom,
        date_to: filters.dateTo,
        sort_by: filters.sortBy,
        sort_dir: filters.sortDir,
        limit: filters.limit,
      })}`
    ),
  getInsiderCargos: () => apiGet<string[]>(`/api/insiders/cargos`),

  getAlerts: (onlyUnread = false, type = "") =>
    apiGet<Alert[]>(`/api/alerts?${buildQuery({ only_unread: onlyUnread ? "true" : undefined, type, limit: 200 })}`),
  getUnreadAlertCount: () => apiGet<{ unread: number }>(`/api/alerts/unread-count`),
  markAlertRead: (id: number) => apiPost<Alert>(`/api/alerts/${id}/read`),
  markAllAlertsRead: () => apiPost<{ ok: boolean }>(`/api/alerts/read-all`),

  getFlowEvolution: () => apiGet<FlowEvolution>(`/api/evolution/flow`),

  getPriceHistory: (ticker: string, years = 10) =>
    apiGet<PricePoint[]>(`/api/market/price-history?${buildQuery({ ticker, years })}`),
};
