//+------------------------------------------------------------------+
//|                                                     HermesEA.mq5 |
//|                             Hermes Autonomous AI Trading Agent   |
//|                             https://github.com/google/ai-studio  |
//|                                                                  |
//| Note: This file relies on the mql5-zmq wrapper for executing    |
//| high-performance socket operations directly with standard MT5,   |
//| linking to local Docker services via host.docker.internal and    |
//| loopback channels.                                               |
//+------------------------------------------------------------------+
#property copyright "Hermes Team"
#property link      "https://github.com/google/ai-studio"
#property version   "1.00"
#property strict

// Include MT5 trade classes
#include <Trade\Trade.mqh>
#include <Trade\PositionInfo.mqh>
#include <Trade\SymbolInfo.mqh>

// Include standard ZMQ wrapper for MQL5
// Ensure you have added the 'mql5-zmq' package containing Zmq.mqh in your Include/Zmq directory
#include <Zmq/Zmq.mqh>

//+------------------------------------------------------------------+
//| Input Parameters                                                 |
//+------------------------------------------------------------------+
input string   InpDataHost       = "127.0.0.1"; // Data Socket Host
input int      InpDataPort       = 5555;        // Data Socket Port (PUSH)
input int      InpDrawPort       = 5556;        // Draw Socket Port (PULL - Bind)
input int      InpOrderPort      = 5557;        // Order Socket Port (PULL - Bind)
input ulong    InpMagicNumber    = 20250001;    // EA Magic Number
input int      InpMaxSlippage    = 10;          // Max Slippage (Pips)

//+------------------------------------------------------------------+
//| Global Variables                                                 |
//+------------------------------------------------------------------+
CTrade         m_trade;          // MT5 standard trade object setter
CPositionInfo  m_position;       // Position info accessor
CSymbolInfo    m_symbol;         // Symbol detail helper

Context        g_zmq_context;    // Shared ZeroMQ Context
Socket*        g_socket_data;    // PUSH socket for data transmissions
Socket*        g_socket_draw;    // PULL socket for receiving draw commands
Socket*        g_socket_order;   // PULL socket for receiving order commands

datetime       g_last_bar_time;  // Track candle formation trends
string         g_instrument;     // Cache current asset symbol (XAUUSD)
ENUM_TIMEFRAMES g_timeframe;     // Active timeframe

//+------------------------------------------------------------------+
//| Session Management Utility                                       |
//+------------------------------------------------------------------+
string GetSession(datetime time)
{
   MqlDateTime dt;
   TimeToStruct(time, dt);
   
   int hour = dt.hour;
   
   // Typical UTC session boundaries:
   // Asian session: 22:00 - 07:00 UTC (Tokyo open)
   // London session: 07:00 - 15:00 UTC (London open)
   // NY session: 12:00 - 21:00 UTC (NY open)
   // Overlap window: 12:00 - 15:00 UTC (US/Europe overlap)
   
   if(hour >= 22 || hour < 7)
      return "asian";
   else if(hour >= 7 && hour < 12)
      return "london";
   else if(hour >= 12 && hour < 15)
      return "overlap";
   else if(hour >= 15 && hour < 21)
      return "newyork";
   else
      return "off";
}

//+------------------------------------------------------------------+
//| Basic JSON Serialization and Parsing Helpers                     |
//+------------------------------------------------------------------+
// Helper to extract a string parameter value from raw flat JSON
string ExtractJsonString(string json, string key)
{
   string key_pattern = "\"" + key + "\":";
   int pos = StringFind(json, key_pattern);
   if(pos == -1) return "";
   
   int start = pos + StringLen(key_pattern);
   
   // Skip any whitespaces or colon delimiters
   while(start < StringLen(json))
   {
      ushort ch = StringGetCharacter(json, start);
      if(ch == ' ' || ch == ':' || ch == '"') start++;
      else break;
   }
   
   int end = start;
   while(end < StringLen(json))
   {
      ushort ch = StringGetCharacter(json, end);
      if(ch == '"' || ch == ',' || ch == '}' || ch == '\r' || ch == '\n') break;
      end++;
   }
   
   return StringSubstr(json, start, end - start);
}

// Helper to extract a double parameter value from raw flat JSON
double ExtractJsonDouble(string json, string key)
{
   string val_str = ExtractJsonString(json, key);
   if(val_str == "") return 0.0;
   return StringToDouble(val_str);
}

// Helper to extract an integer param from JSON
int ExtractJsonInt(string json, string key)
{
   string val_str = ExtractJsonString(json, key);
   if(val_str == "") return 0;
   return (int)StringToInteger(val_str);
}

