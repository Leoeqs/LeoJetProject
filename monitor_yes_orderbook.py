import json
import time
import threading
import websocket  # requires the "websocket-client" library

# Polymarket YES token asset ID to subscribe to:
ASSET_ID = "57338714801830110409291906331043415122319095430948035858069240523339447935973"

# Data structures for order book
bids = {}  # maps price to size for buy orders (bids)
asks = {}  # maps price to size for sell orders (asks)
current_best_bid = None
current_best_ask = None

def on_open(ws):
    """Callback when WebSocket connection is opened. Sends subscription message and starts ping thread."""
    # Subscribe to the market channel for the given asset ID
    subscribe_message = {
        "type": "market",
        "assets_ids": [ASSET_ID]  # list of asset IDs to receive events for
    }
    ws.send(json.dumps(subscribe_message))
    print(f"Subscribed to asset ID {ASSET_ID} (YES token)")

    # Start a background thread to send periodic PING messages to keep connection alive
    def ping_forever():
        while True:
            try:
                ws.send("PING")
            except Exception:
                # If sending fails (e.g. connection closed), exit the thread loop
                break
            time.sleep(15)  # send PING every 15 seconds (adjust as needed)
    ping_thread = threading.Thread(target=ping_forever, daemon=True)
    ping_thread.start()

def on_message(ws, message):
    """Callback for when a message is received from the WebSocket."""
    global bids, asks, current_best_bid, current_best_ask
    try:
        data = json.loads(message)
    except json.JSONDecodeError:
        # If message is not JSON (e.g., a PONG or raw string), handle accordingly
        if message == "PONG":
            return  # ignore PONG responses
        print("Received non-JSON message:", message)
        return

    event_type = data.get("event_type")
    if event_type == "book":
        # Full order book snapshot
        bids.clear()
        asks.clear()
        for entry in data.get("bids", []):
            price = float(entry["price"])
            size = float(entry["size"])
            if size > 0:
                bids[price] = size
        for entry in data.get("asks", []):
            price = float(entry["price"])
            size = float(entry["size"])
            if size > 0:
                asks[price] = size

        # Compute current best bid and ask
        new_best_bid = max(bids.keys()) if bids else None
        new_best_ask = min(asks.keys()) if asks else None
        current_best_bid = new_best_bid
        current_best_ask = new_best_ask
        # Print the initial top-of-book
        if new_best_bid is not None and new_best_ask is not None:
            print(f"Best Bid: {new_best_bid}, Best Ask: {new_best_ask}")
        elif new_best_bid is None and new_best_ask is None:
            print("Order book is empty.")
        else:
            # One side of the book is empty
            if new_best_bid is None:
                print(f"No bids (book empty on buy side), Best Ask: {new_best_ask}")
            if new_best_ask is None:
                print(f"Best Bid: {new_best_bid}, no asks (book empty on sell side)")

    elif event_type == "price_change":
        # Incremental updates to the order book
        changes = data.get("price_changes", [])
        for change in changes:
            if change.get("asset_id") != ASSET_ID:
                # If by chance multiple assets are subscribed, skip others (not expected here)
                continue
            price = float(change.get("price", 0))
            new_size = float(change.get("size", 0))
            side = change.get("side", "").upper()  # "BUY" or "SELL"
            if side == "BUY":
                # Update bid side
                if new_size == 0:
                    bids.pop(price, None)  # remove price level if size is 0
                else:
                    bids[price] = new_size  # add/update bid at this price
            elif side == "SELL":
                # Update ask side
                if new_size == 0:
                    asks.pop(price, None)
                else:
                    asks[price] = new_size

        # After applying all changes, determine new best bid/ask
        new_best_bid = max(bids.keys()) if bids else None
        new_best_ask = min(asks.keys()) if asks else None
        # If top-of-book has changed, print the update
        if new_best_bid != current_best_bid or new_best_ask != current_best_ask:
            if new_best_bid is not None and new_best_ask is not None:
                print(f"Best Bid: {new_best_bid}, Best Ask: {new_best_ask}")
            elif new_best_bid is None and new_best_ask is None:
                print("Order book is empty.")
            else:
                if new_best_bid is None:
                    print(f"No bids, Best Ask: {new_best_ask}")
                if new_best_ask is None:
                    print(f"Best Bid: {new_best_bid}, no asks")
            # Update current bests to the new values
            current_best_bid = new_best_bid
            current_best_ask = new_best_ask

    elif event_type == "tick_size_change":
        # The market's minimum tick size changed (price granularity changed)
        # This does not directly change the order book levels except their allowed increments.
        # We simply log it for information.
        old_tick = data.get("old_tick_size")
        new_tick = data.get("new_tick_size")
        side = data.get("side")
        print(f"Tick size changed ({side} side): {old_tick} -> {new_tick}")

    elif event_type == "last_trade_price":
        # A trade occurred (last traded price message). We don't need this for order book top-of-book, so ignore.
        pass

    else:
        # Handle any other event types or raw messages
        print("Received message:", data)

def on_error(ws, error):
    """Callback for errors."""
    print("WebSocket error:", error)

def on_close(ws, close_status_code, close_msg):
    """Callback when the WebSocket connection is closed."""
    if close_status_code or close_msg:
        print(f"WebSocket closed with code {close_status_code}, reason: {close_msg}")
    else:
        print("WebSocket connection closed")

def run_monitor():
    """Connect to the WebSocket and run indefinitely, with automatic reconnect."""
    url = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
    while True:
        # Create a new WebSocketApp for each connection attempt
        ws_app = websocket.WebSocketApp(url,
                                        on_open=on_open,
                                        on_message=on_message,
                                        on_error=on_error,
                                        on_close=on_close)
        print("Connecting to Polymarket RTDS WebSocket...")
        # Run the WebSocket event loop; this call blocks until the connection is closed
        ws_app.run_forever()
        # If we reach here, the connection was closed or lost; wait and reconnect
        print("Disconnected. Reconnecting in 5 seconds...")
        time.sleep(5)

if __name__ == "__main__":
    run_monitor()
