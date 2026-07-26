// Adapted for plain-browser use (no bundler): React and lucide are loaded
// as global UMD scripts by index.html, so we destructure from those
// globals instead of using ES module imports.
const { useState, useEffect, useCallback } = React;

// The plain "lucide" package (as opposed to "lucide-react") exposes each
// icon as a single node-tuple describing the whole <svg> element, e.g.
// ChevronDown = ["svg", {width, height, viewBox, ...attrs}, [["path", {d:
// "..."}]]] — confirmed directly via runtime inspection of this build.
// This is meant for vanilla-JS use via lucide.createElement(...) /
// data-lucide="..." attributes, not as a React component. Using it
// directly as a JSX tag (<ChevronDown />) makes React try to render
// `undefined` as an element type. This adapter recursively converts any
// lucide node-tuple (and its nested children, which use the same
// [tag, attrs, children] shape) into real React elements.
function nodeToReactElement([tag, attrs = {}, children = []], key) {
  // camelCase a couple of attrs React insists on, since lucide's raw data
  // uses plain SVG attribute names (kebab-case where applicable).
  const { "stroke-width": strokeWidth, "stroke-linecap": strokeLinecap, "stroke-linejoin": strokeLinejoin, ...rest } = attrs;
  const reactAttrs = {
    key,
    ...rest,
    ...(strokeWidth != null && { strokeWidth }),
    ...(strokeLinecap != null && { strokeLinecap }),
    ...(strokeLinejoin != null && { strokeLinejoin }),
  };
  return React.createElement(
    tag,
    reactAttrs,
    (children || []).map((child, i) => nodeToReactElement(child, i))
  );
}

function makeLucideIcon(iconTuple) {
  return function LucideIcon({ size = 24, className, style, ...rest }) {
    if (!Array.isArray(iconTuple)) return null;
    const [tag, attrs = {}, children = []] = iconTuple;
    const { "stroke-width": strokeWidth, "stroke-linecap": strokeLinecap, "stroke-linejoin": strokeLinejoin, ...restAttrs } = attrs;
    return React.createElement(
      tag,
      {
        ...restAttrs,
        width: size,
        height: size,
        className,
        style,
        ...(strokeWidth != null && { strokeWidth }),
        ...(strokeLinecap != null && { strokeLinecap }),
        ...(strokeLinejoin != null && { strokeLinejoin }),
        ...rest,
      },
      (children || []).map((child, i) => nodeToReactElement(child, i))
    );
  };
}

const {
  ChevronDown, ChevronRight, Search, TrendingUp, Target, Wrench, Clock,
  Users, Tag, DollarSign, AlertCircle, CheckCircle2, PlayCircle,
  Archive, Sparkles, ExternalLink, X, Plus, MessageCircle
} = Object.fromEntries(
  Object.entries({
    ChevronDown: lucide.ChevronDown, ChevronRight: lucide.ChevronRight,
    Search: lucide.Search, TrendingUp: lucide.TrendingUp, Target: lucide.Target,
    Wrench: lucide.Wrench, Clock: lucide.Clock, Users: lucide.Users,
    Tag: lucide.Tag, DollarSign: lucide.DollarSign, AlertCircle: lucide.AlertCircle,
    CheckCircle2: lucide.CheckCircle2, PlayCircle: lucide.PlayCircle,
    Archive: lucide.Archive, Sparkles: lucide.Sparkles, ExternalLink: lucide.ExternalLink,
    X: lucide.X, Plus: lucide.Plus, MessageCircle: lucide.MessageCircle,
  }).map(([name, iconNode]) => [name, makeLucideIcon(iconNode)])
);

// ---------------------------------------------------------------------------
// Sample seed data. Replace / append via the daily scraper pipeline — each
// idea object below mirrors the schema the deep-crawl script produces.
// ---------------------------------------------------------------------------
const SEED_IDEAS = [
  {
    id: "2026-07-25-ad-fraud-guardian",
    date: "2026-07-25",
    title: "Ad Fraud Guardian",
    tagline: "Recover thousands in wasted PPC budget lost to ad fraud",
    badges: ["Perfect Timing"],
    description:
      "Most businesses waste 20-40% of their ad spend on bot clicks, competitor sabotage, and fraud without realizing it. Ad Fraud Guardian scans Google Ads, Facebook, and TikTok campaigns in real-time, flagging suspicious patterns and click fraud before they drain budget. Custom blocking rules and a savings dashboard. $99/mo for small accounts, custom pricing for agencies.",
    scores: {
      opportunity: { score: 8, label: "Strong" },
      problem: { score: 8, label: "Real Pain" },
      feasibility: { score: 7, label: "Moderate" },
      whyNow: { score: 9, label: "Perfect Timing" },
    },
    keywords: [
      { keyword: "click fraud detection", volume: 2400, growth: 45 },
      { keyword: "ppc fraud protection", volume: 880, growth: 120 },
      { keyword: "ad fraud software", volume: 1600, growth: 30 },
    ],
    marketGap:
      "Existing fraud tools are enterprise-only and expensive. Small agencies and businesses spending $10K-$100K/month have no accessible, real-time protection layer.",
    executionPlan:
      "Start with a Chrome extension / API integration for Google Ads only. Validate with 10 agency beta users. Add Facebook + TikTok once core detection accuracy is proven. Layer in the savings dashboard as the retention hook.",
    executionDifficulty: { score: 5, note: "API integrations + fraud heuristics; solo-buildable MVP in 3-4 weeks" },
    categorization: { type: "SaaS", market: "B2B", target: "Digital agencies & SMBs", competitor: "Lunio, ClickCease" },
    communitySignals: { reddit: "Active in r/PPC, r/agency", facebook: "Several agency owner groups", youtube: "Moderate coverage" },
    status: "not_started",
    notes: "",
  },
  {
    id: "2026-07-24-link-building-services",
    date: "2026-07-24",
    title: "AI Visibility & Link Building Platform",
    tagline: "Ethical earned-visibility engine for solo operators drowning in AI content",
    badges: ["Exceptional", "Perfect Timing"],
    description:
      "The surge in AI-generated content has created a discoverability crisis. Solo operators and micro-teams using AI content tools lack distribution resources, especially in high-trust local services like clinics and law firms. This platform combines invisibility audits with strategic media placement to create a real edge in a crowded market.",
    scores: {
      opportunity: { score: 9, label: "Exceptional" },
      problem: { score: 9, label: "Severe Pain" },
      feasibility: { score: 9, label: "Very Easy" },
      whyNow: { score: 9, label: "Perfect Timing" },
    },
    keywords: [
      { keyword: "link building services", volume: 8100, growth: 50 },
      { keyword: "ai seo tools", volume: 5400, growth: 1588 },
      { keyword: "artificial intelligence search engine optimization", volume: 27100, growth: 1594 },
      { keyword: "best ai seo tools", volume: 1600, growth: 15900 },
      { keyword: "content marketing for link building", volume: 480, growth: 4700 },
      { keyword: "ai seo platform", volume: 260, growth: 2500 },
      { keyword: "seo services link building", volume: 2900, growth: 21 },
      { keyword: "backlink building service", volume: 1900, growth: 296 },
    ],
    marketGap:
      "The biggest market gap lies in providing ethical, earned visibility solutions for solo operators overwhelmed by AI-generated content. Underserved segment: solo operators & micro-teams (8/10) especially in high-trust local services.",
    executionPlan:
      "Solo-friendly build, 1-2 week MVP with Cursor. Simple to build with AI tools but requires effective distribution strategy. Risks: high API usage costs, distribution/market penetration, dependence on reliable AI outputs.",
    executionDifficulty: { score: 3, note: "Solo-friendly, 1-2 week MVP with Cursor" },
    categorization: { type: "SaaS", market: "B2B", target: "Solo Operators", competitor: "BuzzSumo" },
    communitySignals: { reddit: "5 subreddits found", facebook: "8 groups found", youtube: "13 channels, 16 themes", other: "4 segments, 4 priorities" },
    valueEquation: "Value Equation Analysis — Overall Rating: 6/10 (Good). Dream Outcome 8/10, Perceived Likelihood 6/10, Time Delay 5/10, Effort & Sacrifice 4/10.",
    marketMatrix: "Market Matrix Analysis — Category King (high uniqueness, high value). Positioned for category leadership with a unique, ethical approach to earned distribution.",
    acpFramework: "",
    valueLadderDetail: "",
    proofSignals: "",
    whyNowDetail: "",
    communitySignalsDetail: "",
    status: "researching",
    notes: "",
  },
];

