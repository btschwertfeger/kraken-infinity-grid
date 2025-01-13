import asyncio
import logging
import random
import uuid
from typing import Any, Callable, Self

from kraken.spot import Market, Trade, User

from kraken_infinity_grid.gridbot import KrakenInfinityGridBot


class KrakenAPIMock(Trade, User):
    """
    Class mocking the User and Trade client of the python-kraken-sdk to
    simulate real trading.
    """

    def __init__(
        self: Self,
        kraken_config: dict,
    ) -> None:
        super().__init__()  # DONT PASS SECRETS!
        self.__orders = {}
        self.__balances = kraken_config["balances"]
        self.__fee = kraken_config.get("fee")

        asset_pair_parameter = Market().get_asset_pairs(
            pair=kraken_config["base_currency"] + kraken_config["quote_currency"],
        )
        self.__xsymbol = next(iter(asset_pair_parameter.keys()))
        asset_pair_parameter = asset_pair_parameter[self.__xsymbol]
        self.__altname = asset_pair_parameter["altname"]
        self.__base = asset_pair_parameter["base"]
        self.__quote = asset_pair_parameter["quote"]
        self.__wsname = asset_pair_parameter["wsname"]
        if not self.__fee:
            self.__fee = asset_pair_parameter["fees_maker"][0][1]

    def create_order(self: Self, **kwargs) -> dict:  # noqa: ANN003
        """Create a new order and update balances if needed."""
        txid = str(uuid.uuid4()).upper()
        order = {
            "userref": kwargs["userref"],
            "descr": {
                "pair": self.__altname,
                "type": kwargs["side"],
                "ordertype": kwargs["ordertype"],
                "price": kwargs["price"],
            },
            "status": "open",
            "vol": kwargs["volume"],
            "vol_exec": "0.0",
            "cost": "0.0",
            "fee": "0.0",
        }

        if kwargs["side"] == "buy":
            required_balance = float(kwargs["price"]) * float(kwargs["volume"])
            if float(self.__balances[self.__quote]["balance"]) < required_balance:
                raise ValueError("Insufficient balance to create buy order")
            self.__balances[self.__quote]["balance"] = str(
                float(self.__balances[self.__quote]["balance"]) - required_balance,
            )
            self.__balances[self.__quote]["hold_trade"] = str(
                float(self.__balances[self.__quote]["hold_trade"]) + required_balance,
            )
        elif kwargs["side"] == "sell":
            if float(self.__balances[self.__base]["balance"]) < float(kwargs["volume"]):
                raise ValueError("Insufficient balance to create sell order")
            self.__balances[self.__base]["balance"] = str(
                float(self.__balances[self.__base]["balance"])
                - float(kwargs["volume"]),
            )
            self.__balances[self.__base]["hold_trade"] = str(
                float(self.__balances[self.__base]["hold_trade"])
                + float(kwargs["volume"]),
            )

        self.__orders[txid] = order
        return {"txid": [txid]}

    def fill_order(self: Self, txid: str, volume: float | None = None) -> None:
        """Fill an order and update balances."""
        order = self.__orders.get(txid, {})
        if not order:
            return

        if volume is None:
            volume = float(order["vol"])

        if volume > float(order["vol"]) - float(order["vol_exec"]):
            raise ValueError(
                "Cannot fill order with volume higher than remaining order volume",
            )

        executed_volume = float(order["vol_exec"]) + volume
        remaining_volume = float(order["vol"]) - executed_volume

        order["fee"] = str(float(order["vol_exec"]) * self.__fee)
        order["vol_exec"] = str(executed_volume)
        order["cost"] = str(
            executed_volume * float(order["descr"]["price"]) + float(order["fee"]),
        )

        if remaining_volume <= 0:
            order["status"] = "closed"
        else:
            order["status"] = "open"

        self.__orders[txid] = order

        if order["descr"]["type"] == "buy":
            self.__balances[self.__base]["balance"] = str(
                float(self.__balances[self.__base]["balance"]) + volume,
            )
            self.__balances[self.__quote]["balance"] = str(
                float(self.__balances[self.__quote]["balance"]) - float(order["cost"]),
            )
            self.__balances[self.__quote]["hold_trade"] = str(
                float(self.__balances[self.__quote]["hold_trade"])
                - float(order["cost"]),
            )
        elif order["descr"]["type"] == "sell":
            self.__balances[self.__base]["balance"] = str(
                float(self.__balances["XXBT"]["balance"]) - volume,
            )
            self.__balances[self.__base]["hold_trade"] = str(
                float(self.__balances[self.__base]["hold_trade"]) - volume,
            )
            self.__balances[self.__quote]["balance"] = str(
                float(self.__balances[self.__quote]["balance"]) + float(order["cost"]),
            )

    async def on_ticker_update(self: Self, callback: Callable, last: float) -> None:
        """Update the ticker and fill orders if needed."""
        await callback(
            {
                "channel": "ticker",
                "data": [{"symbol": self.__wsname, "last": last}],
            },
        )

        async def fill_order(txid: str) -> None:
            self.fill_order(txid)
            await callback(
                {
                    "channel": "executions",
                    "type": "update",
                    "data": [{"exec_type": "filled", "order_id": txid}],
                },
            )

        for order in self.get_open_orders()["open"].values():
            if (
                order["descr"]["type"] == "buy"
                and float(order["descr"]["price"]) >= last
            ) or (
                order["descr"]["type"] == "sell"
                and float(order["descr"]["price"]) <= last
            ):
                await fill_order(order["txid"])

    def cancel_order(self: Self, txid: str) -> None:
        """Cancel an order and update balances if needed."""
        order = self.__orders.get(txid, {})
        if not order:
            return

        order.update({"status": "canceled"})
        self.__orders[txid] = order

        if order["descr"]["type"] == "buy":
            executed_cost = float(order["vol_exec"]) * float(order["descr"]["price"])
            remaining_cost = (
                float(order["vol"]) * float(order["descr"]["price"]) - executed_cost
            )
            self.__balances[self.__quote]["balance"] = str(
                float(self.__balances[self.__quote]["balance"]) + remaining_cost,
            )
            self.__balances[self.__quote]["hold_trade"] = str(
                float(self.__balances[self.__quote]["hold_trade"]) - remaining_cost,
            )
            self.__balances[self.__base]["balance"] = str(
                float(self.__balances[self.__base]["balance"])
                - float(order["vol_exec"]),
            )
        elif order["descr"]["type"] == "sell":
            remaining_volume = float(order["vol"]) - float(order["vol_exec"])
            self.__balances[self.__base]["balance"] = str(
                float(self.__balances[self.__base]["balance"]) + remaining_volume,
            )
            self.__balances[self.__base]["hold_trade"] = str(
                float(self.__balances[self.__base]["hold_trade"]) - remaining_volume,
            )
            self.__balances[self.__quote]["balance"] = str(
                float(self.__balances[self.__quote]["balance"]) - float(order["cost"]),
            )

    def cancel_all_orders(self: Self, **kwargs: Any) -> None:  # noqa: ARG002
        """Cancel all open orders."""
        for txid in self.__orders:
            self.cancel_order(txid)

    def get_open_orders(self, **kwargs: Any) -> dict:  # noqa: ARG002
        """Get all open orders."""
        return {
            "open": {k: v for k, v in self.__orders.items() if v["status"] == "open"},
        }

    def get_orders_info(self: Self, txid: str) -> dict:
        """Get information about a specific order."""
        if (order := self.__orders.get(txid, None)) is not None:
            return {txid: order}
        return {}

    def get_balances(self: Self, **kwargs: Any) -> dict:  # noqa: ARG002
        """Get the user's current balances."""
        return self.__balances


