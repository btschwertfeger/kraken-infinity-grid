<h1 align="center">Infinity Grid Trading Algorithm for the Kraken Exchange</h1>

<div align="center">

[![GitHub](https://badgen.net/badge/icon/github?icon=github&label)](https://github.com/btschwertfeger/kraken-infinity-grid)
[![Generic badge](https://img.shields.io/badge/python-3.11+-blue.svg)](https://shields.io/)

[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Typing](https://img.shields.io/badge/typing-mypy-informational)](https://mypy-lang.org/)
[![CI/CD](https://github.com/btschwertfeger/kraken-infinity-grid/actions/workflows/cicd.yaml/badge.svg?branch=master)](https://github.com/btschwertfeger/kraken-infinity-grid/actions/workflows/cicd.yaml)
[![codecov](https://codecov.io/gh/btschwertfeger/kraken-infinity-grid/branch/master/badge.svg)](https://app.codecov.io/gh/btschwertfeger/kraken-infinity-grid)

[![release](https://shields.io/github/release-date/btschwertfeger/kraken-infinity-grid)](https://github.com/btschwertfeger/kraken-infinity-grid/releases)

</div>

# TODOs:

- [x] Telegram exception is not receiving messages properly
- [x] Fix the connection aborted error
- [x] If amount something in balance has changed, cancel all open buy orders
- [x] Show current wealth in telegram
- [x] Improve exception handling
- [x] Add script for calculating max drawdown by given input
- [x] Rename balances table to configuration
- [x] Update docstrings in gridbot.py
- [x] Round amounts to n decimals
- [ ] Testing
  - [x] Add unit tests
  - [x] Add integration tests
  - [ ] Add performance/load tests
- [ ] Setup
  - [x] Use src layout
  - [ ] Use uv in CI
  - [ ] Rename the project to infinity-grid-algorithm
  - [ ] Add codecov to CI and add badge
  - [ ] Add codeql to CI and add badge
  - [ ] Add a badges:
    - [ ] Latest release (PyPI and GitHub)
    - [ ] Documentation
    - [ ] License
    - [ ] Code style
  - [ ] Upload to PyPI
  - [ ] Upload to Docker Hub
- [ ] Add harden runner to CI and add badge
- [ ] Add Scripts or site-tools for backtesting
- [ ] Bugs and open questions
  - [ ] What if execution while bot is initializing?
  - [ ] Call self.close properly after error
  - [ ] Resolve FIXMEs and TODOs
  - [ ] Add timeout for subscribing to ticker and executions to 20 seconds
  - [ ] Fee percentage should be adjustable or depending on the tier
  - [ ] Review the full execution flow and think about how to simplify it.
  - [ ] Extend integration tests
    - [ ] Test unfilled surplus
    - [ ] Update balances of mock API and test what happens if balances are not
          sufficient.
- [ ] Features
  - [ ] Implement proper dryrun (make use of validate trades)
  - [ ] Allow for local sqlite database
- [ ] Write the documentation covering:
  - [ ] Strategies (don't do switches)
  - [ ] Kraken API (use different API keys for different instances)
  - [ ] Configuration
  - [ ] Troubleshooting
  - [ ] Setup
  - [ ] Logging
  - [ ] Telegram notifications
  - [ ] Database configuration
  - [ ] Choosing the right strategy
  - [ ] Choosing the right interval and amount per grid
  - [ ] Backtesting

> ⚠️ **Disclaimer**: This software was initially designed for private use only.
> Please note that this project is independent and not endorsed by Kraken or
> Payward Ltd. Users should be aware that they are using third-party software,
> and the authors of this project are not responsible for any issues, losses, or
> risks associated with its usage. **Payward Ltd. and Kraken are in no way
> associated with the authors of this package and documentation.**
>
> There is no guarantee that this software will work flawlessly at this or later
> times. Of course, no responsibility is taken for possible profits or losses.
> This software probably has some errors in it, so use it at your own risk. Also
> no one should be motivated or tempted to invest assets in speculative forms of
> investment. By using this software you release the author(s) from any liability
> regarding the use of this software.

The Infinity Grid Trading Algorithm is a trading bot that uses grid trading
strategies to trade cryptocurrencies on the [Kraken](https://pro.kraken.com)
Spot exchange. The algorithm is written in Python and uses the
[python-kraken-sdk](https://github.com/btschwertfeger/python-kraken-sdk) library
to interact with the Kraken API.

The algorithm requires a PostgreSQL database and can be run either locally or in
a Docker container (recommended). The algorithm can be configured to use
different trading strategies, such as GridHODL, GridSell, SWING, and DCA.

While the verbosity levels of logging provide useful insights into the bot's
behavior, the Telegram notifications can be used to receive updates on the bot's
activity and exceptions. For this the algorithm requires two different Telegram
bot tokens and chat IDs, one for regular notifications and one for exception
notifications (see [Setup](#Setup) for more information).

# 📍 Strategy Overview

## Information about terms used

- **Base currency**: The base currency is the currency that is being bought
  and sold, e.g. BTC. for the symbol BTC/EUR.

- **Quote currency**: The quote currency is the currency that is being used
  to buy and sell the base currency, e.g. EUR. for the symbol BTC/EUR.

- **Price**: The price is the current price of the base currency in terms of
  the quote currency, e.g. 100,000 USD for 1 BTC, 100,000 is the price.

- **Grid interval**: The grid interval is the percentage difference between the
  placed buy orders, e.g. 4 %. If the current price rises 'to high', the placed
  buy orders will be cancelled and new buy orders will be placed 'interval' %
  below the current price (shifting up). The interval for buy orders is always
  based on the current price _or_ the next higher buy order, e.g. if the current
  price is 100,000 USD and the interval is 4 %, the first buy order will be
  placed at 96,000 USD, the second buy order at 92,160 USD, the third buy order
  at 88,4736 USD, and so on. The interval for sell orders is usually based on
  the buy price, e.g. if the buy price was 100,000 USD, the sell order will be
  placed for 104,000 USD.

- **Shifting up**: Shifting up is the process of canceling and replacing the
  buy orders if the current price rises above a certain threshold, which is
  $(p\cdot(1+i))^2*1.001$ where $p$ is the highest price of an existing,
  unfilled buy order and $i$ is the interval (e.g. 4 %, i.e. 0.04). This
  technique ensures that buy orders don't get out of scope.

## Available Strategies

**GridHODL**

The _GridHODL_ strategy is a grid trading strategy that buys and
sells at fixed intervals, e.g. every 4 %. The algorithm places $n$ buy orders
below the current price and waits for their execution to then execute the
arbitrage and place a sell order for the bought base currency at 4 % higher.
The key idea here is to accumulate a bit of the base currency over time, as the
order size in terms of quote volume is fixed, e.g. to 100 USD.

**GridSell**

The _GridSell_ strategy is the counterpart of the GridHODL strategy,
as it creates a sell order for 100 % of the base currency bought by a single buy
order, e.g. if a buy order for 100 USD worth of BTC is executed and the interval
is set to 4 %, the sell order size will be 104 USD worth of BTC.

**SWING**

<!--
⚠️ It also starts selling the already existing base currency above the current
price.
-->

The _SWING_ strategy is another variation of the GridHODL strategy,
as it does the same but with a twist. The idea is to sell the base currency if
the price rises above the highest price for which the algorithm has bought the
currency, e.g. if the algorithm traded and accumulated a lot of BTC/USD between
40,000-80,000 USD and the highest price for which the algorithm has bought BTC
was 80,000 USD, the algorithm will start placing sell orders at a fixed interval
(e.g. 4 %) if the price rises above 80,000 USD, e.g. to sell 100 USD worth of
BTC at 83,200 USD while further accumulating the currency trades below the
highest buy price.

**DCA**

The _DCA_ strategy is a dollar-cost averaging strategy that buys at
fixed intervals for a fixed size, e.g. 100 USD worth of BTC every 4 % without
placing sell orders in order to accumulate the base currency over team for
speculating on rising value in the long run.

<a name="setup"></a>

# 🚀 Setup

This repository contains a `docker-compose.yaml` file that can be used to run
the algorithm using docker compose. The `docker-compose.yaml` also provides a
default configuration for the PostgreSQL database. To run the algorithm, follow
these steps:

1. Clone the repository:

   ```bash
   git clone https://github.com/btschwertfeger/kraken-infinity-grid.git
   ```

2. Build the Docker images: # FIXME: use public docker registry:

   ```bash
   docker system prune -a
   docker compose build --no-cache
   ```

3. Setup the Telegram bots:

   - Create two new bots, one for regular trading and balance update
     information, and one for receiving messages about errors that might happen
     by talking to the [Botfather](https://telegram.me/BotFather).
   - Start the chat with both new telegram bots.
   - Get the bot token from the BotFather and access
     https://api.telegram.org/bot<your bot token here>/getUpdates to receive
     your chat ID.

4. Configure the algorithm by either by ensuring the environment variables
   documented in the [Configuration](#configuration) section are set.

5. Run the algorithm:

   ```bash
   docker compose up # -d
   ```

6. Check the logs of the container and the Telegram chat for updates.

# 🛠 Configuration

| Variable                       | Type               | Description                                                                                                                                                  |
| ------------------------------ | ------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `KRAKEN_API_KEY`               | `str`              | Your Kraken API key.                                                                                                                                         |
| `KRAKEN_SECRET_KEY`            | `str`              | Your Kraken secret key.                                                                                                                                      |
| `KRAKEN_RUN_NAME`              | `str`              | The name of the bot.                                                                                                                                         |
| `KRAKEN_RUN_USERREF`           | `int`              | A reference number to identify the algorithms's orders. This can be a timestamp or any integer number. **Use different userref's for different algorithms!** |
| `KRAKEN_BOT_VERBOSE`           | `int`/(`-v`,`-vv`) | Enable verbose logging.                                                                                                                                      |
| `KRAKEN_DRY_RUN`               | `bool`             | Enable dry-run mode (no actual trades).                                                                                                                      |
| `KRAKEN_RUN_BASE_CURRENCY`     | `str`              | The base currency e.g., `BTC`.                                                                                                                               |
| `KRAKEN_RUN_QUOTE_CURRENCY`    | `str`              | The quote currency e.g., `USD`.                                                                                                                              |
| `KRAKEN_RUN_AMOUNT_PER_GRID`   | `float`            | The amount to use per grid interval e.g., `100` (USD).                                                                                                       |
| `KRAKEN_RUN_INTERVAL`          | `float`            | The interval between orders e.g., `0.04` to have 4 % intervals).                                                                                             |
| `KRAKEN_RUN_N_OPEN_BUY_ORDERS` | `int`              | The number of concurrent open buy orders, e.g., `3`.                                                                                                         |
| `KRAKEN_RUN_MAX_INVESTMENT`    | `str`              | The maximum investment amount, e.g. `1000` USD.                                                                                                              |
| `KRAKEN_RUN_STRATEGY`          | `str`              | The trading strategy (e.g., `GridHODL`, `GridSell`, `SWING`, or `DCA`).                                                                                      |
| `KRAKEN_RUN_TELEGRAM_TOKEN`    | `str`              | The Telegram bot token for notifications.                                                                                                                    |
| `KRAKEN_RUN_TELEGRAM_CHAT_ID`  | `str`              | The Telegram chat ID for notifications.                                                                                                                      |
| `KRAKEN_RUN_EXCEPTION_TOKEN`   | `str`              | The Telegram bot token for exception notifications.                                                                                                          |
| `KRAKEN_RUN_EXCEPTION_CHAT_ID` | `str`              | The Telegram chat ID for exception notifications.                                                                                                            |
| `KRAKEN_RUN_DB_USER`           | `str`              | The PostgreSQL database user.                                                                                                                                |
| `KRAKEN_RUN_DB_NAME`           | `str`              | The PostgreSQL database name.                                                                                                                                |
| `KRAKEN_RUN_DB_PASSWORD`       | `str`              | The PostgreSQL database password.                                                                                                                            |
| `KRAKEN_RUN_DB_HOST`           | `str`              | The PostgreSQL database host.                                                                                                                                |
| `KRAKEN_RUN_DB_PORT`           | `int`              | The PostgreSQL database port.                                                                                                                                |

<a name="trouble"></a>

# 🚨 Troubleshooting

- Check the **permissions of your API keys** and the required permissions on the
  respective endpoints.
- If you get some Cloudflare or **rate limit errors**, please check your Kraken
  Tier level and maybe apply for a higher rank if required.
- **Use different API keys for different algorithms**, because the nonce
  calculation is based on timestamps and a sent nonce must always be the highest
  nonce ever sent of that API key. Having multiple algorithms using the same
  keys will result in invalid nonce errors.

---

<a name="notes"></a>

# 📝 Notes

The versioning scheme follows the pattern `v<Major>.<Minor>.<Patch>`. Here's
what each part signifies:

- **Major**: This denotes significant changes that may introduce new features or
  modify existing ones. It's possible for these changes to be breaking, meaning
  backward compatibility is not guaranteed. To avoid unexpected behavior, it's
  advisable to specify at least the major version when pinning dependencies.
- **Minor**: This level indicates additions of new features or extensions to
  existing ones. Typically, these changes do not break existing implementations.
- **Patch**: Here, you'll find bug fixes, documentation updates, and changes
  related to continuous integration (CI). These updates are intended to enhance
  stability and reliability without altering existing functionality.

<a name="references"></a>

# 🔭 References

- https://github.com/btschwertfegr/python-kraken-sdk
