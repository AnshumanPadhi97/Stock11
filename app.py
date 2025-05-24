import gradio as gr
import random
import threading
import time
from datetime import datetime

# --- Global State ---
opening_prices = {
    "RELIANCE": 2800,
    "TCS": 3800,
    "INFY": 1450,
    "HDFCBANK": 1650,
    "ICICIBANK": 1100,
    "ADANIENT": 3000,
    "HINDUNILVR": 2550,
    "MARUTI": 11600,
    "TITAN": 3550,
}

stock_options = list(opening_prices.keys())
live_prices = opening_prices.copy()
previous_prices = opening_prices.copy()  # for arrow direction

user_picks = {}    # {user_id: [stock1, stock2, stock3]}
user_captains = {}  # {user_id: {"captain": stock, "vice_captain": stock}}
user_scores = {}   # {user_id: score}
score_change_logs = {}  # {user_id: [str, str, str]}
score_history = {}  # {user_id: [(timestamp, score), ...]}

lock = threading.Lock()  # to sync updates


# --- Price Simulator Thread (only updates prices, not scores) ---
def price_simulator():
    while True:
        with lock:
            for stock in live_prices:
                change_pct = random.uniform(-0.02, 0.02)
                live_prices[stock] = round(live_prices[stock] * (1 + change_pct), 2)
        time.sleep(3)


# --- Update Scores (called only on refresh) ---
def update_scores():
    global score_change_logs, score_history
    timestamp = datetime.now().strftime("%H:%M:%S")
    
    for user, picks in user_picks.items():
        total = 0
        logs = []
        captain = user_captains.get(user, {}).get("captain")
        vice_captain = user_captains.get(user, {}).get("vice_captain")
        
        for stock in picks:
            open_price = opening_prices[stock]
            current_price = live_prices[stock]
            pct = ((current_price - open_price) / open_price) * 100
            base_points = round(pct * 10, 2)
            
            # Apply multipliers
            multiplier = 1
            badge = ""
            if stock == captain:
                multiplier = 2
                badge = " 👑(C)"
            elif stock == vice_captain:
                multiplier = 1.5
                badge = " 🅲(VC)"
            
            final_points = round(base_points * multiplier, 2)
            
            if multiplier > 1:
                logs.append(f"{stock}: {pct:+.2f}% → {base_points:+.1f} × {multiplier} = {final_points:+.1f} pts{badge}")
            else:
                logs.append(f"{stock}: {pct:+.2f}% → {final_points:+.1f} pts")
            
            total += final_points
        
        old_score = user_scores.get(user, 0)
        new_score = round(total, 2)
        user_scores[user] = new_score
        score_change_logs[user] = logs
        
        # Add to score history with change indicator
        if user not in score_history:
            score_history[user] = []
        
        change = new_score - old_score if score_history[user] else 0
        score_history[user].append((timestamp, new_score, change))
        
        # Keep only last 10 entries for readability
        if len(score_history[user]) > 10:
            score_history[user] = score_history[user][-10:]


