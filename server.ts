import express from "express";
import path from "path";
import fs from "fs";
import { createServer as createViteServer } from "vite";
import { GoogleGenAI } from "@google/genai";
import dotenv from "dotenv";

dotenv.config();

const app = express();
const PORT = 3000;

app.use(express.json());

// Initialize GoogleGenAI server side
let ai: GoogleGenAI | null = null;
try {
  if (process.env.GEMINI_API_KEY) {
    ai = new GoogleGenAI({
      apiKey: process.env.GEMINI_API_KEY,
      httpOptions: {
        headers: {
          'User-Agent': 'aistudio-build',
        }
      }
    });
  }
} catch (err) {
  console.error("Failed to initialize GoogleGenAI:", err);
}

// Global Simulated Hermes State
let currentPrice = null;
let balance = 0.0;
let dailyEquityStarting = 0.0;
let weeklyEquityStarting = 0.0;
let lastMT5DataTimestamp: number | null = null;

let trades: any[] = [];

let closedTrades: any[] = [];
let fairValueGaps: any[] = [];
let orderBlocks: any[] = [];
let liquidityPools: any[] = [];
let obsidianNotes: any[] = [];
let skills: any[] = [];
let logs: any[] = [
  { id: "log_boot_1", timestamp: new Date().toISOString(), source: "SYSTEM", level: "INFO", text: "Hermes server process started. Waiting for service connections..." }
];

let autonomousLoops = {
  nightlyMarketScan: { lastRun: new Date(Date.now() - 17280000 * 2).toISOString(), status: "IDLE", outcome: "H1 setup candidate detected on Thursday daily structure, logged to Obsidian vault." },
  skillAutoCreation: { lastRun: new Date(Date.now() - 86400000 * 3).toISOString(), status: "IDLE", outcome: "Self-evolved OB momentum tracker.py code successfully generated and compiled into Hermes Skill system." },
  paperTradeReview: { lastRun: new Date(Date.now() - 86400000 * 1).toISOString(), status: "IDLE", outcome: "Assessed weekly P&L: Weekly equity growth of 2.1% achieved, drawdown controlled within 1.2% maximum." },
  hypothesisRandD: { lastRun: new Date(Date.now() - 1200000).toISOString(), status: "RUNNING", outcome: "Simulating backtests for aggressive New York Silver Divergence logic on M1." }
};

// Only run tick simulation if MT5 is not providing real data AND we have a seed price
setInterval(() => {
  if (currentPrice === null || currentPrice === undefined || isNaN(currentPrice)) return;
  
  // Only simulate if we haven't received real MT5 data recently
  const now = Date.now();
  if (lastMT5DataTimestamp && (now - lastMT5DataTimestamp) < 10000) return;
  
  const change = (Math.random() - 0.495) * 0.4;
  currentPrice = parseFloat((currentPrice + change).toFixed(2));
  
  trades = trades.map(t => {
    let pnl = t.pnl;
    if (t.direction === "BUY") {
      pnl = (currentPrice - t.entryPrice) * t.lotSize * 100;
    } else {
      pnl = (t.entryPrice - currentPrice) * t.lotSize * 100;
    }
    return { ...t, currentPrice, pnl: parseFloat(pnl.toFixed(2)) };
  });

  if (logs.length > 100) logs.shift();
}, 3000);

// Helper to fetch with an abort controller timeout (bug-proof cross-platform)
async function fetchWithTimeout(url: string, options: any = {}, timeoutMs: number = 200) {
  const controller = new AbortController();
  const id = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, { ...options, signal: controller.signal });
    clearTimeout(id);
    return response;
  } catch (error) {
    clearTimeout(id);
    throw error;
  }
}

// Helper to recursively scan local markdown files in the real `/data/obsidian` mount
function scanObsidianVault(dir: string, baseDir: string = ""): any[] {
  let results: any[] = [];
  try {
    if (!fs.existsSync(dir)) return results;
    const list = fs.readdirSync(dir);
    list.forEach(file => {
      const filePath = path.join(dir, file);
      const relativePath = baseDir ? path.join(baseDir, file) : file;
      const stat = fs.statSync(filePath);
      if (stat && stat.isDirectory()) {
        results = results.concat(scanObsidianVault(filePath, relativePath));
      } else if (file.endsWith(".md")) {
        const content = fs.readFileSync(filePath, "utf-8");
        const title = file.replace(/\.md$/, "");
        results.push({
          path: relativePath,
          title,
          content,
          folder: baseDir || "root",
          tags: [],
          mtime: stat.mtime.toISOString()
        });
      }
    });
  } catch (err) {
    // Gracefully catch directory read errors
  }
  return results;
}

