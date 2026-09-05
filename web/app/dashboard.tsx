'use client';

import { useEffect, useState } from 'react';
import {
  Activity,
  BrainCircuit,
  CandlestickChart,
  CircleAlert,
  Clock3,
  Database,
  Gauge,
  Layers3,
  ShieldAlert,
} from 'lucide-react';
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  XAxis,
  YAxis,
} from 'recharts';

import dashboardJson from './dashboard-data.json';
import { Badge } from '@/components/ui/badge';
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import {
  ChartConfig,
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
} from '@/components/ui/chart';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';

type Direction = 'LONG' | 'SHORT' | 'WAIT';

type FrameData = {
  timeframe: string;
  horizon_label: string;
  lookback_bars: number;
  horizon_bars: number;
  as_of: string;
  current_close: number;
  upside_probability: number;
  volatility_amplification_probability: number;
  median_return: number;
  mean_return: number;
  inference_seconds: number;
  signal: {
    label: Direction;
    direction: number;
    entry_limit: number;
    stop_loss: number;
    take_profit_1: number;
    take_profit_2: number;
  };
  history: Array<{
    timestamp: string;
    close: number;
    high: number;
    low: number;
    volume: number;
  }>;
  forecast: Array<{
    timestamp: string;
    mean: number;
    p10: number;
    p90: number;
  }>;
};

type Backtest = {
  label: string;
  return: number;
  gross_pnl: number;
  fees: number;
  funding: number;
  trades: number;
  profit_factor: number | null;
  status: string;
};

type LeverageResult = {
  total_return: number;
  max_drawdown: number;
  capital_index: number;
  trades: number;
  liquidations: number;
};

type DashboardData = {
  research_only: boolean;
  generated_at: string;
  market: string;
  model: string;
  sampling: {
    paths: number;
    temperature: number;
    top_p: number;
    threshold_bps: number;
  };
  costs: {
    entry_fee: number;
    exit_fee: number;
    long_funding_per_8h: number;
    short_funding: number;
  };
  consensus: {
    label: 'LONG' | 'SHORT' | 'MIXED';
    weighted_upside_probability: number;
    agreement: number;
    warning: string;
  };
  timeframes: FrameData[];
  backtests: Backtest[];
  leverage_experiment?: {
    warning: string;
    baseline_1x: LeverageResult;
    dynamic_leverage: LeverageResult;
  } | null;
};

const data = dashboardJson as DashboardData;

const chartConfig = {
  history: { label: 'Lịch sử', color: '#d8dee9' },
  forecast: { label: 'Dự báo trung bình', color: '#71e7cf' },
  range: { label: 'Khoảng P10–P90', color: '#9370ff' },
} satisfies ChartConfig;

const formatPrice = (value: number) =>
  new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: value >= 10_000 ? 0 : 2,
  }).format(value);

const formatPercent = (value: number, digits = 2) =>
  `${value >= 0 ? '+' : ''}${(value * 100).toFixed(digits)}%`;

const timeLabel = (value: string) =>
  new Intl.DateTimeFormat('vi-VN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
    timeZone: 'UTC',
  }).format(new Date(value));

const directionClass: Record<string, string> = {
  LONG: 'signal-long',
  SHORT: 'signal-short',
  WAIT: 'signal-wait',
  MIXED: 'signal-mixed',
};

function DirectionBadge({ value }: { value: string }) {
  return (
    <span className={`signal-pill ${directionClass[value] ?? 'signal-mixed'}`}>
      <span className="signal-dot" />
      {value}
    </span>
  );
}

type ChartRow = {
  timestamp: string;
  history?: number;
  forecast?: number;
  range?: [number, number];
};

function forecastChart(frame: FrameData): ChartRow[] {
  const rows: ChartRow[] = frame.history.map((point) => ({
    timestamp: point.timestamp,
    history: point.close,
  }));
  const lastHistory = frame.history.at(-1);
  if (lastHistory) {
    rows[rows.length - 1] = {
      ...rows[rows.length - 1],
      forecast: lastHistory.close,
      range: [lastHistory.close, lastHistory.close],
    };
  }
  return [
    ...rows,
    ...frame.forecast.map((point) => ({
      timestamp: point.timestamp,
      forecast: point.mean,
      range: [point.p10, point.p90] as [number, number],
    })),
  ];
}