# --- Set User Picks ---
def set_user_picks(*inputs):
    # inputs = [user1_stocks, user1_captain, user1_vice, user2_stocks, user2_captain, user2_vice, user3_stocks, user3_captain, user3_vice]
    with lock:
        user_picks.clear()
        user_captains.clear()
        user_scores.clear()
        score_change_logs.clear()
        score_history.clear()
        
        for i in range(0, len(inputs), 3):  # Process in groups of 3 (stocks, captain, vice_captain)
            user_num = (i // 3) + 1
            user_id = f"User{user_num}"
            
            stocks = list(inputs[i]) if inputs[i] else []
            captain = inputs[i+1] if i+1 < len(inputs) else None
            vice_captain = inputs[i+2] if i+2 < len(inputs) else None
            
            # Validation
            errors = []
            if captain and captain not in stocks:
                errors.append(f"{user_id}: Captain must be from selected stocks")
            if vice_captain and vice_captain not in stocks:
                errors.append(f"{user_id}: Vice Captain must be from selected stocks")
            if captain and vice_captain and captain == vice_captain:
                errors.append(f"{user_id}: Captain and Vice Captain must be different")
            
            if errors:
                return ("❌ Error: " + "; ".join(errors), gr.update(visible=True), gr.update(visible=False))
            
            user_picks[user_id] = stocks
            user_captains[user_id] = {"captain": captain, "vice_captain": vice_captain}
            user_scores[user_id] = 0
            score_change_logs[user_id] = []
            score_history[user_id] = []
    
    return (
        "✅ Picks and captains set! Click refresh to see logs and scores...",
        gr.update(visible=False),  # hide picks container
        gr.update(visible=True),   # show logs container
    )


# --- Get Enhanced Logs with arrows, colors, and user scores ---
def get_enhanced_logs():
    with lock:
        global previous_prices
        
        # Update scores when refreshing logs
        update_scores()
        
        log_lines = []
        now = datetime.now().strftime("%H:%M:%S")
        
        # Stock price changes
        log_lines.append("=" * 80)
        log_lines.append(f"📊 STOCK UPDATES - {now}")
        log_lines.append("=" * 80)
        
        for stock in live_prices:
            prev = previous_prices[stock]
            curr = live_prices[stock]
            direction_up = curr > prev
            arrow = "▲" if direction_up else "▼"
            color_emoji = "🟢" if direction_up else "🔴"
            pct_change = ((curr - opening_prices[stock]) / opening_prices[stock]) * 100
            points = round(pct_change * 10, 2)
            
            line = f"{stock:12} | ₹{prev:8.2f} → ₹{curr:8.2f} {arrow} {color_emoji} | Day: {pct_change:+6.2f}% → {points:+6.1f} pts"
            log_lines.append(line)
            previous_prices[stock] = curr  # update for next refresh

        # User scores breakdown
        if user_picks:
            log_lines.append("")
            log_lines.append("=" * 80)
            log_lines.append("🏆 USER SCORES BREAKDOWN")
            log_lines.append("=" * 80)
            
            # Sort users by score
            sorted_users = sorted(user_scores.items(), key=lambda x: x[1], reverse=True)
            
            for rank, (user, total_score) in enumerate(sorted_users, 1):
                medal = "🥇" if rank == 1 else "🥈" if rank == 2 else "🥉" if rank == 3 else "  "
                
                # Show captain/vice-captain info
                captain_info = ""
                if user in user_captains:
                    captain = user_captains[user].get("captain")
                    vice_captain = user_captains[user].get("vice_captain")
                    if captain or vice_captain:
                        captain_info = f" | 👑{captain or 'None'} 🅲{vice_captain or 'None'}"
                
                log_lines.append(f"{medal} {user:8} | Total: {total_score:+8.1f} pts{captain_info}")
                
                # Show individual stock performance for this user
                if user in score_change_logs:
                    for stock_log in score_change_logs[user]:
                        log_lines.append(f"     └─ {stock_log}")
                
                # Show score history trail
                if user in score_history and len(score_history[user]) > 0:
                    log_lines.append(f"     📈 Score Trail:")
                    for i, (timestamp, score, change) in enumerate(score_history[user]):
                        if i == 0:
                            log_lines.append(f"        {timestamp}: {score:+7.1f} pts (initial)")
                        else:
                            change_indicator = "📈" if change > 0 else "📉" if change < 0 else "➡️"
                            log_lines.append(f"        {timestamp}: {score:+7.1f} pts ({change:+5.1f}) {change_indicator}")
                
                log_lines.append("")

        return "\n".join(log_lines)


# --- Start the price simulation thread ---
threading.Thread(target=price_simulator, daemon=True).start()


# --- Gradio UI ---
with gr.Blocks(css="""
    .logs-container textarea {
        font-family: 'Courier New', monospace !important;
        font-size: 14px !important;
        line-height: 1.4 !important;
    }
    .captain-section {
        background: linear-gradient(45deg, #ffd700, #ffed4e);
        padding: 10px;
        border-radius: 8px;
        margin: 5px 0;
    }
""") as demo:
    gr.Markdown("# 📈 Fantasy Stock Game - Captain Edition")
    gr.Markdown("### 👑 Captain gets 2x points | 🅲 Vice Captain gets 1.5x points")

    with gr.Column(visible=True) as picks_container:
        gr.Markdown("### Pick 3 Stocks + Captain & Vice Captain per User")
        
        all_inputs = []
        
        for i in range(3):
            with gr.Row():
                gr.Markdown(f"## User {i+1}")
            
            with gr.Row():
                stocks = gr.CheckboxGroup(
                    stock_options, 
                    label=f"User {i+1} - Select 3 Stocks", 
                    value=[]
                )
                all_inputs.append(stocks)
            
            with gr.Row(elem_classes=["captain-section"]):
                with gr.Column(scale=1):
                    captain = gr.Dropdown(
                        stock_options,
                        label=f"👑 Captain (2x points)",
                        value=None
                    )
                    all_inputs.append(captain)
                
                with gr.Column(scale=1):
                    vice_captain = gr.Dropdown(
                        stock_options,
                        label=f"🅲 Vice Captain (1.5x points)",
                        value=None
                    )
                    all_inputs.append(vice_captain)

        set_btn = gr.Button("✅ Set Picks & Captains - Start Game!", variant="primary", size="lg")
        status = gr.Textbox(label="Status", interactive=False)

    with gr.Column(visible=False) as logs_container:
        gr.Markdown("### 📊 Live Game Logs")
        gr.Markdown("*Click refresh to update scores and see latest stock movements*")
        
        with gr.Row():
            refresh_btn = gr.Button("🔄 Refresh Logs & Scores", variant="primary", scale=2)
            reset_btn = gr.Button("🔄 Reset Game", variant="secondary", scale=1)
        
        logs = gr.Textbox(
            lines=30, 
            interactive=False, 
            elem_classes=["logs-container"],
            placeholder="Set picks and click refresh to see logs..."
        )

    # Event handlers
    set_btn.click(
        fn=set_user_picks,
        inputs=all_inputs,
        outputs=[status, picks_container, logs_container],
    )
    
    refresh_btn.click(
        fn=get_enhanced_logs,
        outputs=[logs]
    )
    
    def reset_game():
        return (
            "",  # clear status
            gr.update(visible=True),   # show picks container
            gr.update(visible=False),  # hide logs container
            "",  # clear logs
        )
    
    reset_btn.click(
        fn=reset_game,
        outputs=[status, picks_container, logs_container, logs]
    )

demo.launch()