const STATUS_CONFIG = {
  not_started: { label: "New", color: "#8B8577", stamp: null },
  researching: { label: "Researching", color: "#6B8F71", stamp: "RESEARCHING" },
  building: { label: "Building", color: "#E8A33D", stamp: "BUILDING" },
  launched: { label: "Launched", color: "#4A7C59", stamp: "LAUNCHED" },
  shelved: { label: "Shelved", color: "#A85C5C", stamp: "SHELVED" },
};

const TABS = ["Overview", "Keywords", "Market", "Execution", "Community"];

// Defensively converts any field value to a displayable string. Some data
// (especially older/sample entries) may have fields as objects instead of
// plain strings (e.g. {score, label} instead of a sentence) — rendering an
// object directly in JSX throws and silently breaks the whole tab. This
// keeps a card always renderable no matter what shape a field turns out to
// be, rather than crashing on a single bad field.
function safeText(value) {
  if (value == null) return "";
  if (typeof value === "string") return value;
  if (typeof value === "number") return String(value);
  if (typeof value === "object") {
    if ("score" in value || "label" in value) {
      return [value.label, value.score != null ? `${value.score}/10` : null].filter(Boolean).join(" — ");
    }
    try {
      return JSON.stringify(value);
    } catch {
      return "";
    }
  }
  return String(value);
}

function ScoreBar({ label, score, icon: Icon }) {
  const pct = (score / 10) * 100;
  return (
    <div className="flex items-center gap-2 min-w-0">
      <Icon size={13} className="shrink-0 opacity-60" />
      <span className="text-[11px] uppercase tracking-wider opacity-60 w-16 shrink-0" style={{ fontFamily: "'JetBrains Mono', monospace" }}>
        {label}
      </span>
      <div className="flex-1 h-1.5 rounded-full bg-black/10 overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{ width: `${pct}%`, backgroundColor: "#E8A33D" }}
        />
      </div>
      <span className="text-sm font-bold w-4 text-right" style={{ fontFamily: "'JetBrains Mono', monospace" }}>
        {score}
      </span>
    </div>
  );
}

function Stamp({ status }) {
  const cfg = STATUS_CONFIG[status];
  if (!cfg.stamp) return null;
  return (
    <div
      className="absolute -top-2 -right-2 border-[3px] rounded px-2 py-0.5 text-[10px] font-black tracking-widest pointer-events-none select-none"
      style={{
        color: cfg.color,
        borderColor: cfg.color,
        transform: "rotate(8deg)",
        fontFamily: "'JetBrains Mono', monospace",
        backgroundColor: "rgba(247,244,236,0.9)",
      }}
    >
      {cfg.stamp}
    </div>
  );
}

