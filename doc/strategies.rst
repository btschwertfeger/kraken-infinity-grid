.. -*- coding: utf-8 -*-
.. Copyright (C) 2025 Benjamin Thomas Schwertfeger
.. GitHub: https://github.com/btschwertfeger
..

Strategies
==========


Information about terms used
----------------------------

- **Base currency**: The base currency is the currency that is being bought and
  sold, e.g. BTC. for the symbol BTC/EUR.

- **Quote currency**: The quote currency is the currency that is being used to
  buy and sell the base currency, e.g. EUR. for the symbol BTC/EUR.

- **Price**: The price is the current price of the base currency in terms of the
  quote currency, e.g. 100,000 USD for 1 BTC, 100,000 is the price.

- **Grid interval**: The grid interval is the percentage difference between the
  placed buy orders, e.g. 4 %. If the current price rises 'too high', the placed
  buy orders will be cancelled and new buy orders will be placed 'interval' %
  below the current price (shifting up). The interval for buy orders is always
  based on the current price _or_ the next higher buy order, e.g. if the current
  price is 100,000 USD and the interval is 4 %, the first buy order will be
  placed at 96,000 USD, the second buy order at 92,160 USD, the third buy order
  at 88,4736 USD, and so on. The interval for sell orders is usually based on
  the buy price, e.g. if the buy price was 100,000 USD, the sell order will be
  placed for 104,000 USD.

- **Shifting up**: Shifting up is the process of canceling and replacing the buy
  orders if the current price rises above a certain threshold, which is
  :math:`(p\cdot(1+i))^2*1.001` where :math:`p` is the highest price of an
  existing, unfilled buy order and :math:`i` is the interval (e.g. 4 %, i.e.
  0.04). This technique ensures that buy orders don't get out of scope.

Fundamental concepts
--------------------

`kraken-infinity-grid`_ enables automatic trading of a cryptocurrency pair. A
currency pair consists of a base currency and a quote currency. The currency
pair, e.g. BTC/USD has as base currency BTC and USD as quote currency.
Basically, this algorithm follows a grid strategy, in which trading takes place
at fixed intervals. This means that assets with very high volatility are
significantly more profitable than those that are subject to lower fluctuation.
The volume of each position always has approximately the same amount. This can
be set by the user or dynamically adjusted by the algorithm (depending on the
strategy used).

If a purchase was made, depending on the strategy, a part of the purchased base
currency is immediately offered for sale in the amount of the specified position
size above the current price. Above means that the size of the specified
interval is adhered to. This interval must be set by the user before the start
(e.g., in 2 % intervals between orders).

Due to the increased price when selling, while the volume in the quote currency
remains the same (depending on the strategy), less of the base currency is sold
than was bought, causing a portion of the base currency to accumulate in the
portfolio each time it is bought (which is true for the `GirdHODL
<strategies-gridhodl-section>`_ strategy).

By default, the accumulated base currency is not further used by the algorithm.
However, there is a possibility to reinvest it. In this case, as soon as there
is no open sell position, a new sell position is set in the amount of the
defined position volume, above the highest buy price corresponding to the
trading interval. This procedure is the part of the optional swing strategy,
which sells the accumulated base currency to increase the stock of the quote
currency. If by selling the

accumulated base currency several times the quota currency exceeds a certain
threshold, the size of the set volume per position will be increased. This new
position size is valid for all positions opened afterwards.

A. CUSTOMIZATION

The following parameters must be defined before starting the algorithm.

- Trading interval
- Number of concurrent open buy orders
- The order volume

The trading interval determines the intervals at which to buy and sell. For some
currency pairs it is worth setting this interval very high (5-10%). Others have
many smaller movements, so for them a lower interval of 0.5-2% can be more
profitable. It should be noted that this interval must be higher than the
transaction fee for the respective assets on the exchange. The number of open
positions indicates the proportion of the available capital to be divided. Here,
a value of 120 should not be exceeded in order to comply with the limits of many
exchanges. The number of always open buy positions specifies how many buy
positions should be open at the same time. If the position interval is defined
to 2%, a number of 5 open buy positions ensures that a rapid price drop of
almost 10% can be caught immediately. After a buy has been triggered, new
positions are placed accordingly. The number of open buy positions should be
kept low to keep the transaction time as short as possible. The following is an
example configuration of the algorithm described herein.

It should be noted that this is spot trading and no leverage products are used.
furthermore, all currencies remain on the user's account. The algorithm can only
trade the currencies there and is not able to send them to other accounts. Users
have the possibility to transfer their assets, which are not in open positions,
back and forth between the accounts at any time. Thus, profits can be realized
or the investment amount can be increased.

All currency pairs mentioned here are for illustrative purposes only.

.. figure:: _static/images/blsh.png
   :width: 600
   :align: center
   :alt: Buying low and selling high


Available strategies
--------------------

.. _strategies-gridhodl-section:

GridHODL
~~~~~~~~

The *GridHODL* strategy is a grid trading strategy that buys and sells at fixed
intervals, e.g. every 4 %. The algorithm places :math:`n` buy orders below the
current price and waits for their execution to then execute the arbitrage and
place a sell order for the bought base currency at 4 % higher. The key idea here
is to accumulate a bit of the base currency over time, as the order size in
terms of quote volume is fixed, e.g. to 100 USD.

.. _strategies-gridsell-section:

GridSell
~~~~~~~~

The *GridSell* strategy is the counterpart of the GridHODL strategy, as it
creates a sell order for 100 % of the base currency bought by a single buy
order, e.g. if a buy order for 100 USD worth of BTC is executed and the interval
is set to 4 %, the sell order size will be 104 USD worth of BTC.

.. _strategies-swing-section:

SWING
~~~~~

The *SWING* strategy is another variation of the GridHODL strategy, as it does
the same but with a twist. The idea is to sell the base currency if the price
rises above the highest price for which the algorithm has bought the currency,
e.g. if the algorithm traded and accumulated a lot of BTC/USD between
40,000-80,000 USD and the highest price for which the algorithm has bought BTC
was 80,000 USD, the algorithm will start placing sell orders at a fixed interval
(e.g. 4 %) if the price rises above 80,000 USD, e.g. to sell 100 USD worth of
BTC at 83,200 USD while further accumulating the currency trades below the
highest buy price.

.. NOTE:: ⚠️ It also starts selling the already existing base currency above the
          current price. This should be kept in mind when choosing this
          strategy.

.. _strategies-cdca-section:

cDCA
~~~~

The *cDCA* strategy is a dollar-cost averaging strategy that buys at fixed
intervals for a fixed size, e.g. 100 USD worth of BTC every 4 % without placing
sell orders in order to accumulate the base currency over team for speculating
on rising value in the long run. The difference to classical DCA strategies is
that even if the price rises, the algorithm will shift-up buy orders instead of
getting out of scope.