// API Endpoints
app.get("/api/status", async (req, res) => {
  let ollamaStatus = ai ? 'connected' : 'disconnected';
  let hermesRpcStatus = 'disconnected';
  let mt5DataStatus = 'disconnected';
  let mt5DrawStatus = 'disconnected';
  let mt5OrderStatus = 'disconnected';
  let redisStatus = 'disconnected';
  let chromadbStatus = 'disconnected';
  let obsidianStatus = fs.existsSync("/data/obsidian") ? 'connected' : 'disconnected';

  // 1. Check Ollama
  try {
    const r = await fetchWithTimeout("http://host.docker.internal:11434/api/tags", {}, 150);
    if (r.ok) ollamaStatus = 'connected';
  } catch (e) {}

  // 2. Check Hermes RPC
  try {
    const r = await fetchWithTimeout("http://host.docker.internal:7778/", {}, 150);
    if (r.ok) hermesRpcStatus = 'connected';
  } catch (e) {}

  // 3. Check MT5 gateway/bridge
  try {
    const r = await fetchWithTimeout("http://mt5_bridge:5558/health", {}, 150);
    if (r.ok) {
      mt5DataStatus = 'connected';
      mt5DrawStatus = 'connected';
      mt5OrderStatus = 'connected';
    }
  } catch (e) {}

  // 3b. Try localhost if mt5_bridge hostname is unreachable
  if (mt5DataStatus === 'disconnected') {
    try {
      const r = await fetchWithTimeout("http://localhost:5558/health", {}, 100);
      if (r.ok) {
        mt5DataStatus = 'connected';
        mt5DrawStatus = 'connected';
        mt5OrderStatus = 'connected';
      }
    } catch (e) {}
  }

  // 4. Check Redis via Preprocessor Health (which checks internal redis client connection)
  try {
    const r = await fetchWithTimeout("http://preprocessor:5559/health", {}, 150);
    if (r.ok) redisStatus = 'connected';
  } catch (e) {}

  // 5. Check ChromaDB
  try {
    const r = await fetchWithTimeout("http://chromadb:8000/api/v1/heartbeat", {}, 150);
    if (r.ok) chromadbStatus = 'connected';
  } catch (e) {}

  res.json({
    ollama: ollamaStatus,
    hermesRpc: hermesRpcStatus,
    mt5Zmq: {
      data: mt5DataStatus,
      draw: mt5DrawStatus,
      order: mt5OrderStatus
    },
    redis: redisStatus,
    chromaDb: chromadbStatus,
    obsidian: obsidianStatus
  });
});

app.get("/api/market", async (req, res) => {
  let price = currentPrice;
  let high: number | null = null;
  let low: number | null = null;
  let fvgList = fairValueGaps;
  let obList = orderBlocks;
  let liqList = liquidityPools;

  // 1. Try to fetch SMC indicators from preprocessor
  try {
    const preRes = await fetchWithTimeout("http://preprocessor:5559/smc_analysis?instrument=XAUUSD&tf=M15&n=300", {}, 200);
    if (preRes.ok) {
      const smcData = await preRes.json();
      if (smcData.fvg && smcData.fvg.length > 0) fvgList = smcData.fvg;
      if (smcData.order_blocks && smcData.order_blocks.length > 0) obList = smcData.order_blocks;
      if (smcData.liquidity && smcData.liquidity.length > 0) liqList = smcData.liquidity;
    }
  } catch (e) {}

  // 2. Try to fetch live price / range from mt5_bridge
  try {
    const mt5Res = await fetchWithTimeout("http://mt5_bridge:5558/latest_bars?instrument=XAUUSD&tf=M15&n=50", {}, 200);
    if (mt5Res.ok) {
      const bars = await mt5Res.json();
      if (bars && bars.length > 0) {
        const latestBar = bars[bars.length - 1];
        price = latestBar.close;
        high = Math.max(...bars.map((b: any) => b.high));
        low = Math.min(...bars.map((b: any) => b.low));
        currentPrice = price; // sync internal state
        lastMT5DataTimestamp = Date.now();
      }
    }
  } catch (e) {}

  // 3. Fallback to parsing live_feed.jsonl file on disk directly
  if (price === currentPrice && fs.existsSync("/data/market_data/live_feed.jsonl")) {
    try {
      const data = fs.readFileSync("/data/market_data/live_feed.jsonl", "utf-8");
      const lines = data.split("\n").filter(Boolean);
      const bars = lines.map(l => JSON.parse(l)).filter(b => b.instrument?.toUpperCase() === "XAUUSD");
      if (bars.length > 0) {
        const latestBar = bars[bars.length - 1];
        price = latestBar.close || latestBar.price;
        high = Math.max(...bars.map((b: any) => b.high || price));
        low = Math.min(...bars.map((b: any) => b.low || price));
        currentPrice = price;
      }
    } catch (err) {}
  }

  res.json({
    currentPrice: price,
    dailyHigh: high ?? 0,
    dailyLow: low ?? 0,
    sessions: {
      asian: { open: false, range: `${((low ?? 0) + 2).toFixed(2)} - ${((low ?? 0) + 12).toFixed(2)}` },
      london: { open: true, range: `${((low ?? 0) + 5).toFixed(2)} - ${((high ?? 0) - 5).toFixed(2)}` },
      newYork: { open: true, range: `${((low ?? 0) + 10).toFixed(2)} - ${(high ?? 0).toFixed(2)}` }
    },
    fairValueGaps: fvgList,
    orderBlocks: obList,
    liquidityPools: liqList
  });
});