// Small hand-built SVG sparkline showing a keyword's growth trajectory.
// We don't have real historical monthly data points from the scraper (only
// current volume + overall growth %), so rather than fabricate a precise
// multi-year line like the real site's chart, this renders an honest
// visual shape: a smooth rising/falling curve whose steepness reflects the
// actual growth percentage, clearly conveying "this is trending up fast"
// vs "this is flat" at a glance, without pretending to show exact history.
// Real interactive hover chart for a keyword's volume history, built by
// hand with plain SVG (no charting library dependency, given the CDN/UMD
// reliability issues we've hit elsewhere in this app) — matches the site's
// own line-chart style. Only renders when real chartHistory data exists
// for this keyword (captured by hovering the site's actual chart during
// scraping); if that data is missing for a given day/keyword, the caller
// falls back to the plain volume/growth summary instead of showing a fake
// or empty chart.
function KeywordHistoryChart({ history }) {
  const [hoverIndex, setHoverIndex] = useState(null);
  const width = 600;
  const height = 220;
  const padding = { top: 20, right: 20, bottom: 30, left: 50 };
  const plotW = width - padding.left - padding.right;
  const plotH = height - padding.top - padding.bottom;

  // Parse numeric values out of strings like "8,100 searches" -> 8100.
  const points = history
    .map((h) => {
      const m = String(h.value || "").replace(/,/g, "").match(/(\d+)/);
      return { label: h.label, raw: h.value, num: m ? Number(m[1]) : 0 };
    })
    .filter((p) => p.label);

  if (points.length < 2) return null;

  const maxVal = Math.max(...points.map((p) => p.num), 1);
  const toX = (i) => padding.left + (i / (points.length - 1)) * plotW;
  const toY = (v) => padding.top + plotH - (v / maxVal) * plotH;

  const linePath = points.map((p, i) => `${i === 0 ? "M" : "L"} ${toX(i)} ${toY(p.num)}`).join(" ");
  const areaPath = `${linePath} L ${toX(points.length - 1)} ${padding.top + plotH} L ${toX(0)} ${padding.top + plotH} Z`;

  const handleMove = (e) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const relX = ((e.clientX - rect.left) / rect.width) * width;
    const frac = Math.max(0, Math.min(1, (relX - padding.left) / plotW));
    setHoverIndex(Math.round(frac * (points.length - 1)));
  };

  const active = hoverIndex != null ? points[hoverIndex] : null;

  return (
    <div className="relative">
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="w-full h-auto"
        onMouseMove={handleMove}
        onMouseLeave={() => setHoverIndex(null)}
      >
        {/* Y-axis gridlines + labels */}
        {[0, 0.25, 0.5, 0.75, 1].map((frac) => (
          <g key={frac}>
            <line
              x1={padding.left}
              x2={width - padding.right}
              y1={padding.top + plotH * (1 - frac)}
              y2={padding.top + plotH * (1 - frac)}
              stroke="rgba(0,0,0,0.06)"
              strokeWidth="1"
            />
            <text x={padding.left - 8} y={padding.top + plotH * (1 - frac) + 4} textAnchor="end" fontSize="10" fill="rgba(0,0,0,0.4)" style={{ fontFamily: "'JetBrains Mono', monospace" }}>
              {Math.round(maxVal * frac).toLocaleString()}
            </text>
          </g>
        ))}
        {/* Area fill + line */}
        <path d={areaPath} fill="#E8A33D" opacity="0.12" />
        <path d={linePath} fill="none" stroke="#E8A33D" strokeWidth="2" />
        {/* X-axis labels: show a handful evenly spaced, not every point */}
        {points
          .filter((_, i) => i % Math.ceil(points.length / 6) === 0)
          .map((p) => {
            const i = points.indexOf(p);
            return (
              <text key={i} x={toX(i)} y={height - 8} textAnchor="middle" fontSize="10" fill="rgba(0,0,0,0.4)" style={{ fontFamily: "'JetBrains Mono', monospace" }}>
                {p.label}
              </text>
            );
          })}
        {/* Hover indicator */}
        {active && (
          <>
            <line x1={toX(hoverIndex)} x2={toX(hoverIndex)} y1={padding.top} y2={padding.top + plotH} stroke="#12151C" strokeWidth="1" strokeDasharray="3,3" opacity="0.4" />
            <circle cx={toX(hoverIndex)} cy={toY(active.num)} r="4" fill="#12151C" stroke="#E8A33D" strokeWidth="2" />
          </>
        )}
      </svg>
      {active && (
        <div
          className="absolute pointer-events-none px-2 py-1 rounded text-xs shadow-lg"
          style={{
            left: `${(toX(hoverIndex) / width) * 100}%`,
            top: `${(toY(active.num) / height) * 100}%`,
            transform: "translate(-50%, -130%)",
            backgroundColor: "#12151C",
            color: "#F7F4EC",
            fontFamily: "'JetBrains Mono', monospace",
            whiteSpace: "nowrap",
          }}
        >
          <div className="font-bold">{active.label}</div>
          <div>{active.raw}</div>
        </div>
      )}
    </div>
  );
}

function KeywordSparkline({ growth, color }) {
  const width = 72;
  const height = 28;
  // Normalize growth into a 0-1 steepness factor for the curve, capping
  // extreme values (some keywords in this dataset show +100000%) so the
  // shape stays readable rather than a flat line at the bottom.
  const steepness = Math.max(0, Math.min(1, Math.log10(Math.max(growth, 1) + 1) / 5));
  const startY = height - 4;
  const endY = height - 4 - steepness * (height - 8);
  const midY = height - 4 - steepness * (height - 8) * 0.4;
  const path = `M 2 ${startY} Q ${width * 0.5} ${midY}, ${width - 2} ${endY}`;
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} className="shrink-0">
      <path d={path} fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" />
      <circle cx={width - 2} cy={endY} r="2.5" fill={color} />
    </svg>
  );
}

// The scraper stores Value Equation and Market Matrix as raw paragraph
// text (whatever the site's own page copy says), not structured numbers —
// so to render real visual score bars / a real quadrant like the site
// does, we parse the specific numeric patterns back out of that text.
// Regexes are written against the actual real scraped text we've observed
// (e.g. "Dream Outcome\n9/10", "Uniqueness\n\n8/10"), and everything
// degrades gracefully to null if a pattern isn't found, so a parsing miss
// never breaks rendering — it just quietly falls back to plain text.
function parseValueEquation(text) {
  if (!text) return null;
  const overall = text.match(/Overall Rating\s*\n*\s*(\d+)\s*\/\s*10/i);
  const dream = text.match(/Dream Outcome\s*\n*\s*(\d+)\s*\/\s*10/i);
  const likelihood = text.match(/Perceived Likelihood\s*\n*\s*(\d+)\s*\/\s*10/i);
  const delay = text.match(/Time Delay\s*\n*\s*(\d+)\s*\/\s*10/i);
  const effort = text.match(/Effort\s*(?:&|and)?\s*Sacrifice\s*\n*\s*(\d+)\s*\/\s*10/i);
  if (!dream && !likelihood && !delay && !effort) return null;
  return {
    overall: overall ? Number(overall[1]) : null,
    factors: [
      { label: "Dream Outcome", icon: "🎯", score: dream ? Number(dream[1]) : null },
      { label: "Perceived Likelihood", icon: "🎲", score: likelihood ? Number(likelihood[1]) : null },
      { label: "Time Delay", icon: "⏱️", score: delay ? Number(delay[1]) : null },
      { label: "Effort & Sacrifice", icon: "💪", score: effort ? Number(effort[1]) : null },
    ].filter((f) => f.score != null),
  };
}

function parseMarketMatrix(text) {
  if (!text) return null;
  const uniqueness = text.match(/Uniqueness\s*\n*\s*(\d+)\s*\/\s*10/i);
  const value = text.match(/\bValue\s*\n*\s*(\d+)\s*\/\s*10/i);
  if (!uniqueness && !value) return null;
  const u = uniqueness ? Number(uniqueness[1]) : 5;
  const v = value ? Number(value[1]) : 5;
  // Quadrant position: 0-10 scale mapped to a 0-100% position inside the
  // 2x2 grid, matching the site's own four-quadrant framing.
  const quadrant = u >= 5 && v >= 5 ? "Category King" : u >= 5 && v < 5 ? "Tech Novelty" : u < 5 && v >= 5 ? "Commodity Play" : "Low Impact";
  return { uniqueness: u, value: v, quadrant };
}

// Individual score bar matching the site's own visual language for the
// Value Equation breakdown (icon, label, numeric bar, score).
function ValueEquationBar({ icon, label, score }) {
  return (
    <div className="flex items-center gap-2">
      <span className="text-sm shrink-0">{icon}</span>
      <span className="text-xs w-36 shrink-0" style={{ fontFamily: "'JetBrains Mono', monospace" }}>{label}</span>
      <div className="flex-1 h-1.5 rounded-full bg-black/10 overflow-hidden">
        <div className="h-full rounded-full" style={{ width: `${score * 10}%`, backgroundColor: "#E8A33D" }} />
      </div>
      <span className="text-xs font-bold w-8 text-right" style={{ fontFamily: "'JetBrains Mono', monospace" }}>{score}/10</span>
    </div>
  );
}

