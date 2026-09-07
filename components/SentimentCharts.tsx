'use client';

import {
  PieChart, Pie, Cell, BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer
} from 'recharts';
import type { PieLabelRenderProps, TooltipValueType } from 'recharts';
import { AnalysisData, SentimentData } from '@/types';

interface ChartsProps {
  sentiment: SentimentData;
  detailedData: AnalysisData | null;
  brandName: string;
}

interface KeywordItem {
  keyword: string;
  frequency: number;
}

const tooltipStyle = { backgroundColor: '#ffffff', border: '1px solid #14140f', borderRadius: '10px', color: '#14140f', fontWeight: 800 };
const tooltipLabelStyle = { color: '#14140f', fontWeight: 900 };
const axisStyle = { fill: '#14140f', fontSize: 13, fontWeight: 800 };

export function SentimentCharts({ sentiment, detailedData }: ChartsProps) {
  return (
    <div className="space-y-8">
      {/* Row 1: Sentiment Pie + Emotions Bar */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <SentimentPieChart sentiment={sentiment} />
        <EmotionBarChart sentiment={sentiment} />
      </div>

      {/* Row 2: Keywords + Pain Points */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <KeywordsChart keywords={detailedData?.keywords} />
        <PainPointsVsDesires painPoints={detailedData?.pain_points} desires={detailedData?.desires} />
      </div>

      {/* Row 3: Sentiment Gauge + Data Source Distribution */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <SentimentGauge sentiment={sentiment} />
        <PlatformDistributionChart sentiment={sentiment} detailedData={detailedData} />
      </div>
    </div>
  );
}

// ===== CHART 1: SENTIMENT PIE CHART =====
function SentimentPieChart({ sentiment }: { sentiment: SentimentData }) {
  const data = [
    { name: 'Positive', value: sentiment.positive, fill: '#14b8a6' },
    { name: 'Negative', value: sentiment.negative, fill: '#8b5cf6' },
    { name: 'Neutral', value: sentiment.neutral, fill: '#60a5fa' }
  ];

  const CustomLabel = ({ name, percent, x, y }: PieLabelRenderProps) => {
    return (
      <text x={x} y={y} fill="#14140f" textAnchor="middle" dominantBaseline="central" fontSize={13} fontWeight={900}>
        {`${name}: ${((percent ?? 0) * 100).toFixed(1)}%`}
      </text>
    );
  };

  return (
    <div className="bg-white p-6 rounded-lg shadow-lg">
      <h3 className="text-xl font-black text-gray-950 mb-4">Sentiment Distribution</h3>
      <ResponsiveContainer width="100%" height={300}>
        <PieChart>
          <Pie
            data={data}
            cx="50%"
            cy="50%"
            labelLine={true}
            label={CustomLabel}
            outerRadius={80}
            dataKey="value"
          >
            {data.map((entry, index) => (
              <Cell key={`cell-${index}`} fill={entry.fill} />
            ))}
          </Pie>
          <Tooltip 
            formatter={(value: TooltipValueType | undefined) => `${value} posts`}
            contentStyle={tooltipStyle}
            labelStyle={tooltipLabelStyle}
            itemStyle={{ color: '#14140f', fontWeight: 800 }}
          />
        </PieChart>
      </ResponsiveContainer>
      <div className="mt-4 grid grid-cols-3 gap-4 text-sm">
        <div className="text-center p-2 bg-teal-50 rounded">
          <p className="font-black text-black">{sentiment.positive}</p>
          <p className="font-bold text-black">Positive</p>
        </div>
        <div className="text-center p-2 bg-[#fdf4e6] rounded">
          <p className="font-black text-black">{sentiment.negative}</p>
          <p className="font-bold text-black">Negative</p>
        </div>
        <div className="text-center p-2 bg-sky-50 rounded">
          <p className="font-black text-black">{sentiment.neutral}</p>
          <p className="font-bold text-black">Neutral</p>
        </div>
      </div>
    </div>
  );
}

// ===== CHART 2: EMOTION BAR CHART =====
function EmotionBarChart({ sentiment }: { sentiment: SentimentData }) {
  const data = [
    { name: 'Positive', count: sentiment.positive, percentage: sentiment.positive_percent, fill: '#14b8a6' },
    { name: 'Negative', count: sentiment.negative, percentage: sentiment.negative_percent, fill: '#8b5cf6' },
    { name: 'Neutral', count: sentiment.neutral, percentage: sentiment.neutral_percent, fill: '#60a5fa' }
  ];

  return (
    <div className="bg-white p-6 rounded-lg shadow-lg">
      <h3 className="text-xl font-black text-gray-950 mb-4">Emotion Breakdown</h3>
      <ResponsiveContainer width="100%" height={300}>
        <BarChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="#d1d5db" />
          <XAxis dataKey="name" tick={axisStyle} />
          <YAxis tick={axisStyle} />
          <Tooltip 
            contentStyle={tooltipStyle}
            labelStyle={tooltipLabelStyle}
            itemStyle={{ color: '#14140f', fontWeight: 800 }}
            formatter={(value: TooltipValueType | undefined) => `${value} posts`}
          />
          <Bar dataKey="count" radius={[8, 8, 0, 0]}>
            {data.map((entry, index) => (
              <Cell key={`cell-${index}`} fill={entry.fill} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

// ===== CHART 3: KEYWORDS FREQUENCY BAR CHART =====
function KeywordsChart({ keywords }: { keywords?: KeywordItem[] }) {
  if (!keywords || keywords.length === 0) {
    return (
      <div className="bg-white p-6 rounded-lg shadow-lg">
        <h3 className="text-xl font-black text-gray-950 mb-4">Top Keywords</h3>
        <p className="text-sm font-bold text-black">No keywords found</p>
      </div>
    );
  }

  const chartData = keywords.slice(0, 10).map((kw) => ({
    keyword: kw.keyword.substring(0, 15),
    frequency: kw.frequency
  }));

  return (
    <div className="bg-white p-6 rounded-lg shadow-lg">
      <h3 className="text-xl font-black text-gray-950 mb-4">Top Keywords Mentioned</h3>
      <ResponsiveContainer width="100%" height={300}>
        <BarChart
          data={chartData}
          layout="vertical"
          margin={{ top: 5, right: 30, left: 100, bottom: 5 }}
        >
          <CartesianGrid strokeDasharray="3 3" stroke="#d1d5db" />
          <XAxis type="number" tick={axisStyle} />
          <YAxis dataKey="keyword" type="category" width={90} tick={axisStyle} />
          <Tooltip 
            contentStyle={tooltipStyle}
            labelStyle={tooltipLabelStyle}
            itemStyle={{ color: '#14140f', fontWeight: 800 }}
            formatter={(value: TooltipValueType | undefined) => `${value} mentions`}
          />
          <Bar dataKey="frequency" fill="#38bdf8" radius={[0, 8, 8, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

// ===== CHART 4: PAIN POINTS VS DESIRES =====
function PainPointsVsDesires({ painPoints, desires }: { painPoints?: string[]; desires?: string[] }) {
  const data = [
    {
      name: 'Issues',
      count: painPoints ? painPoints.length : 0,
      type: 'Pain Points',
      fill: '#8b5cf6'
    },
    {
      name: 'Wants',
      count: desires ? desires.length : 0,
      type: 'Desires',
      fill: '#14b8a6'
    }
  ];

  return (
    <div className="bg-white p-6 rounded-lg shadow-lg">
      <h3 className="text-xl font-black text-gray-950 mb-4">Issues vs Opportunities</h3>
      <ResponsiveContainer width="100%" height={300}>
        <BarChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="#d1d5db" />
          <XAxis dataKey="name" tick={axisStyle} />
          <YAxis tick={axisStyle} />
          <Tooltip 
            contentStyle={tooltipStyle}
            labelStyle={tooltipLabelStyle}
            itemStyle={{ color: '#14140f', fontWeight: 800 }}
            formatter={(value: TooltipValueType | undefined) => `${value} items`}
          />
          <Bar dataKey="count" radius={[8, 8, 0, 0]}>
            {data.map((entry, index) => (
              <Cell key={`cell-${index}`} fill={entry.fill} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      <div className="mt-4 grid grid-cols-2 gap-4 text-sm">
        <div className="p-3 bg-[#fdf4e6] rounded border-l-4 border-violet-500">
          <p className="font-black text-black">{painPoints ? painPoints.length : 0}</p>
          <p className="font-bold text-black">Pain Points</p>
        </div>
        <div className="p-3 bg-teal-50 rounded border-l-4 border-teal-500">
          <p className="font-black text-black">{desires ? desires.length : 0}</p>
          <p className="font-bold text-black">Customer Desires</p>
        </div>
      </div>
    </div>
  );
}

// ===== CHART 5: SENTIMENT GAUGE =====
function SentimentGauge({ sentiment }: { sentiment: SentimentData }) {
  const percentage = sentiment.positive_percent;

  let gaugeColor = '#c084fc';
  if (percentage >= 40 && percentage < 60) gaugeColor = '#38bdf8';
  if (percentage >= 60) gaugeColor = '#2dd4bf';

  return (
    <div className="bg-white p-6 rounded-lg shadow-lg">
      <h3 className="text-xl font-black text-gray-950 mb-4">Overall Sentiment Gauge</h3>
      <div className="flex flex-col items-center justify-center">
        <svg width="200" height="150" viewBox="0 0 200 150" className="mb-4">
          {/* Background arc */}
          <path
            d="M 20 100 A 80 80 0 0 1 180 100"
            stroke="#dbeafe"
            strokeWidth="20"
            fill="none"
            strokeLinecap="round"
          />
          {/* Progress arc */}
          <path
            d="M 20 100 A 80 80 0 0 1 180 100"
            stroke={gaugeColor}
            strokeWidth="20"
            fill="none"
            strokeLinecap="round"
            strokeDasharray={`${(percentage / 100) * (Math.PI * 160)}, ${Math.PI * 160}`}
          />
          {/* Center text */}
          <text
            x="100"
            y="100"
            fontSize="36"
            fontWeight="bold"
            textAnchor="middle"
            fill={gaugeColor}
          >
            {percentage.toFixed(1)}%
          </text>
        </svg>
        <p className="text-center text-black text-sm font-black">
          {percentage >= 60 ? '✅ Positive Sentiment' : percentage >= 40 ? '⚠️ Mixed Sentiment' : '❌ Negative Sentiment'}
        </p>
      </div>
    </div>
  );
}

// ===== CHART 6: PLATFORM DISTRIBUTION =====
// Ab ek se zyada sources ho sakte hain (Trustpilot + YouTube).
// Purani saved analyses mein sirf `trustpilot` key hoti thi — wo bhi theek
// render hoti hai kyunki youtube optional hai aur 0 par bar chhup jata hai.
const SOURCE_META: { key: 'trustpilot' | 'youtube'; label: string; fill: string; blurb: string }[] = [
  { key: 'trustpilot', label: 'Trustpilot', fill: '#38bdf8', blurb: 'customer reviews' },
  { key: 'youtube',    label: 'YouTube',    fill: '#f43f5e', blurb: 'video comments'   },
];

function PlatformDistributionChart({ sentiment, detailedData }: { sentiment: SentimentData; detailedData?: AnalysisData | null }) {
  const platforms = detailedData?.platforms;

  const sources = SOURCE_META
    .map((m) => ({ ...m, value: platforms?.[m.key] ?? 0 }))
    .filter((s) => s.value > 0);

  // Fallback: agar platforms key hi na ho (bohat purani analysis), to
  // total ko Trustpilot maan lo — pehle wala behaviour.
  const data = sources.length
    ? sources
    : [{ key: 'trustpilot' as const, label: 'Trustpilot', fill: '#38bdf8', blurb: 'customer reviews', value: sentiment.total_posts }];

  const total = data.reduce((sum, d) => sum + d.value, 0) || 1;

  return (
    <div className="bg-white p-6 rounded-lg shadow-lg">
      <h3 className="text-xl font-black text-gray-950 mb-4">Data Source Distribution</h3>
      <ResponsiveContainer width="100%" height={250}>
        <BarChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="#d1d5db" />
          <XAxis dataKey="label" tick={axisStyle} />
          <YAxis tick={axisStyle} />
          <Tooltip
            contentStyle={tooltipStyle}
            labelStyle={tooltipLabelStyle}
            itemStyle={{ color: '#14140f', fontWeight: 800 }}
            formatter={(value: TooltipValueType | undefined) => `${value} items`}
          />
          <Bar dataKey="value" radius={[8, 8, 0, 0]}>
            {data.map((entry) => (
              <Cell key={entry.key} fill={entry.fill} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      <div className="mt-4 space-y-2">
        {data.map((s) => (
          <div key={s.key} className="p-3 bg-[#fbfaf7] rounded border-l-4" style={{ borderColor: s.fill }}>
            <p className="text-sm font-bold text-black">
              <strong>{s.label}:</strong> {s.value} {s.blurb}{' '}
              <span className="text-[#8b877d]">({((s.value / total) * 100).toFixed(0)}%)</span>
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}