function MetricCard({
  label,
  value,
  note,
  icon: Icon,
}: {
  label: string;
  value: string;
  note: string;
  icon: typeof Gauge;
}) {
  return (
    <Card className="metric-card" size="sm">
      <CardHeader>
        <CardDescription className="metric-label">{label}</CardDescription>
        <CardAction>
          <Icon className="size-4 text-[var(--accent-cyan)]" />
        </CardAction>
      </CardHeader>
      <CardContent>
        <div className="metric-value">{value}</div>
        <p className="metric-note">{note}</p>
      </CardContent>
    </Card>
  );
}

function ForecastPanel({ frame }: { frame: FrameData }) {
  const chartRows = forecastChart(frame);
  const forecastStart = frame.forecast[0]?.timestamp;
  const signal = frame.signal;
  const active = signal.label !== 'WAIT';

  return (
    <div className="space-y-4">
      <div className="grid gap-3 md:grid-cols-3">
        <MetricCard
          label={`Xác suất tăng · ${frame.horizon_label}`}
          value={`${(frame.upside_probability * 100).toFixed(1)}%`}
          note={`${data.sampling.paths} đường lấy mẫu xác suất`}
          icon={Activity}
        />
        <MetricCard
          label="Khuếch đại biến động"
          value={`${(frame.volatility_amplification_probability * 100).toFixed(1)}%`}
          note="So với biến động context gần nhất"
          icon={Gauge}
        />
        <MetricCard
          label="Lợi suất dự báo trung vị"
          value={formatPercent(frame.median_return)}
          note={`${frame.lookback_bars} nến context · ${frame.inference_seconds.toFixed(1)}s GPU`}
          icon={BrainCircuit}
        />
      </div>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_290px]">
        <Card className="chart-card">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <CandlestickChart className="size-4 text-[var(--accent-cyan)]" />
              BTC/USDT · {frame.timeframe}
            </CardTitle>
            <CardDescription>
              Giá đóng cửa lịch sử, dự báo trung bình và vùng P10–P90
            </CardDescription>
            <CardAction>
              <DirectionBadge value={signal.label} />
            </CardAction>
          </CardHeader>
          <CardContent className="px-2 pb-1 sm:px-4">
            <ChartContainer config={chartConfig} className="h-[360px] w-full aspect-auto">
              <ComposedChart data={chartRows} margin={{ top: 12, right: 12, left: 4, bottom: 4 }}>
                <defs>
                  <linearGradient id={`range-${frame.timeframe}`} x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#9370ff" stopOpacity={0.3} />
                    <stop offset="100%" stopColor="#9370ff" stopOpacity={0.04} />
                  </linearGradient>
                </defs>
                <CartesianGrid vertical={false} strokeDasharray="3 5" />
                <XAxis
                  dataKey="timestamp"
                  tickFormatter={timeLabel}
                  minTickGap={42}
                  axisLine={false}
                  tickLine={false}
                />
                <YAxis
                  domain={['auto', 'auto']}
                  tickFormatter={(value) => `$${Math.round(Number(value) / 100) * 100}`}
                  width={68}
                  axisLine={false}
                  tickLine={false}
                />
                <ChartTooltip
                  content={
                    <ChartTooltipContent
                      labelFormatter={(_, payload) =>
                        payload?.[0]?.payload?.timestamp
                          ? `${timeLabel(payload[0].payload.timestamp)} UTC`
                          : ''
                      }
                      formatter={(value, name) => (
                        <div className="flex w-full min-w-48 items-center justify-between gap-5">
                          <span className="text-muted-foreground">{String(name)}</span>
                          <span className="font-mono font-semibold">
                            {Array.isArray(value)
                              ? `${formatPrice(Number(value[0]))} – ${formatPrice(Number(value[1]))}`
                              : formatPrice(Number(value))}
                          </span>
                        </div>
                      )}
                    />
                  }
                />
                <Area
                  type="monotone"
                  dataKey="range"
                  stroke="transparent"
                  fill={`url(#range-${frame.timeframe})`}
                  connectNulls={false}
                  name="P10–P90"
                />
                <Line
                  type="monotone"
                  dataKey="history"
                  stroke="var(--color-history)"
                  strokeWidth={1.7}
                  dot={false}
                  name="Lịch sử"
                />
                <Line
                  type="monotone"
                  dataKey="forecast"
                  stroke="var(--color-forecast)"
                  strokeWidth={2.4}
                  dot={false}
                  name="Dự báo"
                />
                {forecastStart ? (
                  <ReferenceLine
                    x={forecastStart}
                    stroke="#6b7280"
                    strokeDasharray="4 4"
                    label={{ value: 'INFER', fill: '#89909d', fontSize: 10, position: 'insideTopRight' }}
                  />
                ) : null}
              </ComposedChart>
            </ChartContainer>
          </CardContent>
        </Card>

        <Card className="order-card">
          <CardHeader>
            <CardTitle>Kế hoạch lệnh</CardTitle>
            <CardDescription>
              Bracket tham khảo từ mean path · chưa được phép live
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-5">
            <div className="flex items-center justify-between rounded-lg border border-white/8 bg-white/[0.025] p-3">
              <span className="text-xs uppercase tracking-[0.15em] text-muted-foreground">Trạng thái</span>
              <DirectionBadge value={signal.label} />
            </div>
            <div className={`order-levels ${active ? '' : 'opacity-45'}`}>
              <div><span>Entry limit</span><strong>{formatPrice(signal.entry_limit)}</strong></div>
              <div><span>Stop loss</span><strong className="text-[var(--accent-red)]">{formatPrice(signal.stop_loss)}</strong></div>
              <div><span>Take profit 1</span><strong className="text-[var(--accent-green)]">{formatPrice(signal.take_profit_1)}</strong></div>
              <div><span>Take profit 2</span><strong className="text-[var(--accent-green)]">{formatPrice(signal.take_profit_2)}</strong></div>
            </div>
            {!active ? (
              <div className="notice-inline">
                <CircleAlert className="size-4 shrink-0" />
                Dự báo chưa vượt ngưỡng {data.sampling.threshold_bps} bps, không tạo bracket.
              </div>
            ) : null}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function BacktestTable() {
  return (
    <Card className="section-card">
      <CardHeader>
        <CardTitle>Backtest sau chi phí</CardTitle>
        <CardDescription>
          Vốn khởi đầu được chuẩn hóa thành 100; notional tái tính theo equity sau mỗi lệnh.
        </CardDescription>
        <CardAction>
          <Badge variant="outline" className="border-white/10 text-muted-foreground">
            Compounded
          </Badge>
        </CardAction>
      </CardHeader>
      <CardContent className="overflow-x-auto px-0 sm:px-4">
        <table className="data-table min-w-[760px]">
          <thead>
            <tr>
              <th>Thử nghiệm</th>
              <th>Vốn cuối</th>
              <th>Lợi nhuận</th>
              <th>Gross PnL</th>
              <th>Phí + funding</th>
              <th>PF</th>
              <th>Lệnh</th>
            </tr>
          </thead>
          <tbody>
            {data.backtests.map((row) => (
              <tr key={`${row.label}-${row.status}`}>
                <td>
                  <div className="font-medium text-foreground">{row.label}</div>
                  <span className="table-tag">{row.status.replaceAll('_', ' ')}</span>
                </td>
                <td className="font-mono">{(100 * (1 + row.return)).toFixed(2)}</td>
                <td className={`font-mono ${row.return >= 0 ? 'positive' : 'negative'}`}>
                  {formatPercent(row.return)}
                </td>
                <td className="font-mono">{row.gross_pnl.toFixed(1)}</td>
                <td className="font-mono">{(row.fees + row.funding).toFixed(1)}</td>
                <td className="font-mono">{row.profit_factor?.toFixed(2) ?? '—'}</td>
                <td className="font-mono">{row.trades}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </CardContent>
    </Card>
  );
}

function LeverageComparison() {
  const experiment = data.leverage_experiment;
  if (!experiment) return null;
  const rows = [
    { label: 'Cơ sở', note: 'Cố định 1×', ...experiment.baseline_1x },
    { label: 'Confidence sizing', note: '1× / 1.5× / tối đa 2×', ...experiment.dynamic_leverage },
  ];
  return (
    <Card className="section-card">
      <CardHeader>
        <CardTitle>Đòn bẩy có điều kiện</CardTitle>
        <CardDescription>So sánh thăm dò trên forecast 4 giờ; không phải locked test mới.</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-3 md:grid-cols-2">
        {rows.map((row) => (
          <div className="leverage-row" key={row.label}>
            <div>
              <span className="eyebrow">{row.note}</span>
              <h3>{row.label}</h3>
            </div>
            <div className="leverage-number">{row.capital_index.toFixed(2)}</div>
            <div className="leverage-stats">
              <span>Lợi nhuận <strong className={row.total_return >= 0 ? 'positive' : 'negative'}>{formatPercent(row.total_return)}</strong></span>
              <span>Max DD <strong className="negative">{formatPercent(row.max_drawdown)}</strong></span>
              <span>{row.trades} lệnh · {row.liquidations} liquidation</span>
            </div>
          </div>
        ))}
        <div className="notice-inline md:col-span-2">
          <ShieldAlert className="size-4 shrink-0" />
          Độ lớn forecast chưa phải xác suất đã hiệu chỉnh. Chỉ bật leverage sau khi policy vượt validation và một forward test mới.
        </div>
      </CardContent>
    </Card>
  );
}

export default function Dashboard() {
  const [selectedTimeframe, setSelectedTimeframe] = useState(data.timeframes[0].timeframe);
  const current = data.timeframes[0];
  const generated = new Intl.DateTimeFormat('vi-VN', {
    dateStyle: 'medium',
    timeStyle: 'medium',
    timeZone: 'UTC',
  }).format(new Date(data.generated_at));

  useEffect(() => {
    const modelContext = (
      document as Document & {
        modelContext?: {
          registerTool: (tool: unknown, options?: { signal?: AbortSignal }) => void | Promise<void>;
        };
      }
    ).modelContext;
    if (!modelContext?.registerTool) return;
    const lifecycle = new AbortController();
    void Promise.resolve(
      modelContext.registerTool(
        {
          name: 'select_forecast_timeframe',
          title: 'Chọn khung dự báo',
          description: 'Switch the visible Kronos forecast panel to one supported BTC timeframe.',
          inputSchema: {
            type: 'object',
            properties: {
              timeframe: { type: 'string', enum: data.timeframes.map((item) => item.timeframe) },
            },
            required: ['timeframe'],
            additionalProperties: false,
          },
          annotations: { readOnlyHint: false, untrustedContentHint: false },
          execute(input: unknown) {
            const timeframe =
              typeof input === 'object' && input !== null && 'timeframe' in input
                ? String(input.timeframe)
                : '';
            if (!data.timeframes.some((item) => item.timeframe === timeframe)) {
              throw new Error(`Unsupported timeframe: ${timeframe}`);
            }
            setSelectedTimeframe(timeframe);
            return { selectedTimeframe: timeframe };
          },
        },
        { signal: lifecycle.signal },
      ),
    ).catch(() => undefined);
    return () => lifecycle.abort();
  }, []);

  return (
    <main className="min-h-screen">
      <header className="topbar">
        <div className="shell flex h-full items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="brand-mark"><span /></div>
            <div>
              <div className="brand-name">Agentic Alpha Lab</div>
              <div className="brand-sub">Kronos inference console</div>
            </div>
          </div>
          <div className="hidden items-center gap-5 text-xs text-muted-foreground md:flex">
            <span className="flex items-center gap-1.5"><Database className="size-3.5" /> Binance USD-M</span>
            <span className="flex items-center gap-1.5"><Clock3 className="size-3.5" /> {generated} UTC</span>
          </div>
          <Badge className="border border-amber-300/20 bg-amber-300/10 text-amber-200">
            Research only
          </Badge>
        </div>
      </header>

      <div className="shell py-7 sm:py-10">
        <section className="overview-grid">
          <div>
            <div className="eyebrow flex items-center gap-2">
              <Layers3 className="size-3.5" /> Multi-timeframe consensus
            </div>
            <div className="mt-3 flex flex-wrap items-end gap-x-5 gap-y-2">
              <h1>{data.consensus.label}</h1>
              <DirectionBadge value={data.consensus.label} />
            </div>
            <p className="overview-copy">
              Xác suất tăng có trọng số{' '}
              <strong>{(data.consensus.weighted_upside_probability * 100).toFixed(1)}%</strong>,
              mức đồng thuận {(data.consensus.agreement * 100).toFixed(0)}% trên bốn khung.
            </p>
          </div>
          <div className="price-block">
            <span>BTCUSDT · giá context mới nhất</span>
            <strong>{formatPrice(current.current_close)}</strong>
            <small>{data.model} · {data.sampling.paths} stochastic paths / timeframe</small>
          </div>
        </section>

        <section className="mt-5 grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
          {data.timeframes.map((frame) => (
            <div className="frame-strip" key={frame.timeframe}>
              <div className="flex items-center justify-between">
                <span className="frame-name">{frame.timeframe}</span>
                <DirectionBadge value={frame.signal.label} />
              </div>
              <div className="frame-return">{formatPercent(frame.mean_return)}</div>
              <div className="frame-meta">
                <span>{(frame.upside_probability * 100).toFixed(0)}% up</span>
                <span>→ {frame.horizon_label}</span>
              </div>
            </div>
          ))}
        </section>

        <section className="mt-7">
          <Tabs value={selectedTimeframe} onValueChange={setSelectedTimeframe}>
            <div className="mb-4 flex flex-col justify-between gap-3 sm:flex-row sm:items-end">
              <div>
                <div className="eyebrow">Probabilistic forecast</div>
                <h2 className="section-title">Mỗi khung kể một phần câu chuyện</h2>
              </div>
              <TabsList className="timeframe-tabs">
                {data.timeframes.map((frame) => (
                  <TabsTrigger key={frame.timeframe} value={frame.timeframe}>
                    {frame.timeframe}
                  </TabsTrigger>
                ))}
              </TabsList>
            </div>
            {data.timeframes.map((frame) => (
              <TabsContent key={frame.timeframe} value={frame.timeframe}>
                <ForecastPanel frame={frame} />
              </TabsContent>
            ))}
          </Tabs>
        </section>

        <section className="mt-7 grid gap-4">
          <BacktestTable />
          <LeverageComparison />
        </section>

        <section className="method-grid mt-7">
          <div>
            <div className="eyebrow">Execution contract</div>
            <h2 className="section-title">Chi phí được tính trước khi tin tín hiệu</h2>
          </div>
          <div className="cost-grid">
            <div><span>Entry limit</span><strong>0.02%</strong></div>
            <div><span>Exit limit</span><strong>0.02%</strong></div>
            <div><span>Long funding / 8h</span><strong>0.01%</strong></div>
            <div><span>Short funding</span><strong>0.00%</strong></div>
          </div>
          <div className="notice-block">
            <ShieldAlert className="size-5" />
            <p>
              Limit chỉ fill khi OHLC thật chạm giá; tín hiệu tại nến t chỉ được vào từ t+1.
              Funding short dương được bỏ qua để bù cho slippage và tránh làm kết quả lạc quan.
            </p>
          </div>
        </section>

        <footer>
          <span>AGENTIC ALPHA LAB / PHASE A</span>
          <span>{data.market}</span>
          <span className="flex items-center gap-1.5"><Activity className="size-3" /> data snapshot · not live execution</span>
        </footer>
      </div>
    </main>
  );
}
