"""Local-only visual system; no external fonts, trackers or assets."""
STYLE = """
<style>
:root{color-scheme:dark;--ink:#e9effb;--muted:#8392ac;--line:#22304a;--mint:#54efc3;--violet:#a899ff}
.stApp{background:radial-gradient(ellipse at 75% 0%,#18203a66,transparent 42%),#080c15;color:var(--ink)}
[data-testid="stHeader"]{background:#080c15dd;border-bottom:1px solid #192338}
[data-testid="stSidebar"]{background:linear-gradient(180deg,#101727,#0a101c);border-right:1px solid #202b41}
.block-container{max-width:1560px;padding:2.5rem 2.5rem 3rem}
h1,h2,h3{color:var(--ink)!important;letter-spacing:-.035em}h1{font-size:2rem!important}h3{font-size:1.12rem!important}
p,li{line-height:1.75}.subtle{color:var(--muted);font-size:13px;line-height:1.8}
.brand{font-size:22px;font-weight:850;letter-spacing:-1px;margin:2px 0 5px}.brand span{color:var(--mint)}
.brand-sub{font:10px monospace;letter-spacing:.19em;color:#7688a9;margin-bottom:28px}
.eyebrow,.kicker{font:10px monospace;letter-spacing:.2em;color:#93a2c0;font-weight:600;margin-bottom:12px}
.hero{border:1px solid #2d3d5b;border-radius:18px;background:radial-gradient(ellipse at 90% 10%,#36547b40,transparent 65%),linear-gradient(120deg,#131d30,#101725);padding:28px 30px;margin-bottom:22px;position:relative;overflow:hidden}
.hero:after{content:'';position:absolute;right:24px;top:20px;width:70px;height:70px;border:1px solid #6477b940;border-radius:50%;box-shadow:0 0 0 16px #6477b910,0 0 0 33px #6477b908;pointer-events:none}
.hero h1{margin:0 0 8px;padding:0;font-size:32px!important;line-height:1.3;max-width:85%}.hero p{color:#98a9c4;margin:0;max-width:85%;font-size:13px}
.hero-footer{display:flex;gap:8px;flex-wrap:wrap;margin-top:22px}
.pill,.tag{display:inline-block;padding:5px 10px;border:1px solid #31415c;border-radius:6px;color:#afbdd3;background:#162136;font:11px monospace;letter-spacing:.02em}
.pill.green,.tag.live{border-color:#315b51;background:#12352c;color:#6bf0c9}.pill.amber,.tag.demo{border-color:#655334;background:#33291a;color:#f3cb7c}.pill.red{border-color:#603746;color:#ffa1b4;background:#321e29}
.section-head{display:flex;justify-content:space-between;align-items:center;gap:12px;margin:24px 0 14px}.section-head h3{margin:0;padding:0}.section-head small{font:10px monospace;color:#7e91b1;letter-spacing:.1em}
.card,.op-card{border:1px solid var(--line);background:linear-gradient(145deg,#131d2e,#0f1726);border-radius:13px;padding:20px;margin-bottom:14px}
.op-card{min-height:144px;border-top:2px solid #435575}.op-card.long{border-top-color:var(--mint)}.op-card.short{border-top-color:#ff8ba9}
.op-top{display:flex;justify-content:space-between;align-items:center;gap:10px}.op-symbol{font-size:18px;font-weight:750;letter-spacing:-.5px}.op-price{font:24px monospace;font-weight:650;margin:14px 0 8px}.op-detail{font-size:11px;color:#8fa1bd;line-height:1.6}
.metric-label{font-size:11px;color:#8fa2bf}.metric-value{font-size:29px;font-weight:750;letter-spacing:-1px;margin-top:8px}.metric-foot{font-size:11px;color:#7386a6;margin-top:8px}.up{color:var(--mint)}.down{color:#ff8ba9}
[data-testid="stMetric"]{border:1px solid var(--line);background:linear-gradient(150deg,#142035,#101725);padding:18px 20px;border-radius:12px;min-height:108px}
[data-testid="stMetricLabel"]{color:#8fa2bf;font-size:12px}[data-testid="stMetricValue"]{font-size:29px;letter-spacing:-1px;font-family:ui-monospace,monospace}
[data-testid="stButton"] button,[data-testid="stDownloadButton"] button{border-radius:8px;border-color:#2c3a53;transition:border-color .15s ease,background .15s ease}
[data-testid="stButton"] button:hover{border-color:#54efc3!important;color:#72f1cf!important}
button[kind="primary"]{background:var(--mint)!important;color:#08251c!important;border-color:var(--mint)!important;font-weight:750!important}
[data-baseweb="tab-list"]{gap:25px;border-bottom:1px solid #26344d;margin-bottom:16px}
[data-baseweb="tab"]{color:#8fa2bf!important;padding:13px 2px;font-size:13px}
[aria-selected="true"][data-baseweb="tab"]{color:var(--mint)!important}
[data-testid="stSidebar"] [data-testid="stRadio"] label[data-baseweb="radio"]{padding:8px 10px;border-radius:7px;margin:2px 0;border:1px solid transparent}
[data-testid="stSidebar"] [data-testid="stRadio"] label[data-baseweb="radio"]:has(input:checked){background:#17312f;border-color:#31534e}
[data-testid="stDataFrame"]{border:1px solid #22304a;border-radius:10px;overflow:hidden}
[data-testid="stExpander"]{border-color:#26344c!important;border-radius:10px!important;background:#0f172380}
[data-testid="stAlert"]{border-radius:10px}.signal-title{font-size:32px;font-weight:800}.signal-top{display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:14px}
.rule{height:1px;background:#263248;margin:16px 0}.factor{display:flex;justify-content:space-between;gap:16px;padding:11px 0;border-bottom:1px solid #202c40;font-size:13px}.factor small{color:#899bb5;display:block;margin-top:5px;line-height:1.5}
.news-title{font-size:16px;line-height:1.7;color:#e5edf9;text-decoration:none!important;font-weight:600}.news-title:hover{color:var(--mint)}.news-meta{color:#8a9bb6;font-size:11px;margin-top:10px}.section-title{font-size:19px;font-weight:700;margin:14px 0}
.footer{border-top:1px solid #202c40;color:#7385a1;font-size:11px;padding-top:20px;margin-top:28px;line-height:1.9}
.health-row{display:flex;align-items:center;justify-content:space-between;gap:16px;border-bottom:1px solid #22304a;padding:14px 0}.health-name{font-size:13px;font-weight:650}.health-note{font-size:11px;color:#8fa1bd;margin-top:4px}.health-state{font:11px monospace;white-space:nowrap;color:#afbdd3}
@media(min-width:1000px){[data-testid="stSidebar"]{min-width:255px!important;max-width:255px!important}}
@media(max-width:700px){.block-container{padding:1.2rem 1rem 2rem}.hero{padding:22px 18px}.hero h1{font-size:25px!important}.hero:after{right:12px;width:40px;height:40px}.hero p{max-width:95%}.op-card{min-height:120px}[data-testid="stMetric"]{padding:13px;min-height:90px}[data-testid="stMetricValue"]{font-size:23px}.section-head{align-items:flex-start}}
@media(prefers-reduced-motion:reduce){*{transition:none!important;animation:none!important}}
.growth-flow{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:10px;margin:16px 0 24px}.growth-step{border:1px solid #34476a;border-radius:14px;padding:18px 14px;background:linear-gradient(145deg,#1d2947,#101a2a);min-width:0}.growth-step b{display:block;color:#7c98ff;font:26px monospace;margin-bottom:14px}.growth-step strong{display:block;color:#e8f0ff;font-size:14px}.growth-step small{display:block;color:#98accb;margin-top:10px;font-size:11px;line-height:1.7}.hero{background:radial-gradient(ellipse at 90% 10%,#6159ba55,transparent 60%),linear-gradient(120deg,#132c35,#15192f)}
@media(max-width:900px){.growth-flow{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:450px){.growth-step{padding:12px}.growth-step b{font-size:21px}}
.front-levels{display:flex;flex-wrap:wrap;gap:20px;font-size:18px;margin:12px 0 18px}.front-levels b{display:block;font:24px monospace;margin-top:6px}
.front-status{display:flex;gap:12px;flex-wrap:wrap;margin:12px 0}.front-status span{padding:8px 12px;background:#142135;border:1px solid #2b3b56;border-radius:8px;color:#a7bad7;font-size:12px}.front-status b{color:#60e6c3;font:18px monospace;margin-left:7px}
</style>
"""