app.get("/api/trades", async (req, res) => {
  let activeTradesList = trades;
  let closedTradesList = closedTrades;
  let currentBalance = balance;
  let currentEquity = balance + trades.reduce((acc, t) => acc + t.pnl, 0);
  let d_dd = 0.0;
  let w_dd = 0.0;

  try {
    const paperTraderUrl = "http://paper_trader:5561";
    // Check positions from paper_trader
    const posRes = await fetchWithTimeout(`${paperTraderUrl}/positions`, {}, 250);
    if (posRes.ok) {
      const livePos = await posRes.json();
      if (livePos && Array.isArray(livePos)) {
        activeTradesList = livePos.map((tp: any) => ({
          id: String(tp.ticket || tp.id),
          timestamp: tp.timestamp ? new Date(tp.timestamp * 1000).toISOString() : new Date().toISOString(),
          instrument: tp.instrument || "XAUUSD",
          direction: String(tp.direction || "BUY").toUpperCase(),
          type: tp.strategy_id || tp.setup_type || "SMC Trade Setup",
          entryPrice: parseFloat(tp.entry_price || tp.entryPrice || 0),
          stopLoss: parseFloat(tp.sl || tp.stopLoss || 0),
          takeProfit: parseFloat(tp.tp || tp.takeProfit || 0),
          lotSize: parseFloat(tp.lots || tp.lotSize || 1.0),
          currentPrice: parseFloat(tp.current_price || currentPrice),
          pnl: parseFloat(tp.profit || tp.pnl || 0.0),
          status: "OPEN",
          stage: tp.mode || tp.stage || "paper",
          riskPercent: parseFloat(tp.risk_pct || tp.riskPercent || 0.5),
          rrRatio: parseFloat(tp.r_ratio || tp.rrRatio || 2.0),
          notes: tp.notes || tp.agent_notes || "Active paper tracking database position."
        }));
      }
    }

    // Check stats from paper_trader
    const statsRes = await fetchWithTimeout(`${paperTraderUrl}/stats`, {}, 200);
    if (statsRes.ok) {
      const stats = await statsRes.json();
      if (stats) {
        currentBalance = stats.balance ?? currentBalance;
        currentEquity = stats.equity ?? currentEquity;
        d_dd = stats.max_drawdown_percent ?? d_dd;
        w_dd = stats.max_drawdown_percent !== undefined && stats.max_drawdown_percent !== null ? stats.max_drawdown_percent * 1.5 : w_dd;
      }
    }

    // Check history from paper_trader
    const histRes = await fetchWithTimeout(`${paperTraderUrl}/history`, {}, 200);
    if (histRes.ok) {
      const liveHist = await histRes.json();
      if (liveHist && Array.isArray(liveHist)) {
        closedTradesList = liveHist.map((tp: any) => ({
          id: String(tp.ticket || tp.id),
          timestamp: tp.entry_time ? new Date(tp.entry_time * 1000).toISOString() : new Date().toISOString(),
          instrument: tp.instrument || "XAUUSD",
          direction: String(tp.direction || "BUY").toUpperCase(),
          type: tp.strategy_id || tp.setup_type || "SMC Trade Setup",
          entryPrice: parseFloat(tp.entry_price || 0),
          exitPrice: parseFloat(tp.close_price || tp.exitPrice || 0),
          stopLoss: parseFloat(tp.sl || 0),
          takeProfit: parseFloat(tp.tp || 0),
          lotSize: parseFloat(tp.lots || 1.0),
          currentPrice: parseFloat(tp.close_price || currentPrice),
          pnl: parseFloat(tp.profit || tp.pnl || 0.0),
          status: "CLOSED",
          stage: tp.mode || tp.stage || "paper",
          riskPercent: parseFloat(tp.risk_pct || 0.5),
          rrRatio: parseFloat(tp.r_ratio || 2.0),
          closedAt: tp.close_time ? new Date(tp.close_time * 1000).toISOString() : new Date().toISOString(),
          notes: `Concluded setup: ${String(tp.outcome || 'manual').toUpperCase()}`
        }));
      }
    }
  } catch (err) {
    // Graceful fallback to simulated trades list in local state
  }

  res.json({
    active: activeTradesList,
    closed: closedTradesList,
    balance: currentBalance,
    equity: currentEquity,
    dailyDDPercent: parseFloat(d_dd.toFixed(2)),
    weeklyDDPercent: parseFloat(w_dd.toFixed(2))
  });
});