// Ensure proper escaping and serialization for outgoing string contents
string EscapeString(string txt)
{
   StringReplace(txt, "\\", "\\\\");
   StringReplace(txt, "\"", "\\\"");
   StringReplace(txt, "\n", "\\n");
   StringReplace(txt, "\r", "\\r");
   StringReplace(txt, "\t", "\\t");
   return txt;
}

//+------------------------------------------------------------------+
//| Expert initialization function                                   |
//+------------------------------------------------------------------+
int OnInit()
{
   g_instrument = Symbol();
   g_timeframe  = Period();
   g_last_bar_time = 0;
   
   m_trade.SetExpertMagicNumber(InpMagicNumber);
   
   // Verify symbol setup
   if(!m_symbol.Name(g_instrument))
   {
      Print("[!] FAILED to initialize symbol: ", g_instrument);
      return INIT_FAILED;
   }
   
   Print("[*] Booting HermesEA on symbol: ", g_instrument, " (", EnumToString(g_timeframe), ")");
   
   // Initialize ZeroMQ socket allocations
   g_socket_data  = new Socket(g_zmq_context, ZMQ_PUSH);
   g_socket_draw  = new Socket(g_zmq_context, ZMQ_PULL);
   g_socket_order = new Socket(g_zmq_context, ZMQ_PULL);
   
   // Prevent infinite resource blocks on closing
   g_socket_data.setLinger(1000);
   g_socket_draw.setLinger(1000);
   g_socket_order.setLinger(1000);
   
   // Establish connections
   string data_addr = "tcp://" + InpDataHost + ":" + IntegerToString(InpDataPort);
   string draw_addr = "tcp://0.0.0.0:" + IntegerToString(InpDrawPort);
   string order_addr = "tcp://0.0.0.0:" + IntegerToString(InpOrderPort);
   
   Print("[*] Data Socket: Connecting to ", data_addr);
   if(!g_socket_data.connect(data_addr))
   {
      Print("[!] FAILED connecting Data PUSH socket. Error: ", GetLastError());
      return INIT_FAILED;
   }
   
   Print("[*] Draw Socket: Binding to ", draw_addr);
   if(!g_socket_draw.bind(draw_addr))
   {
      Print("[!] FAILED binding Draw PULL socket. Error: ", GetLastError());
      return INIT_FAILED;
   }
   
   Print("[*] Order Socket: Binding to ", order_addr);
   if(!g_socket_order.bind(order_addr))
   {
      Print("[!] FAILED binding Order PULL socket. Error: ", GetLastError());
      return INIT_FAILED;
   }
   
   Print("[✓] Hermes Expert Advisor Socket layers configured successfully.");
   return(INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
//| Expert deinitialization function                                 |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   Print("[*] Demobilizing HermesEA interface sockets...");
   
   if(g_socket_data != NULL)
   {
      g_socket_data.close();
      delete g_socket_data;
   }
   if(g_socket_draw != NULL)
   {
      g_socket_draw.close();
      delete g_socket_draw;
   }
   if(g_socket_order != NULL)
   {
      g_socket_order.close();
      delete g_socket_order;
   }
   
   Print("[✓] Decoded bindings offline.");
}

//+------------------------------------------------------------------+
//| Chart Drawing Engine                                             |
//+------------------------------------------------------------------+
void DrawObject(string json_cmd)
{
   string cmd_type = ExtractJsonString(json_cmd, "type");
   string draw_cmd = ExtractJsonString(json_cmd, "cmd"); // "draw", "delete", "clear"
   string obj_id   = ExtractJsonString(json_cmd, "id");
   
   if(draw_cmd == "clear")
   {
      Print("[*] Action CLEAR received. Deleting chart objects...");
      ObjectsDeleteAll(0, "hermes_", -1, -1);
      ChartRedraw(0);
      return;
   }
   
   if(draw_cmd == "delete")
   {
      string target_name = "hermes_" + obj_id;
      Print("[*] Action DELETE: removing target object: ", target_name);
      ObjectDelete(0, target_name);
      ChartRedraw(0);
      return;
   }
   
   // Handle real dynamic Drawing actions
   if(draw_cmd == "draw")
   {
      string obj_name = "hermes_" + obj_id;
      double price1 = ExtractJsonDouble(json_cmd, "price1");
      double price2 = ExtractJsonDouble(json_cmd, "price2");
      datetime time1 = (datetime)ExtractJsonInt(json_cmd, "time1");
      datetime time2 = (datetime)ExtractJsonInt(json_cmd, "time2");
      
      // Fallback timeline limits
      if(time1 == 0) time1 = TimeCurrent();
      if(time2 == 0) time2 = TimeCurrent();
      
      string color_name = ExtractJsonString(json_cmd, "color");
      string label_text = ExtractJsonString(json_cmd, "label");
      string style_name = ExtractJsonString(json_cmd, "style");
      int width = ExtractJsonInt(json_cmd, "width");
      if(width <= 0) width = 1;
      
      color item_color = clrSkyBlue;
      if(color_name == "green") item_color = clrMediumSeaGreen;
      if(color_name == "red")   item_color = clrCrimson;
      if(color_name == "blue")  item_color = clrBlue;
      if(color_name == "orange") item_color = clrDarkOrange;
      if(color_name == "cyan")   item_color = clrCyan;
      if(color_name == "magenta") item_color = clrMagenta;
      if(color_name == "yellow")  item_color = clrYellow;
      
      ENUM_LINE_STYLE item_style = STYLE_SOLID;
      if(style_name == "dashed") item_style = STYLE_DASH;
      if(style_name == "dotted") item_style = STYLE_DOT;
      
      ObjectDelete(0, obj_name); // Clean potential duplicates first
      
      if(cmd_type == "rect")
      {
         Print("[*] Drawing RECT: ", obj_name, " | Prices: ", price1, " to ", price2);
         if(ObjectCreate(0, obj_name, OBJ_RECTANGLE, 0, time1, price1, time2, price2))
         {
            ObjectSetInteger(0, obj_name, OBJPROP_COLOR, item_color);
            ObjectSetInteger(0, obj_name, OBJPROP_STYLE, item_style);
            ObjectSetInteger(0, obj_name, OBJPROP_WIDTH, width);
            ObjectSetInteger(0, obj_name, OBJPROP_FILL, false);
            ObjectSetString(0, obj_name, OBJPROP_TOOLTIP, label_text);
         }
      }
      else if(cmd_type == "hline")
      {
         Print("[*] Drawing HLINE: ", obj_name, " @ Price: ", price1);
         if(ObjectCreate(0, obj_name, OBJ_HLINE, 0, time1, price1))
         {
            ObjectSetInteger(0, obj_name, OBJPROP_COLOR, item_color);
            ObjectSetInteger(0, obj_name, OBJPROP_STYLE, item_style);
            ObjectSetInteger(0, obj_name, OBJPROP_WIDTH, width);
            ObjectSetString(0, obj_name, OBJPROP_TOOLTIP, label_text);
         }
      }
      else if(cmd_type == "trendline")
      {
         Print("[*] Drawing TRENDLINE: ", obj_name);
         if(ObjectCreate(0, obj_name, OBJ_TREND, 0, time1, price1, time2, price2))
         {
            ObjectSetInteger(0, obj_name, OBJPROP_COLOR, item_color);
            ObjectSetInteger(0, obj_name, OBJPROP_STYLE, item_style);
            ObjectSetInteger(0, obj_name, OBJPROP_WIDTH, width);
            ObjectSetInteger(0, obj_name, OBJPROP_RAY_RIGHT, false);
            ObjectSetString(0, obj_name, OBJPROP_TOOLTIP, label_text);
         }
      }
      else if(cmd_type == "arrow")
      {
         Print("[*] Drawing ARROW: ", obj_name, " @ price: ", price1);
         ENUM_OBJECT arrow_type = OBJ_ARROW_UP;
         if(color_name == "red") arrow_type = OBJ_ARROW_DOWN;
         
         if(ObjectCreate(0, obj_name, arrow_type, 0, time1, price1))
         {
            ObjectSetInteger(0, obj_name, OBJPROP_COLOR, item_color);
            ObjectSetInteger(0, obj_name, OBJPROP_WIDTH, width + 1);
            ObjectSetString(0, obj_name, OBJPROP_TEXT, label_text);
         }
      }
      else if(cmd_type == "label")
      {
         Print("[*] Drawing TEXT label: ", obj_name);
         if(ObjectCreate(0, obj_name, OBJ_TEXT, 0, time1, price1))
         {
            ObjectSetString(0, obj_name, OBJPROP_TEXT, label_text);
            ObjectSetInteger(0, obj_name, OBJPROP_COLOR, item_color);
            ObjectSetInteger(0, obj_name, OBJPROP_FONTSIZE, 10);
         }
      }
      
      ChartRedraw(0);
   }
}

//+------------------------------------------------------------------+
//| Executing Trading Orders Router                                  |
//+------------------------------------------------------------------+
void ExecuteOrder(string json_cmd)
{
   string action    = ExtractJsonString(json_cmd, "action"); // "BUY", "SELL", "CLOSE", "MODIFY"
   string symbol    = ExtractJsonString(json_cmd, "instrument");
   double lots      = ExtractJsonDouble(json_cmd, "lots");
   double sl        = ExtractJsonDouble(json_cmd, "sl");
   double tp        = ExtractJsonDouble(json_cmd, "tp");
   string comment   = ExtractJsonString(json_cmd, "comment");
   int magic        = ExtractJsonInt(json_cmd, "magic");
   
   if(symbol == "") symbol = g_instrument;
   if(magic <= 0) magic = (int)InpMagicNumber;
   
   bool res = false;
   ulong ticket = 0;
   
   Print("[*] Executor Pipeline: Intercepted order command: ", action, " on ", symbol, " lots: ", lots);
   
   if(action == "BUY")
   {
      double ask = SymbolInfoDouble(symbol, SYMBOL_ASK);
      res = m_trade.Buy(lots, symbol, ask, sl, tp, comment);
      if(res) {
         ticket = m_trade.ResultDeal();
         Print("[✓] BUY ORDER executed successfully! Ticket: ", ticket);
      } else {
         Print("[!] BUY ORDER FAILED. Code: ", m_trade.ResultRetcode(), " Desc: ", m_trade.ResultComment());
      }
   }
   else if(action == "SELL")
   {
      double bid = SymbolInfoDouble(symbol, SYMBOL_BID);
      res = m_trade.Sell(lots, symbol, bid, sl, tp, comment);
      if(res) {
         ticket = m_trade.ResultDeal();
         Print("[✓] SELL ORDER executed successfully! Ticket: ", ticket);
      } else {
         Print("[!] SELL ORDER FAILED. Code: ", m_trade.ResultRetcode(), " Desc: ", m_trade.ResultComment());
      }
   }
   else if(action == "CLOSE")
   {
      // Iterate open positions and selectively liquidate
      int closed_count = 0;
      for(int i = PositionsTotal() - 1; i >= 0; i--)
      {
         if(m_position.SelectByIndex(i))
         {
            if(m_position.Symbol() == symbol && (m_position.Magic() == magic || m_position.Comment() == comment))
            {
               Print("[*] Liquidation target found: ticket ", m_position.Ticket());
               if(m_trade.PositionClose(m_position.Ticket(), InpMaxSlippage))
               {
                  closed_count++;
               }
            }
         }
      }
      res = (closed_count > 0);
      Print("[✓] Completed closing operation. Total positions cleared: ", closed_count);
   }
   else if(action == "MODIFY")
   {
      int modified_count = 0;
      for(int i = PositionsTotal() - 1; i >= 0; i--)
      {
         if(m_position.SelectByIndex(i))
         {
            if(m_position.Symbol() == symbol && (m_position.Magic() == magic || m_position.Comment() == comment))
            {
               Print("[*] Modification target found: ticket ", m_position.Ticket());
               if(m_trade.PositionModify(m_position.Ticket(), sl, tp))
               {
                  modified_count++;
               }
            }
         }
      }
      res = (modified_count > 0);
      Print("[✓] Completed modifications. Total positions updated: ", modified_count);
   }
   
   // Dispatch confirmation log back to docker container over pipeline channel
   string result_payload = "{"
      + "\"type\":\"trade_event\","
      + "\"action\":\"" + action + "\","
      + "\"symbol\":\"" + symbol + "\","
      + "\"result\":" + (res ? "true" : "false") + ","
      + "\"ticket\":" + IntegerToString(ticket) + ","
      + "\"comment\":\"" + comment + "\""
      + "}";
      
   g_socket_data.send(result_payload);
}

//+------------------------------------------------------------------+
//| OnTick Core Handler Loop                                         |
//+------------------------------------------------------------------+
void OnTick()
{
   // Check bar transitions
   datetime current_bar_time = (datetime)SeriesInfoInteger(g_instrument, g_timeframe, SERIES_LASTBAR_DATE);
   
   if(current_bar_time != g_last_bar_time)
   {
      double open_val = iOpen(g_instrument, g_timeframe, 0);
      double high_val = iHigh(g_instrument, g_timeframe, 0);
      double low_val  = iLow(g_instrument, g_timeframe, 0);
      double close_val = iClose(g_instrument, g_timeframe, 0);
      long vol_val    = iVolume(g_instrument, g_timeframe, 0);
      long spread_val = SymbolInfoInteger(g_instrument, SYMBOL_SPREAD);
      
      // Build JSON representation
      string data_body = "{"
         + "\"type\":\"bar_event\","
         + "\"instrument\":\"" + g_instrument + "\","
         + "\"timeframe\":\"" + EnumToString(g_timeframe) + "\","
         + "\"timestamp\":" + IntegerToString((long)current_bar_time) + ","
         + "\"open\":" + DoubleToString(open_val, Digits()) + ","
         + "\"high\":" + DoubleToString(high_val, Digits()) + ","
         + "\"low\":" + DoubleToString(low_val, Digits()) + ","
         + "\"close\":" + DoubleToString(close_val, Digits()) + ","
         + "\"volume\":" + IntegerToString(vol_val) + ","
         + "\"spread\":" + IntegerToString(spread_val) + ","
         + "\"session\":\"" + GetSession(current_bar_time) + "\""
         + "}";
         
      logger_publish:
      Print("[*] New bar detected. Broad-casting structured event payload...");
      if(!g_socket_data.send(data_body))
      {
         Print("[!] Connection warning: Data socket send dropped.");
      }
      
      g_last_bar_time = current_bar_time;
   }
   
   // Consume Draw commands
   string draw_msg = "";
   while(g_socket_draw.recv(draw_msg, true)) // true for non-blocking recv operation
   {
      if(draw_msg != "")
      {
         Print("[*] Draw command received: ", draw_msg);
         DrawObject(draw_msg);
      }
      draw_msg = "";
   }
   
   // Consume Order commands
   string order_msg = "";
   while(g_socket_order.recv(order_msg, true))
   {
      if(order_msg != "")
      {
         Print("[*] Order command received: ", order_msg);
         ExecuteOrder(order_msg);
      }
      order_msg = "";
   }
}

//+------------------------------------------------------------------+
//| OnTester / Backtest Data Upload pipeline                         |
//+------------------------------------------------------------------+
double OnTester()
{
   Print("[*] High-speed simulation backtest data export started...");
   MqlRates rates[];
   ArraySetAsSeries(rates, false);
   
   int copy_cnt = CopyRates(g_instrument, g_timeframe, 0, 50000, rates);
   if(copy_cnt <= 0)
   {
      Print("[!] FAILED capturing historical datasets to push. CopyRates error: ", GetLastError());
      return 0.0;
   }
   
   int chunk_size = 500;
   int total_chunks = (copy_cnt + chunk_size - 1) / chunk_size;
   
   Print("[*] Exporting ", copy_cnt, " historical candles split across ", total_chunks, " chunks...");
   
   for(int chunk_idx = 0; chunk_idx < total_chunks; chunk_idx++)
   {
      int start_idx = chunk_idx * chunk_size;
      int take_cnt  = MathMin(chunk_size, copy_cnt - start_idx);
      
      string chunk_body = "{\"type\":\"backtest_chunk\",\"chunk_id\":" + IntegerToString(chunk_idx) + ",\"total_chunks\":" + IntegerToString(total_chunks) + ",\"rates\":[";
      
      for(int i = 0; i < take_cnt; i++)
      {
         int rate_index = start_idx + i;
         
         chunk_body += "{"
            + "\"t\":" + IntegerToString((long)rates[rate_index].time) + ","
            + "\"o\":" + DoubleToString(rates[rate_index].open, Digits()) + ","
            + "\"h\":" + DoubleToString(rates[rate_index].high, Digits()) + ","
            + "\"l\":" + DoubleToString(rates[rate_index].low, Digits()) + ","
            + "\"c\":" + DoubleToString(rates[rate_index].close, Digits()) + ","
            + "\"v\":" + IntegerToString(rates[rate_index].tick_volume) + ","
            + "\"s\":" + IntegerToString(rates[rate_index].spread)
            + "}";
            
         if(i < take_cnt - 1)
            chunk_body += ",";
      }
      chunk_body += "]}";
      
      if(!g_socket_data.send(chunk_body))
      {
         Print("[!] Simulation transfer dropped during chunk: ", chunk_idx);
         return 0.0;
      }
      
      // Small pause to prevent socket saturations
      Sleep(20);
   }
   
   // Broadcast completed simulation report marker
   string end_payload = "{\"type\":\"backtest_end\",\"instrument\":\"" + g_instrument + "\",\"timeframe\":\"" + EnumToString(g_timeframe) + "\"}";
   g_socket_data.send(end_payload);
   
   Print("[✓] Finished transferring backtest dataset successfully.");
   return 100.0;
}