// 2x2 quadrant visual matching the site's Market Matrix framing: Tech
// Novelty / Category King on top, Low Impact / Commodity Play on bottom,
// with a dot placed according to the idea's actual uniqueness/value score.
function MarketMatrixGrid({ uniqueness, value, quadrant }) {
  // Position dot: x = value (0-10 -> 0-100%), y = uniqueness inverted
  // (higher uniqueness = higher on the grid = lower CSS top%).
  const dotLeft = `${(value / 10) * 100}%`;
  const dotTop = `${100 - (uniqueness / 10) * 100}%`;
  const cellStyle = "flex items-center justify-center text-center text-[10px] uppercase tracking-wide p-2 leading-tight";
  return (
    <div>
      <div className="relative grid grid-cols-2 grid-rows-2 gap-1 aspect-square max-w-[220px] mx-auto rounded-lg overflow-hidden border border-black/10">
        <div className={cellStyle} style={{ backgroundColor: quadrant === "Tech Novelty" ? "rgba(232,163,61,0.25)" : "rgba(0,0,0,0.03)" }}>Tech Novelty</div>
        <div className={cellStyle} style={{ backgroundColor: quadrant === "Category King" ? "rgba(232,163,61,0.25)" : "rgba(0,0,0,0.03)" }}>Category King</div>
        <div className={cellStyle} style={{ backgroundColor: quadrant === "Low Impact" ? "rgba(232,163,61,0.25)" : "rgba(0,0,0,0.03)" }}>Low Impact</div>
        <div className={cellStyle} style={{ backgroundColor: quadrant === "Commodity Play" ? "rgba(232,163,61,0.25)" : "rgba(0,0,0,0.03)" }}>Commodity Play</div>
        <div
          className="absolute w-3 h-3 rounded-full border-2"
          style={{ left: dotLeft, top: dotTop, transform: "translate(-50%, -50%)", backgroundColor: "#12151C", borderColor: "#E8A33D" }}
        />
      </div>
      <div className="flex justify-center gap-4 mt-2 text-[10px] opacity-50" style={{ fontFamily: "'JetBrains Mono', monospace" }}>
        <span>Uniqueness: {uniqueness}/10</span>
        <span>Value: {value}/10</span>
      </div>
    </div>
  );
}

function KeywordRow({ kw }) {
  const growthColor = kw.growth > 500 ? "#4A7C59" : kw.growth > 50 ? "#6B8F71" : "#8B8577";
  return (
    <div className="flex items-center justify-between py-3 border-b border-black/5 last:border-0 gap-3">
      <span className="text-sm flex-1 min-w-0 truncate">{kw.keyword}</span>
      <KeywordSparkline growth={kw.growth} color={growthColor} />
      <div className="flex flex-col items-end shrink-0 w-16" style={{ fontFamily: "'JetBrains Mono', monospace" }}>
        <span className="text-xs opacity-60">{kw.volume.toLocaleString()}/mo</span>
        <span className="text-xs font-bold" style={{ color: growthColor }}>
          +{kw.growth}%
        </span>
      </div>
    </div>
  );
}