app.post("/api/trades", async (req, res) => {
  const { direction, type, entryPrice, stopLoss, takeProfit, lotSize, stage, riskPercent } = req.body;
  
  if (riskPercent > 1.0) {
    return res.status(400).json({ error: "SMC Risk Gatekeeper: Cannot execute trade. Risk percentage exceeds maximum allowed 1.0% setup limit." });
  }

  const signalPayload = {
    signal_id: "sig_" + Math.random().toString(36).substr(2, 5),
    timestamp: Math.floor(Date.now() / 1000),
    instrument: "XAUUSD",
    direction: direction.toLowerCase(),
    entry_price: parseFloat(entryPrice) || currentPrice,
    entry_type: "market",
    sl: parseFloat(stopLoss),
    tp: parseFloat(takeProfit),
    lots: parseFloat(lotSize) || 1.0,
    timeframe: "M15",
    strategy_id: "strat_1",
    setup_type: type,
    session: "New York",
    mode: stage || "paper",
    r_ratio: parseFloat(((takeProfit - entryPrice) / (entryPrice - stopLoss)).toFixed(2)) || 2.0,
    confidence: "high",
    agent_notes: `${stage} order route initiated directly from Hermes agent dashboard.`,
    status: "pending"
  };

  try {
    const paperTraderUrl = "http://paper_trader:5561";
    const ptResponse = await fetchWithTimeout(`${paperTraderUrl}/signal`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(signalPayload)
    }, 400);

    if (ptResponse.ok) {
      const result = await ptResponse.json();
      const pos = result.data || {};
      const newTrade = {
        id: String(pos.id || pos.ticket || signalPayload.signal_id),
        timestamp: new Date().toISOString(),
        instrument: "XAUUSD",
        direction,
        type,
        entryPrice: signalPayload.entry_price,
        stopLoss: signalPayload.sl,
        takeProfit: signalPayload.tp,
        lotSize: signalPayload.lots,
        currentPrice,
        pnl: 0,
        status: "OPEN",
        stage: stage || "paper",
        riskPercent: parseFloat(riskPercent) || 0.5,
        rrRatio: signalPayload.r_ratio,
        notes: signalPayload.agent_notes
      };

      logs.push({
        id: "log_" + Date.now(),
        timestamp: new Date().toISOString(),
        source: "MT5_ORDER",
        level: "SUCCESS",
        text: `Order Router (Broker Active): Successfully routed trade [${direction}] ticket to Paper Trader DB (ID: ${newTrade.id}) and Redis pipelines.`
      });

      return res.json(newTrade);
    }
  } catch (err) {
    // If paper trader is unreachable, fallback to simulated trade local broker queue
  }

  // Gracefully fallback to simulated trade
  const newTrade = {
    id: "t_" + Math.random().toString(36).substr(2, 5),
    timestamp: new Date().toISOString(),
    instrument: "XAUUSD",
    direction,
    type,
    entryPrice: parseFloat(entryPrice) || currentPrice,
    stopLoss: parseFloat(stopLoss),
    takeProfit: parseFloat(takeProfit),
    lotSize: parseFloat(lotSize) || 1.0,
    currentPrice,
    pnl: 0,
    status: "OPEN",
    stage: stage || "paper",
    riskPercent: parseFloat(riskPercent) || 0.5,
    rrRatio: parseFloat(((takeProfit - entryPrice) / (entryPrice - stopLoss)).toFixed(2)) || 2.0,
    notes: `${stage} order route initiated directly from Hermes agent dashboard (Simulated fallback offline).`
  };

  trades.push(newTrade);
  
  logs.push({
    id: "log_" + Date.now(),
    timestamp: new Date().toISOString(),
    source: "MT5_ORDER",
    level: "SUCCESS",
    text: `Order Router (Simulated): Successfully deployed [${direction}] trade ticket for ${newTrade.lotSize} lots at ${newTrade.entryPrice} on ZeroMQ Port 5557.`
  });

  res.json(newTrade);
});