class Backtest:
    def __init__(
        self: Self,
        strategy_config: dict,
        db_config: dict,
        kraken_config: dict,
    ) -> None:
        strategy_config |= {
            "telegram_token": "",
            "telegram_chat_id": "",
            "exception_token": "",
            "exception_chat_id": "",
        }
        self.instance = KrakenInfinityGridBot(
            key="key",
            secret="secret",
            config=strategy_config,
            db_config=db_config,
        )

        # We don't need to test for telegram messages here...
        self.instance.t.send_to_telegram = lambda message, exception=False, log=True: (
            logging.getLogger().info(message)
            if log and not exception
            else logging.getLogger().error(message) if exception and log else None
        )
        kraken_config["quote_currency"] = strategy_config["quote_currency"]
        kraken_config["base_currency"] = strategy_config["base_currency"]
        if "fee" in strategy_config:
            kraken_config["fee"] = strategy_config["fee"]
        api = KrakenAPIMock(kraken_config=kraken_config)
        self.instance.user = api
        self.instance.market = Market()
        self.instance.trade = api


def generate_ticker_events(
    price_range: tuple[float, float],
    num_events: int,
    symbol: str = "",
) -> list[dict]:
    events = []
    current_price = random.uniform(*price_range)

    for _ in range(num_events):
        bid = round(current_price, 2)
        ask = round(current_price + random.uniform(0.1, 1.0), 2)
        bid_qty = round(random.uniform(0.1, 1.0), 8)
        ask_qty = round(random.uniform(0.1, 1.0), 8)
        last = bid
        volume = round(random.uniform(1000, 5000), 8)
        vwap = round(random.uniform(price_range[0], price_range[1]), 1)
        low = round(min(price_range[0], current_price - random.uniform(0, 5000)), 1)
        high = round(max(price_range[1], current_price + random.uniform(0, 5000)), 1)
        change = round(last - current_price, 1)
        change_pct = round((change / current_price) * 100, 2)

        event = {
            "channel": "ticker",
            "type": "update",
            "data": [
                {
                    "symbol": symbol,
                    "bid": bid,
                    "bid_qty": bid_qty,
                    "ask": ask,
                    "ask_qty": ask_qty,
                    "last": last,
                    "volume": volume,
                    "vwap": vwap,
                    "low": low,
                    "high": high,
                    "change": change,
                    "change_pct": change_pct,
                },
            ],
        }

        events.append(event)

        # Update current price for next event
        current_price += random.uniform(-1000, 1000)
        current_price = max(price_range[0], min(price_range[1], current_price))

    return events


