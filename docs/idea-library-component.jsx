// Adapted for plain-browser use (no bundler): React and lucide are loaded
// as global UMD scripts by index.html, so we destructure from those
// globals instead of using ES module imports.
const { useState, useEffect, useCallback } = React;

// The plain "lucide" package (as opposed to "lucide-react") exposes each
// icon as a PascalCase-named array of SVG node descriptors — e.g.
// ChevronDown = [["path", {d: "..."}], ...] — meant for vanilla-JS use via
// lucide.createElement(...) or the data-lucide="..." HTML attribute
// approach, NOT as React components. Using these arrays directly as JSX
// tags (<ChevronDown />) makes React try to render `undefined` as an
// element type, crashing with a cryptic minified invariant error. This
// adapter converts any lucide icon-node array into a real, usable React
// function component on the fly.
function makeLucideIcon(iconNode) {
  return function LucideIcon({ size = 24, className, style, ...rest }) {
    return React.createElement(
      "svg",
      {
        xmlns: "http://www.w3.org/2000/svg",
        width: size,
        height: size,
        viewBox: "0 0 24 24",
        fill: "none",
        stroke: "currentColor",
        strokeWidth: 2,
        strokeLinecap: "round",
        strokeLinejoin: "round",
        className,
        style,
        ...rest,
      },
      iconNode.map(([tag, attrs], i) => React.createElement(tag, { key: i, ...attrs }))
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

function KeywordRow({ kw }) {
  const growthColor = kw.growth > 500 ? "#4A7C59" : kw.growth > 50 ? "#6B8F71" : "#8B8577";
  return (
    <div className="flex items-center justify-between py-2 border-b border-black/5 last:border-0">
      <span className="text-sm">{kw.keyword}</span>
      <div className="flex items-center gap-3 shrink-0" style={{ fontFamily: "'JetBrains Mono', monospace" }}>
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
          <div className="flex gap-1 mb-4 border-b border-black/10">
            {TABS.map((t) => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className="px-3 py-2 text-xs font-semibold uppercase tracking-wide -mb-px border-b-2 transition-colors"
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
                  <details className="pt-2 border-t border-black/10">
                    <summary className="text-[11px] uppercase tracking-wider opacity-50 cursor-pointer" style={{ fontFamily: "'JetBrains Mono', monospace" }}>
                      Value Equation & Market Matrix ▾
                    </summary>
                    <p className="mt-2 leading-relaxed whitespace-pre-line text-xs opacity-80">{idea.valueEquation}</p>
                    <p className="mt-2 leading-relaxed whitespace-pre-line text-xs opacity-80">{idea.marketMatrix}</p>
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
                {idea.communitySignalsDetail && (
                  <details className="pt-2 border-t border-black/10">
                    <summary className="text-[11px] uppercase tracking-wider opacity-50 cursor-pointer" style={{ fontFamily: "'JetBrains Mono', monospace" }}>
                      Full Community Breakdown ▾
                    </summary>
                    <p className="mt-2 leading-relaxed whitespace-pre-line text-xs opacity-80">{idea.communitySignalsDetail}</p>
                  </details>
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
  const manifestRes = await fetch(`${baseUrl}/library/manifest.json`);
  if (!manifestRes.ok) throw new Error(`manifest fetch failed: ${manifestRes.status}`);
  const manifest = await manifestRes.json();

  const ideas = await Promise.all(
    manifest.ideas.map(async (entry) => {
      const res = await fetch(`${baseUrl}/${entry.path}`);
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