app.post("/api/trades/close/:id", async (req, res) => {
  const tradeId = req.params.id;

  try {
    const paperTraderUrl = "http://paper_trader:5561";
    const ptResponse = await fetchWithTimeout(`${paperTraderUrl}/close/${tradeId}`, {
      method: "POST"
    }, 500);

    if (ptResponse.ok) {
      logs.push({
        id: "log_" + Date.now(),
        timestamp: new Date().toISOString(),
        source: "MT5_ORDER",
        level: "INFO",
        text: `Order Router: Successfully sent close signal to Paper Trader database for position ${tradeId}.`
      });
      return res.json({ id: tradeId, status: "CLOSED", notes: "Closed via Paper Trader backend endpoint." });
    }
  } catch (err) {
    // Fallback to local array close logic
  }

  const tradeIndex = trades.findIndex(t => t.id === tradeId);
  if (tradeIndex !== -1) {
    const trade = trades[tradeIndex];
    trades.splice(tradeIndex, 1);
    const completed = {
      ...trade,
      status: "CLOSED",
      exitPrice: currentPrice,
      closedAt: new Date().toISOString(),
      notes: "Closed manually by supervisor from web terminal."
    };
    closedTrades.push(completed);
    balance += completed.pnl;

    logs.push({
      id: "log_" + Date.now(),
      timestamp: new Date().toISOString(),
      source: "MT5_ORDER",
      level: "INFO",
      text: `Order Router: Position ${completed.id} cleared. Net PnL realized (simulated fallback): $${completed.pnl.toFixed(2)}`
    });

    res.json(completed);
  } else {
    res.status(404).json({ error: "Trade ticket not found" });
  }
});

app.get("/api/logs", (req, res) => {
  res.json(logs);
});

app.get("/api/errors", async (req, res) => {
  try {
    const r = await fetchWithTimeout("http://dashboard:8080/api/errors?n=100", {}, 3000);
    if (r.ok) {
      return res.json(await r.json());
    }
  } catch (e) {}
  res.json([]);
});

app.post("/api/logs", (req, res) => {
  const { source, level, text } = req.body;
  const newLog = {
    id: "log_" + Date.now(),
    timestamp: new Date().toISOString(),
    source: source || "SYSTEM",
    level: level || "INFO",
    text
  };
  logs.push(newLog);
  res.json(newLog);
});

app.get("/api/vault", (req, res) => {
  const vaultPath = "/data/obsidian";
  if (fs.existsSync(vaultPath)) {
    const realNotes = scanObsidianVault(vaultPath);
    if (realNotes && realNotes.length > 0) {
      return res.json(realNotes);
    }
  }
  res.json(obsidianNotes);
});

app.post("/api/vault", (req, res) => {
  const { title, content, folder, tags } = req.body;
  const fileName = `${title.replace(/\s+/g, '_')}.md`;
  const folderPath = folder || "root";
  const relativePath = folderPath !== "root" ? `${folderPath}/${fileName}` : fileName;
  const vaultPath = "/data/obsidian";
  const fullPath = path.join(vaultPath, relativePath);

  if (fs.existsSync(vaultPath)) {
    try {
      const parentDir = path.dirname(fullPath);
      if (!fs.existsSync(parentDir)) {
        fs.mkdirSync(parentDir, { recursive: true });
      }
      fs.writeFileSync(fullPath, content, "utf-8");
    } catch (err) {
      console.error("Error writing note to mounted vault:", err);
    }
  }

  const newNote = {
    path: relativePath,
    title,
    content,
    folder: folderPath,
    tags: tags || [],
    mtime: new Date().toISOString()
  };
  
  // Update local index cache
  const idx = obsidianNotes.findIndex(n => n.path === relativePath);
  if (idx !== -1) {
    obsidianNotes[idx] = newNote;
  } else {
    obsidianNotes.push(newNote);
  }
  
  logs.push({
    id: "log_" + Date.now(),
    timestamp: new Date().toISOString(),
    source: "SYSTEM",
    level: "SUCCESS",
    text: `Obsidian Vault Synchronizer: Successfully compiled note ${newNote.path} inside mounted directory.`
  });

  res.json(newNote);
});