async def main() -> None:
    """Main function to run the backtest."""

    bt = Backtest(
        strategy_config={
            "strategy": "GridSell",
            "userref": 1,
            "name": "Backtester",
            "interval": 0.02,
            "amount_per_grid": 10,
            "max_investment": 1000,
            "n_open_buy_orders": 5,
            "base_currency": "BTC",
            "quote_currency": "EUR",
        },
        db_config={"sqlite_file": ":memory:"},
        kraken_config={
            "balances": {
                "XXBT": {"balance": "100.0", "hold_trade": "0.0"},
                "ZEUR": {"balance": "1000000.0", "hold_trade": "0.0"},
            },
            "fee": 0.0026,  # 0.26%
        },
    )

    price_range = (50000, 100000)
    num_events = 1000000

    # Generate events
    events = generate_ticker_events(price_range, num_events)

    try:
        await bt.instance.on_message(
            {
                "channel": "executions",
                "type": "snapshot",
                "data": [{"exec_type": "canceled", "order_id": "txid0"}],
            },
        )

        for event in events:
            await bt.instance.trade.on_ticker_update(
                bt.instance.on_message, event["data"][0]["last"]
            )
    except:
        pass
    finally:
        await bt.instance.async_close()
        await bt.instance.stop()
        from textwrap import dedent

        print(
            dedent(
                f"""
                Balances:
                {bt.instance.user.get_balances()}
                """,
            ),
        )


if __name__ == "__main__":
    logging.basicConfig(
        format="%(asctime)s %(levelname)8s | %(message)s",
        datefmt="%Y/%m/%d %H:%M:%S",
        level=logging.ERROR,
    )
    asyncio.run(main())