function IdeaCard({ idea, isOpen, onToggle, onStatusChange, onNotesChange, onAskClaude, onSummarize }) {
  const [tab, setTab] = useState("Overview");
  const [localNotes, setLocalNotes] = useState(idea.notes || "");
  const cfg = STATUS_CONFIG[idea.status];

  useEffect(() => setLocalNotes(idea.notes || ""), [idea.id]);

  const avgScore = Math.round(
    Object.values(idea.scores).reduce((s, o) => s + o.score, 0) / Object.values(idea.scores).length
  );

  return (
    <div
      className="relative rounded-xl border overflow-hidden transition-shadow"
      style={{
        backgroundColor: "#F7F4EC",
        borderColor: "rgba(0,0,0,0.08)",
        boxShadow: isOpen ? "0 8px 30px rgba(0,0,0,0.25)" : "0 2px 8px rgba(0,0,0,0.15)",
      }}
    >
      <Stamp status={idea.status} />

      {/* Header — always visible */}
      <button
        onClick={onToggle}
        className="w-full text-left p-5 flex items-start gap-4"
      >
        <div
          className="shrink-0 w-12 h-12 rounded-lg flex items-center justify-center text-lg font-black"
          style={{
            backgroundColor: "#12151C",
            color: "#E8A33D",
            fontFamily: "'JetBrains Mono', monospace",
          }}
        >
          {avgScore}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h3
              className="text-lg font-bold leading-tight"
              style={{ fontFamily: "'Fraunces', serif", color: "#1A1A1A" }}
            >
              {idea.title}
            </h3>
            {idea.badges?.map((b) => (
              <span
                key={b}
                className="text-[10px] uppercase tracking-wide px-1.5 py-0.5 rounded"
                style={{ backgroundColor: "#6B8F71", color: "#F7F4EC" }}
              >
                {b}
              </span>
            ))}
          </div>
          <p className="text-sm opacity-70 mt-0.5">{idea.tagline}</p>
          <p className="text-[11px] opacity-50 mt-1" style={{ fontFamily: "'JetBrains Mono', monospace" }}>
            {idea.date}
          </p>
        </div>
        {isOpen ? <ChevronDown size={20} className="shrink-0 opacity-50 mt-2" /> : <ChevronRight size={20} className="shrink-0 opacity-50 mt-2" />}
      </button>

      {isOpen && (
        <div className="px-5 pb-5 border-t border-black/10 pt-4">
          {/* Status selector */}
          <div className="flex items-center gap-2 mb-4 flex-wrap">
            <span className="text-[11px] uppercase tracking-wider opacity-50" style={{ fontFamily: "'JetBrains Mono', monospace" }}>
              Status:
            </span>
            {Object.entries(STATUS_CONFIG).map(([key, c]) => (
              <button
                key={key}
                onClick={() => onStatusChange(idea.id, key)}
                className="text-xs px-2.5 py-1 rounded-full border transition-all"
                style={{
                  borderColor: c.color,
                  backgroundColor: idea.status === key ? c.color : "transparent",
                  color: idea.status === key ? "#F7F4EC" : c.color,
                }}
              >
                {c.label}
              </button>
            ))}
          </div>

          {/* Tabs */}
          <div className="flex gap-1 mb-4 border-b border-black/10 overflow-x-auto" style={{ scrollbarWidth: "none", WebkitOverflowScrolling: "touch" }}>
            {TABS.map((t) => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className="px-3 py-2 text-xs font-semibold uppercase tracking-wide -mb-px border-b-2 transition-colors shrink-0 whitespace-nowrap"
                style={{
                  borderColor: tab === t ? "#E8A33D" : "transparent",
                  color: tab === t ? "#1A1A1A" : "rgba(0,0,0,0.4)",
                  fontFamily: "'JetBrains Mono', monospace",
                }}
              >
                {t}
              </button>
            ))}
          </div>

          {/* Tab content */}
          <div className="min-h-[140px]">
            {tab === "Overview" && (
              <div className="space-y-4">
                <div className="text-[10px] uppercase tracking-wider opacity-40" style={{ fontFamily: "'JetBrains Mono', monospace" }}>
                  The pitch — see Market, Execution & Keywords tabs for the rest
                </div>
                <p className="text-sm leading-relaxed">{idea.description}</p>
                <div className="grid grid-cols-2 gap-x-6 gap-y-2 pt-2">
                  <ScoreBar label="Opp." score={idea.scores.opportunity.score} icon={TrendingUp} />
                  <ScoreBar label="Problem" score={idea.scores.problem.score} icon={AlertCircle} />
                  <ScoreBar label="Feasib." score={idea.scores.feasibility.score} icon={Wrench} />
                  <ScoreBar label="Timing" score={idea.scores.whyNow.score} icon={Clock} />
                </div>
              </div>
            )}

            {tab === "Keywords" && (
              <div>
                <div className="text-[10px] uppercase tracking-wider opacity-40 mb-3" style={{ fontFamily: "'JetBrains Mono', monospace" }}>
                  Search demand data — sorted by growth
                </div>
                {idea.keywords?.[0]?.chartHistory?.length >= 2 && (
                  <div className="mb-4 pb-4 border-b border-black/10">
                    <div className="text-xs font-semibold mb-2" style={{ fontFamily: "'JetBrains Mono', monospace" }}>
                      {idea.keywords[0].keyword} — search volume over time
                    </div>
                    <KeywordHistoryChart history={idea.keywords[0].chartHistory} />
                    <div className="text-[10px] opacity-40 mt-1">Hover the chart to see monthly values</div>
                  </div>
                )}
                {idea.keywords?.length ? (
                  idea.keywords
                    .slice()
                    .sort((a, b) => b.growth - a.growth)
                    .map((kw) => <KeywordRow key={kw.keyword} kw={kw} />)
                ) : (
                  <p className="text-sm opacity-50 italic">No keyword data captured for this idea yet.</p>
                )}
              </div>
            )}

            {tab === "Market" && (
              <div className="space-y-4 text-sm">
                <div className="text-[10px] uppercase tracking-wider opacity-40" style={{ fontFamily: "'JetBrains Mono', monospace" }}>
                  Market Gap, Why Now, Proof & Signals, framework fit
                </div>
                <div>
                  <div className="text-[11px] uppercase tracking-wider opacity-50 mb-1" style={{ fontFamily: "'JetBrains Mono', monospace" }}>
                    Market Gap
                  </div>
                  <p className="leading-relaxed">{safeText(idea.marketGap)}</p>
                </div>
                <div className="grid grid-cols-2 gap-3 pt-2">
                  <div>
                    <div className="text-[11px] uppercase tracking-wider opacity-50" style={{ fontFamily: "'JetBrains Mono', monospace" }}>Type</div>
                    <div className="font-semibold">{idea.categorization?.type}</div>
                  </div>
                  <div>
                    <div className="text-[11px] uppercase tracking-wider opacity-50" style={{ fontFamily: "'JetBrains Mono', monospace" }}>Market</div>
                    <div className="font-semibold">{idea.categorization?.market}</div>
                  </div>
                  <div>
                    <div className="text-[11px] uppercase tracking-wider opacity-50" style={{ fontFamily: "'JetBrains Mono', monospace" }}>Target</div>
                    <div className="font-semibold">{idea.categorization?.target}</div>
                  </div>
                  <div>
                    <div className="text-[11px] uppercase tracking-wider opacity-50" style={{ fontFamily: "'JetBrains Mono', monospace" }}>Main Competitor</div>
                    <div className="font-semibold">{idea.categorization?.competitor}</div>
                  </div>
                </div>
                {idea.whyNowDetail && (
                  <details className="pt-2 border-t border-black/10">
                    <summary className="text-[11px] uppercase tracking-wider opacity-50 cursor-pointer" style={{ fontFamily: "'JetBrains Mono', monospace" }}>
                      Why Now (full analysis) ▾
                    </summary>
                    <p className="mt-2 leading-relaxed whitespace-pre-line text-xs opacity-80">{idea.whyNowDetail}</p>
                  </details>
                )}
                {idea.proofSignals && (
                  <details className="pt-2 border-t border-black/10">
                    <summary className="text-[11px] uppercase tracking-wider opacity-50 cursor-pointer" style={{ fontFamily: "'JetBrains Mono', monospace" }}>
                      Proof & Signals ▾
                    </summary>
                    <p className="mt-2 leading-relaxed whitespace-pre-line text-xs opacity-80">{idea.proofSignals}</p>
                  </details>
                )}
                {(idea.valueEquation || idea.marketMatrix) && (
                  <details className="pt-2 border-t border-black/10" open>
                    <summary className="text-[11px] uppercase tracking-wider opacity-50 cursor-pointer" style={{ fontFamily: "'JetBrains Mono', monospace" }}>
                      Value Equation & Market Matrix ▾
                    </summary>
                    <div className="mt-3 space-y-4">
                      {(() => {
                        const ve = parseValueEquation(idea.valueEquation);
                        if (!ve) return idea.valueEquation ? <p className="leading-relaxed whitespace-pre-line text-xs opacity-80">{idea.valueEquation}</p> : null;
                        return (
                          <div className="space-y-2">
                            {ve.overall != null && (
                              <div className="text-xs font-semibold" style={{ fontFamily: "'JetBrains Mono', monospace" }}>
                                Value Equation — {ve.overall}/10
                              </div>
                            )}
                            {ve.factors.map((f) => (
                              <ValueEquationBar key={f.label} icon={f.icon} label={f.label} score={f.score} />
                            ))}
                          </div>
                        );
                      })()}
                      {(() => {
                        const mm = parseMarketMatrix(idea.marketMatrix);
                        if (!mm) return idea.marketMatrix ? <p className="leading-relaxed whitespace-pre-line text-xs opacity-80">{idea.marketMatrix}</p> : null;
                        return (
                          <div>
                            <div className="text-xs font-semibold mb-2" style={{ fontFamily: "'JetBrains Mono', monospace" }}>
                              Market Matrix — {mm.quadrant}
                            </div>
                            <MarketMatrixGrid uniqueness={mm.uniqueness} value={mm.value} quadrant={mm.quadrant} />
                          </div>
                        );
                      })()}
                    </div>
                  </details>
                )}
                {idea.acpFramework && (
                  <details className="pt-2 border-t border-black/10">
                    <summary className="text-[11px] uppercase tracking-wider opacity-50 cursor-pointer" style={{ fontFamily: "'JetBrains Mono', monospace" }}>
                      Audience / Community / Product Framework ▾
                    </summary>
                    <p className="mt-2 leading-relaxed whitespace-pre-line text-xs opacity-80">{idea.acpFramework}</p>
                  </details>
                )}
              </div>
            )}

            {tab === "Execution" && (
              <div className="space-y-3 text-sm">
                <div className="text-[10px] uppercase tracking-wider opacity-40" style={{ fontFamily: "'JetBrains Mono', monospace" }}>
                  Difficulty, phased plan, value ladder
                </div>
                <div className="flex items-center gap-2">
                  <Wrench size={14} className="opacity-60" />
                  <span className="text-[11px] uppercase tracking-wider opacity-50" style={{ fontFamily: "'JetBrains Mono', monospace" }}>
                    Difficulty: {idea.executionDifficulty?.score}/10
                  </span>
                </div>
                <p className="opacity-70 italic text-xs">{idea.executionDifficulty?.note}</p>
                <div className="pt-2">
                  <div className="text-[11px] uppercase tracking-wider opacity-50 mb-1" style={{ fontFamily: "'JetBrains Mono', monospace" }}>
                    Suggested Plan
                  </div>
                  <p className="leading-relaxed whitespace-pre-line">{safeText(idea.executionPlan)}</p>
                </div>
                {idea.valueLadderDetail && (
                  <details className="pt-2 border-t border-black/10">
                    <summary className="text-[11px] uppercase tracking-wider opacity-50 cursor-pointer" style={{ fontFamily: "'JetBrains Mono', monospace" }}>
                      Full Value Ladder ▾
                    </summary>
                    <p className="mt-2 leading-relaxed whitespace-pre-line text-xs opacity-80">{idea.valueLadderDetail}</p>
                  </details>
                )}
              </div>
            )}

            {tab === "Community" && (
              <div className="space-y-3 text-sm">
                <div className="text-[10px] uppercase tracking-wider opacity-40" style={{ fontFamily: "'JetBrains Mono', monospace" }}>
                  Reddit, Facebook, YouTube & other community signals
                </div>
                <div className="space-y-2">
                  {idea.communitySignals && Object.entries(idea.communitySignals).map(([k, v]) => (
                    <div key={k} className="flex items-center gap-2">
                      <Users size={13} className="opacity-50 shrink-0" />
                      <span className="font-semibold capitalize w-16 shrink-0">{k}</span>
                      <span className="opacity-70">{v}</span>
                    </div>
                  ))}
                </div>
                {idea.communitySignalsRich && Object.values(idea.communitySignalsRich).some((arr) => arr?.length) ? (
                  <div className="space-y-3 pt-2">
                    {Object.entries(idea.communitySignalsRich).map(([platform, communities]) =>
                      (communities || []).length > 0 ? (
                        <div key={platform}>
                          <div className="text-[11px] uppercase tracking-wider opacity-50 mb-1.5 capitalize" style={{ fontFamily: "'JetBrains Mono', monospace" }}>
                            {platform}
                          </div>
                          <div className="space-y-2">
                            {communities.map((community, i) => (
                              <details key={i} className="rounded-lg border border-black/10 overflow-hidden">
                                <summary className="cursor-pointer px-3 py-2 font-semibold flex items-center justify-between gap-2">
                                  <span className="truncate">{community.name || "Community"}</span>
                                  <ChevronRight size={14} className="opacity-40 shrink-0" />
                                </summary>
                                <div className="px-3 pb-3 space-y-2 border-t border-black/5 pt-2">
                                  {community.summary && (
                                    <p className="text-xs opacity-70 leading-relaxed">{community.summary}</p>
                                  )}
                                  {community.discussions?.length > 0 && (
                                    <div className="space-y-1.5">
                                      <div className="text-[10px] uppercase tracking-wider opacity-40">
                                        {community.discussions.length} discussion{community.discussions.length !== 1 ? "s" : ""} found
                                      </div>
                                      {community.discussions.map((d, di) => (
                                        <a
                                          key={di}
                                          href={d.url}
                                          target="_blank"
                                          rel="noopener noreferrer"
                                          className="flex items-center gap-2 text-xs px-2 py-1.5 rounded hover:bg-black/5 transition-colors"
                                          style={{ color: "#12151C" }}
                                        >
                                          <ExternalLink size={12} className="opacity-50 shrink-0" />
                                          <span className="truncate underline decoration-black/20">{d.title}</span>
                                        </a>
                                      ))}
                                    </div>
                                  )}
                                  {community.url && !community.discussions?.length && (
                                    <a
                                      href={community.url}
                                      target="_blank"
                                      rel="noopener noreferrer"
                                      className="inline-flex items-center gap-1 text-xs underline"
                                      style={{ color: "#6B8F71" }}
                                    >
                                      <ExternalLink size={12} />
                                      View source
                                    </a>
                                  )}
                                </div>
                              </details>
                            ))}
                          </div>
                        </div>
                      ) : null
                    )}
                  </div>
                ) : (
                  idea.communitySignalsDetail && (
                    <details className="pt-2 border-t border-black/10">
                      <summary className="text-[11px] uppercase tracking-wider opacity-50 cursor-pointer" style={{ fontFamily: "'JetBrains Mono', monospace" }}>
                        Full Community Breakdown ▾
                      </summary>
                      <p className="mt-2 leading-relaxed whitespace-pre-line text-xs opacity-80">{idea.communitySignalsDetail}</p>
                    </details>
                  )
                )}
              </div>
            )}
          </div>

          {/* Notes */}
          <div className="mt-4 pt-4 border-t border-black/10">
            <div className="text-[11px] uppercase tracking-wider opacity-50 mb-1" style={{ fontFamily: "'JetBrains Mono', monospace" }}>
              Your Notes
            </div>
            <textarea
              value={localNotes}
              onChange={(e) => setLocalNotes(e.target.value)}
              onBlur={() => onNotesChange(idea.id, localNotes)}
              placeholder="Jot down thoughts, angles, or why this caught your eye..."
              className="w-full text-sm p-2 rounded-lg border border-black/10 bg-white/50 resize-none focus:outline-none focus:ring-2"
              style={{ minHeight: "60px" }}
              rows={2}
            />
          </div>

          {/* Action CTAs */}
          <div className="mt-4 grid grid-cols-2 gap-2">
            <button
              onClick={() => onSummarize(idea)}
              className="flex items-center justify-center gap-2 py-3 rounded-lg font-bold text-sm transition-transform hover:scale-[1.01]"
              style={{ backgroundColor: "rgba(18,21,28,0.06)", color: "#12151C", fontFamily: "'JetBrains Mono', monospace" }}
            >
              <MessageCircle size={16} />
              Summarize
            </button>
            <button
              onClick={() => onAskClaude(idea)}
              className="flex items-center justify-center gap-2 py-3 rounded-lg font-bold text-sm transition-transform hover:scale-[1.01]"
              style={{ backgroundColor: "#12151C", color: "#E8A33D", fontFamily: "'JetBrains Mono', monospace" }}
            >
              <Sparkles size={16} />
              Build this
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function CopyPromptModal({ idea, onClose, mode = "build" }) {
  const [copied, setCopied] = useState(false);

  const buildPrompt = `I want to build "${idea.title}" — ${idea.tagline}

Here's the full research on this idea:

${idea.description}

Market gap: ${safeText(idea.marketGap)}
Suggested execution plan: ${safeText(idea.executionPlan)}
Execution difficulty: ${idea.executionDifficulty?.score}/10 — ${idea.executionDifficulty?.note}
Target: ${idea.categorization?.target} | Market: ${idea.categorization?.market} | Main competitor: ${idea.categorization?.competitor}

Top keywords: ${idea.keywords?.slice(0, 5).map(k => `${k.keyword} (${k.volume}/mo, +${k.growth}%)`).join(", ")}

My notes: ${idea.notes || "(none yet)"}

Let's scaffold this step by step — help me pick the right tech stack for a solo build, plan the MVP scope, and start building the actual project files, the way we've done with my other projects (Halal Finder, Gluco Diary, etc). Walk me through it like a real build session, not just a plan.`;

  const summarizePrompt = `Give me an in-depth summary of this business idea, pulling together everything below into a clear, organized read — not just a repeat of each section, but genuine synthesis: what's the core opportunity, why does it hold up (or not), what's the realistic path to building it, and what would you personally flag as the biggest risk or open question.

Idea: "${idea.title}"
${idea.tagline}

Full pitch:
${idea.description}

Scores: Opportunity ${idea.scores?.opportunity?.score}/10 (${idea.scores?.opportunity?.label}), Problem ${idea.scores?.problem?.score}/10 (${idea.scores?.problem?.label}), Feasibility ${idea.scores?.feasibility?.score}/10 (${idea.scores?.feasibility?.label}), Why Now ${idea.scores?.whyNow?.score}/10 (${idea.scores?.whyNow?.label})

Categorization: ${idea.categorization?.type} | ${idea.categorization?.market} | Target: ${idea.categorization?.target} | Competitor: ${idea.categorization?.competitor}

Market Gap:
${safeText(idea.marketGap)}

Execution Plan:
${safeText(idea.executionPlan)}

Execution Difficulty (${idea.executionDifficulty?.score}/10):
${safeText(idea.executionDifficulty?.note)}

Value Equation:
${safeText(idea.valueEquation)}

Market Matrix:
${safeText(idea.marketMatrix)}

Audience/Community/Product Framework:
${safeText(idea.acpFramework)}

Value Ladder:
${safeText(idea.valueLadderDetail)}

Proof & Signals:
${safeText(idea.proofSignals)}

Why Now (detail):
${safeText(idea.whyNowDetail)}

Community Signals: ${JSON.stringify(idea.communitySignals)}
${safeText(idea.communitySignalsDetail)}

Keywords: ${idea.keywords?.map(k => `${k.keyword} (${k.volume}/mo, ${k.growth > 0 ? "+" : ""}${k.growth}%)`).join(", ")}

My notes: ${idea.notes || "(none yet)"}`;

  const prompt = mode === "summarize" ? summarizePrompt : buildPrompt;
  const title = mode === "summarize" ? `Summarize "${idea.title}"` : `Start building "${idea.title}"`;
  const description = mode === "summarize"
    ? "Copy this prompt and paste it into a chat with Claude for an in-depth, synthesized summary of this idea — not just a re-listing of the sections, but genuine analysis."
    : "Copy this prompt and paste it into your chat with Claude. It carries over everything captured about this idea so the build session starts with full context — no re-explaining needed.";

  const copy = () => {
    navigator.clipboard?.writeText(prompt).catch(() => {});
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" style={{ backgroundColor: "rgba(18,21,28,0.7)" }}>
      <div className="max-w-lg w-full rounded-xl p-6" style={{ backgroundColor: "#F7F4EC" }}>
        <div className="flex items-start justify-between mb-3">
          <h3 className="text-lg font-bold" style={{ fontFamily: "'Fraunces', serif" }}>
            {title}
          </h3>
          <button onClick={onClose}><X size={18} /></button>
        </div>
        <p className="text-sm opacity-70 mb-4 leading-relaxed">
          {description}
        </p>
        <div className="rounded-lg p-3 mb-4 text-xs max-h-48 overflow-y-auto whitespace-pre-wrap" style={{ backgroundColor: "rgba(0,0,0,0.05)", fontFamily: "'JetBrains Mono', monospace" }}>
          {prompt}
        </div>
        <button
          onClick={copy}
          className="w-full py-3 rounded-lg font-bold text-sm flex items-center justify-center gap-2"
          style={{ backgroundColor: "#12151C", color: copied ? "#6B8F71" : "#E8A33D" }}
        >
          {copied ? <CheckCircle2 size={16} /> : <MessageCircle size={16} />}
          {copied ? "Copied — paste into a new chat" : "Copy build prompt"}
        </button>
      </div>
    </div>
  );
}

// Set this to your published GitHub Pages / raw.githubusercontent.com base
// URL once your repo is live, e.g.:
//   "https://raw.githubusercontent.com/<you>/<repo>/main"
// or, if using GitHub Pages:
//   "https://<you>.github.io/<repo>"
// Leave as null to run on the built-in seed data only (useful for testing
// the app itself before the scraper/repo exists).
const LIBRARY_BASE_URL = "https://raw.githubusercontent.com/zarshadshah/idea-browser-library/main";

async function loadLibraryFromRemote(baseUrl) {
  const manifestRes = await fetch(`${baseUrl}/scraper/library/manifest.json`);
  if (!manifestRes.ok) throw new Error(`manifest fetch failed: ${manifestRes.status}`);
  const manifest = await manifestRes.json();

  const ideas = await Promise.all(
    manifest.ideas.map(async (entry) => {
      const res = await fetch(`${baseUrl}/scraper/${entry.path}`);
      if (!res.ok) throw new Error(`idea fetch failed for ${entry.id}: ${res.status}`);
      return res.json();
    })
  );
  return ideas;
}

function IdeaLibrary() {
  const [ideas, setIdeas] = useState(SEED_IDEAS);
  const [openId, setOpenId] = useState(null);
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [modalIdea, setModalIdea] = useState(null);
  const [modalMode, setModalMode] = useState("build");
  const [loaded, setLoaded] = useState(false);
  const [loadError, setLoadError] = useState(null);
  const [usingRemote, setUsingRemote] = useState(false);

  // Load remote library (if configured) then overlay persisted status/notes
  useEffect(() => {
    (async () => {
      let baseIdeas = SEED_IDEAS;

      if (LIBRARY_BASE_URL) {
        try {
          const remoteIdeas = await loadLibraryFromRemote(LIBRARY_BASE_URL);
          if (remoteIdeas.length > 0) {
            baseIdeas = remoteIdeas;
            setUsingRemote(true);
          }
        } catch (e) {
          console.error("Falling back to seed data:", e);
          setLoadError(e.message);
        }
      }

      try {
        const result = await window.storage?.get("idea-library-state");
        if (result?.value) {
          const saved = JSON.parse(result.value);
          baseIdeas = baseIdeas.map((idea) => ({ ...idea, ...(saved[idea.id] || {}) }));
        }
      } catch (e) {
        // no saved state yet
      }

      setIdeas(baseIdeas);
      setLoaded(true);
    })();
  }, []);

  const persist = useCallback(async (updatedIdeas) => {
    try {
      const stateToSave = {};
      updatedIdeas.forEach((idea) => {
        stateToSave[idea.id] = { status: idea.status, notes: idea.notes };
      });
      await window.storage?.set("idea-library-state", JSON.stringify(stateToSave));
    } catch (e) {
      console.error("Failed to persist:", e);
    }
  }, []);

  const updateIdea = (id, patch) => {
    setIdeas((prev) => {
      const next = prev.map((i) => (i.id === id ? { ...i, ...patch } : i));
      persist(next);
      return next;
    });
  };

  const filtered = ideas.filter((idea) => {
    const matchesQuery =
      !query ||
      idea.title.toLowerCase().includes(query.toLowerCase()) ||
      idea.tagline.toLowerCase().includes(query.toLowerCase()) ||
      idea.keywords?.some((k) => k.keyword.toLowerCase().includes(query.toLowerCase()));
    const matchesStatus = statusFilter === "all" || idea.status === statusFilter;
    return matchesQuery && matchesStatus;
  });

  const counts = ideas.reduce((acc, i) => {
    acc[i.status] = (acc[i.status] || 0) + 1;
    return acc;
  }, {});

  if (!loaded) return null;

  return (
    <div className="min-h-screen" style={{ backgroundColor: "#12151C" }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,600;9..144,900&family=JetBrains+Mono:wght@400;500;700;800&family=Inter:wght@400;500;600&display=swap');
        * { font-family: 'Inter', sans-serif; }
        textarea:focus { --tw-ring-color: #E8A33D; }
      `}</style>

      <div className="max-w-3xl mx-auto px-4 py-10">
        {/* Header */}
        <div className="mb-8">
          <div className="flex items-center gap-2 mb-2">
            <div className="w-2 h-2 rounded-full" style={{ backgroundColor: "#E8A33D" }} />
            <span className="text-[11px] uppercase tracking-[0.2em]" style={{ color: "#E8A33D", fontFamily: "'JetBrains Mono', monospace" }}>
              Idea of the Day — Case Files
            </span>
          </div>
          <h1
            className="text-4xl font-black mb-2"
            style={{ color: "#F7F4EC", fontFamily: "'Fraunces', serif" }}
          >
            Your Build Library
          </h1>
          <p className="text-sm" style={{ color: "rgba(247,244,236,0.5)" }}>
            {ideas.length} ideas archived · {counts.building || 0} in progress · {counts.launched || 0} launched
          </p>
          <p className="text-xs mt-1" style={{ color: usingRemote ? "#6B8F71" : "#E8A33D", fontFamily: "'JetBrains Mono', monospace" }}>
            {usingRemote
              ? "● Live data from your repo"
              : loadError
              ? `● Showing sample data (couldn't reach library: ${loadError})`
              : "● Showing sample data — set LIBRARY_BASE_URL to connect your repo"}
          </p>
        </div>

        {/* Search + filters */}
        <div className="mb-6 space-y-3">
          <div className="relative">
            <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 opacity-40" style={{ color: "#F7F4EC" }} />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search ideas or keywords..."
              className="w-full pl-9 pr-4 py-2.5 rounded-lg text-sm focus:outline-none"
              style={{ backgroundColor: "rgba(247,244,236,0.08)", color: "#F7F4EC", border: "1px solid rgba(247,244,236,0.15)" }}
            />
          </div>
          <div className="flex gap-2 flex-wrap">
            <button
              onClick={() => setStatusFilter("all")}
              className="text-xs px-3 py-1.5 rounded-full border"
              style={{
                borderColor: "rgba(247,244,236,0.2)",
                backgroundColor: statusFilter === "all" ? "#E8A33D" : "transparent",
                color: statusFilter === "all" ? "#12151C" : "#F7F4EC",
              }}
            >
              All ({ideas.length})
            </button>
            {Object.entries(STATUS_CONFIG).map(([key, c]) => (
              <button
                key={key}
                onClick={() => setStatusFilter(key)}
                className="text-xs px-3 py-1.5 rounded-full border"
                style={{
                  borderColor: c.color,
                  backgroundColor: statusFilter === key ? c.color : "transparent",
                  color: statusFilter === key ? "#F7F4EC" : c.color,
                }}
              >
                {c.label} ({counts[key] || 0})
              </button>
            ))}
          </div>
        </div>

        {/* Cards */}
        <div className="space-y-4">
          {filtered.length === 0 && (
            <div className="text-center py-16" style={{ color: "rgba(247,244,236,0.4)" }}>
              No ideas match your search.
            </div>
          )}
          {filtered.map((idea) => (
            <IdeaCard
              key={idea.id}
              idea={idea}
              isOpen={openId === idea.id}
              onToggle={() => setOpenId(openId === idea.id ? null : idea.id)}
              onStatusChange={(id, status) => updateIdea(id, { status })}
              onNotesChange={(id, notes) => updateIdea(id, { notes })}
              onAskClaude={(idea) => { setModalIdea(idea); setModalMode("build"); }}
              onSummarize={(idea) => { setModalIdea(idea); setModalMode("summarize"); }}
            />
          ))}
        </div>

        <div className="mt-10 text-center text-xs" style={{ color: "rgba(247,244,236,0.3)" }}>
          New ideas are added here automatically as they're captured each day.
        </div>
      </div>

      {modalIdea && <CopyPromptModal idea={modalIdea} mode={modalMode} onClose={() => setModalIdea(null)} />}
    </div>
  );
}

// Expose to the global scope so index.html's plain <script> mounting code
// can find and render it (no ES module system available here).
window.IdeaLibraryApp = IdeaLibrary;