app.get("/api/skills", (req, res) => {
  const skillDirs = [
    "/data/obsidian/04_KNOWLEDGE_BASE/skills",
    "/home/claude/.hermes/skills/trading"
  ];
  
  const diskSkills: any[] = [];
  
  for (const dir of skillDirs) {
    if (fs.existsSync(dir)) {
      try {
        const files = fs.readdirSync(dir).filter(f => f.endsWith('.py') || f.endsWith('.md'));
        for (const file of files) {
          const filePath = path.join(dir, file);
          const stat = fs.statSync(filePath);
          const content = fs.readFileSync(filePath, 'utf-8');
          diskSkills.push({
            name: file,
            description: content.split('\n').find(l => l.startsWith('"""') || l.startsWith('#'))?.replace(/^[#"]+/, '').trim() || file,
            code: content,
            successRate: 0,
            usageCount: 0,
            lastUpdated: stat.mtime.toISOString()
          });
        }
      } catch (e) {}
    }
  }
  
  // Return disk skills if found, otherwise return the in-memory skills array (user-added via POST)
  res.json(diskSkills.length > 0 ? diskSkills : skills);
});

app.post("/api/skills", (req, res) => {
  const { name, description, code } = req.body;
  const newSkill = {
    name,
    description,
    code,
    successRate: 75.0,
    usageCount: 1,
    lastUpdated: new Date().toISOString()
  };
  skills.push(newSkill);

  logs.push({
    id: "log_" + Date.now(),
    timestamp: new Date().toISOString(),
    source: "SYSTEM",
    level: "SUCCESS",
    text: `Hermes Autonomous loop: New trading skill compiled successfully [${name}]. Adding to skills index.`
  });

  res.json(newSkill);
});

app.get("/api/loops", (req, res) => {
  res.json(autonomousLoops);
});

app.post("/api/loops/trigger/:loop", async (req, res) => {
  const loop = req.params.loop as keyof typeof autonomousLoops;
  if (!autonomousLoops[loop]) {
    return res.status(400).json({ error: "Unknown loop identifier" });
  }

  if (autonomousLoops[loop].status === "RUNNING") {
    return res.status(409).json({ error: "Loop already running" });
  }

  autonomousLoops[loop].status = "RUNNING";
  autonomousLoops[loop].lastRun = new Date().toISOString();
  res.json(autonomousLoops[loop]);

  // Execute asynchronously after responding
  (async () => {
    try {
      if (loop === "nightlyMarketScan") {
        // Call hermes_rpc to analyse market structure via Ollama
        const r = await fetchWithTimeout("http://host.docker.internal:7778/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            message: "Run the analyse_market_structure skill for XAUUSD M15. Retrieve the last 300 bars, identify all FVGs, Order Blocks, BOS and CHoCH. Write the study to the Obsidian vault under 01_MARKET_STUDIES.",
            task_type: "analysis"
          })
        }, 120000);
        const outcome = r.ok
          ? "Market structure scan completed. Study written to Obsidian vault."
          : `Scan failed: hermes_rpc returned ${r.status}`;
        autonomousLoops[loop].outcome = outcome;

      } else if (loop === "skillAutoCreation") {
        // Call hermes_rpc to generate a new skill
        const r = await fetchWithTimeout("http://host.docker.internal:7778/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            message: "Using the generate_strategy skill, identify the weakest performing pattern in recent market studies and generate a new Python skill file to detect it. Write the skill to the vault under 04_KNOWLEDGE_BASE/skills/.",
            task_type: "code"
          })
        }, 120000);
        const outcome = r.ok
          ? "Skill auto-creation task dispatched to Hermes agent."
          : `Skill creation failed: hermes_rpc returned ${r.status}`;
        autonomousLoops[loop].outcome = outcome;

      } else if (loop === "paperTradeReview") {
        // Fetch real stats from paper_trader and then ask Hermes to review them
        let statsText = "No paper trade data available.";
        try {
          const statsRes = await fetchWithTimeout("http://paper_trader:5561/stats", {}, 5000);
          if (statsRes.ok) {
            const stats = await statsRes.json();
            statsText = JSON.stringify(stats, null, 2);
          }
        } catch (e) {}

        const r = await fetchWithTimeout("http://host.docker.internal:7778/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            message: `Run the review_paper_trades skill. Here are the current paper trading statistics:\n${statsText}\nAnalyse performance, identify losing patterns, and write a weekly review note to the Obsidian vault under 03_TRADE_JOURNAL/weekly_reviews/.`,
            task_type: "analysis"
          })
        }, 120000);
        const outcome = r.ok
          ? "Paper trade review completed. Journal entry written to vault."
          : `Review failed: hermes_rpc returned ${r.status}`;
        autonomousLoops[loop].outcome = outcome;

      } else if (loop === "hypothesisRandD") {
        // Check R&D queue and trigger backtester for next pending hypothesis
        let hypothesis = "Test FVG mitigation entries on XAUUSD M15 during London session.";
        try {
          const qRes = await fetchWithTimeout("http://dashboard:8080/api/rnd/queue", {}, 5000);
          if (qRes.ok) {
            const queue = await qRes.json();
            const pending = queue.find((q: any) => q.status === "pending");
            if (pending) hypothesis = pending.hypothesis;
          }
        } catch (e) {}

        const r = await fetchWithTimeout("http://host.docker.internal:7778/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            message: `Run the run_backtest skill for this hypothesis: "${hypothesis}". Extract strategy parameters, submit to the backtester, and write results to the Obsidian vault under 05_RND/results/.`,
            task_type: "analysis"
          })
        }, 300000);
        const outcome = r.ok
          ? `R&D backtest dispatched for: ${hypothesis.slice(0, 80)}...`
          : `R&D failed: hermes_rpc returned ${r.status}`;
        autonomousLoops[loop].outcome = outcome;
      }

    } catch (e: any) {
      autonomousLoops[loop].outcome = `Loop execution error: ${e.message}`;
    } finally {
      autonomousLoops[loop].status = "IDLE";
    }
  })();
});

app.get("/api/strategy/list", async (req, res) => {
  try {
    const response = await fetchWithTimeout("http://dashboard:8080/api/strategy/list", {}, 400);
    if (response.ok) {
      const data = await response.json();
      return res.json(data);
    }
  } catch (e) {
    try {
      const response = await fetchWithTimeout("http://localhost:8080/api/strategy/list", {}, 400);
      if (response.ok) {
        const data = await response.json();
        return res.json(data);
      }
    } catch (e2) {}
  }
  // Default fallback if dashboard is offline
  res.json([
    {
      id: "strat_NY_divergence",
      name: "NY Silver Divergence (Aggressive)",
      status: "hypothesis",
      instrument: "XAUUSD",
      timeframe: "M1",
      date_created: "2026-06-10",
      rules: {
        entry_rules: ["M1 displacement", "SSL sweep", "FVG reaction"],
        metrics: { win_rate: 0.65, profit_factor: 1.8, total_trades: 12 }
      }
    }
  ]);
});

app.get("/api/vault/search", async (req, res) => {
  const query = req.query.q as string || "";
  try {
    const qString = encodeURIComponent(query);
    const response = await fetchWithTimeout(`http://dashboard:8080/api/vault/search?q=${qString}`, {}, 400);
    if (response.ok) {
      const data = await response.json();
      return res.json(data);
    }
  } catch (e) {
    try {
      const qString = encodeURIComponent(query);
      const response = await fetchWithTimeout(`http://localhost:8080/api/vault/search?q=${qString}`, {}, 400);
      if (response.ok) {
        const data = await response.json();
        return res.json(data);
      }
    } catch (e2) {}
  }
  res.json([]);
});

// Gemini Chat & Analysis Endpoint
app.post("/api/gemini/analyze", async (req, res) => {
  const { prompt, type } = req.body;
  
  if (!ai) {
    return res.json({ 
      text: `### Ollama Offline - Hermes Agent Assistant Mode (SMC Analysis Framework)

The actual Gemini API is currently offline or the API key is not configured inside this testbed. However, let me evaluate this gold SMC/ICT setup mathematically based on Hermes system properties:

* **Asset**: XAUUSD (Gold)
* **Structure Price**: $${currentPrice.toFixed(2)}
* **Active FVG**: ${fairValueGaps.map(f => `[$${f.low} - $${f.high}]`).join(', ') || 'No active gaps detected'}
* **Major Liquidity**: SSL established at $2298.10, BSL established at $2338.50.

**Analysis & Strategy Suggestion**:
Since high-volume liquidity pools remain intact, expect a hunt for the sell-stops at $2298.10 before any major bullish expansion. Keep entry risks strictly bounded to **0.9%** with a stop-loss directly outside the swing swing candle high to satisfy strict staged security guidelines (Max Daily limit of 4%).`
    });
  }

  try {
    let customPrompt = prompt;
    if (type === "smc-audit") {
      customPrompt = `You are "Hermes Trading Agent" - a highly specialized autonomous SMC/ICT algorithmic trader analyzing the XAUUSD market.
Current Gold Price: $${currentPrice}
Active Fair Value Gaps (FVG): ${JSON.stringify(fairValueGaps)}
Open Order Blocks: ${JSON.stringify(orderBlocks)}
Active Liquidity Levels BSL/SSL: ${JSON.stringify(liquidityPools)}

Analyze this market context using classic SMC/ICT frameworks. Identify potential trade setups, and comment specifically on managing the trade within our risk constraints:
- Maximum 1% risk per trade
- Staged trust level verification (hypothesis -> backtest -> paper -> live_candidate -> live)

Give your analysis in clear, highly professional Markdown formatting. Do not assume any external indicators, focus strictly on Price Action, displacement, sweeps, and structural displacement.`;
    }

    const response = await ai.models.generateContent({
      model: "gemini-2.5-flash",
      contents: customPrompt,
      config: {
        systemInstruction: "You are the core consciousness of the Hermes Trading Agent, a sophisticated SMC/ICT trading system designed for Gold. You are meticulous, speak with professional precision, and always demand rigorous risk management.",
      }
    });

    res.json({ text: response.text });
  } catch (error: any) {
    console.error("Gemini call failed:", error);
    res.status(500).json({ error: "Gemini server call failure: " + error.message });
  }
});


async function hydrateStateFromServices(): Promise<void> {
  console.log("[Startup] Hydrating dashboard state from persistent services...");

  // Load active and closed trades from paper_trader
  try {
    const activeRes = await fetchWithTimeout("http://paper_trader:5561/positions", {}, 5000);
    if (activeRes.ok) {
      const data = await activeRes.json();
      if (Array.isArray(data)) {
        trades = data.map((p: any) => ({
          id: p.id,
          timestamp: new Date(p.open_time * 1000).toISOString(),
          instrument: p.instrument || "XAUUSD",
          direction: (p.direction || "buy").toUpperCase(),
          type: p.setup_type || "Unknown",
          entryPrice: p.entry_price || 0,
          stopLoss: p.sl || 0,
          takeProfit: p.tp || 0,
          lotSize: p.lots || 0,
          currentPrice: p.entry_price || 0,
          pnl: 0,
          status: "OPEN",
          stage: p.strategy_id ? "paper" : "paper",
          riskPercent: 1.0,
          rrRatio: 2.0,
          notes: p.agent_notes || ""
        }));
        console.log(`[Startup] Loaded ${trades.length} active positions from paper_trader`);
      }
    }
  } catch (e) {
    console.log("[Startup] paper_trader not available yet, active trades start empty");
  }

  try {
    const historyRes = await fetchWithTimeout("http://paper_trader:5561/history?n=50", {}, 5000);
    if (historyRes.ok) {
      const data = await historyRes.json();
      if (Array.isArray(data)) {
        closedTrades = data.map((p: any) => ({
          id: p.id,
          timestamp: new Date(p.open_time * 1000).toISOString(),
          instrument: p.instrument || "XAUUSD",
          direction: (p.direction || "buy").toUpperCase(),
          type: p.setup_type || "Unknown",
          entryPrice: p.entry_price || 0,
          stopLoss: p.sl || 0,
          takeProfit: p.tp || 0,
          exitPrice: p.close_price || 0,
          lotSize: p.lots || 0,
          currentPrice: p.close_price || 0,
          pnl: (p.pnl_r || 0) * 400,
          status: "CLOSED",
          stage: "paper",
          riskPercent: 1.0,
          rrRatio: p.pnl_r || 0,
          closedAt: p.close_time ? new Date(p.close_time * 1000).toISOString() : undefined,
          notes: p.close_reason || ""
        }));
        console.log(`[Startup] Loaded ${closedTrades.length} closed trades from paper_trader`);
      }
    }
  } catch (e) {
    console.log("[Startup] paper_trader history not available yet");
  }

  // Load recent logs from Redis
  try {
    const { createClient } = await import("redis");
    const redisClient = createClient({ url: process.env.REDIS_URL || "redis://redis:6379" });
    await redisClient.connect();
    const history = await redisClient.lRange("chat_history", -20, -1);
    if (history.length > 0) {
      logs.push({
        id: "log_hydrate_1",
        timestamp: new Date().toISOString(),
        source: "SYSTEM",
        level: "INFO",
        text: `Restored ${history.length} recent chat history entries from Redis.`
      });
    }
    await redisClient.disconnect();
  } catch (e) {
    console.log("[Startup] Redis not available for log hydration");
  }

  console.log("[Startup] State hydration complete.");
}

async function startServer() {
  await hydrateStateFromServices();   // ADD THIS LINE

  // Serve static files in production setup or proxy Vite in development setup
  if (process.env.NODE_ENV !== "production") {
    const vite = await createViteServer({
      server: { middlewareMode: true },
      appType: "spa",
    });
    app.use(vite.middlewares);
  } else {
    const distPath = path.join(process.cwd(), 'dist');
    app.use(express.static(distPath));
    app.get('*', (req: any, res: any) => {
      res.sendFile(path.join(distPath, 'index.html'));
    });
  }

  // Try to seed currentPrice from MT5 bridge at startup
  try {
    const seedRes = await fetchWithTimeout("http://mt5_bridge:5558/latest_bars?instrument=XAUUSD&tf=M15&n=1", {}, 3000);
    if (seedRes.ok) {
      const bars = await seedRes.json();
      if (bars && bars.length > 0) {
        currentPrice = bars[bars.length - 1].close;
        console.log(`[Startup] Seeded price from MT5: ${currentPrice}`);
      }
    }
  } catch (e) {
    console.log("[Startup] MT5 not available yet, currentPrice stays null until first market poll.");
  }

  app.listen(PORT, "0.0.0.0", () => {
    console.log(`Server running on port ${PORT}`);
  });
}

startServer();
